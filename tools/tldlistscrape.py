import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import json
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_tld_info(tld, driver):
    tld = tld.lower()
    url = f'https://tld-list.com/tld/{tld}'
    try:
        driver.get(url)
        # Wait for the 'price-info' section to load
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.ID, 'price-info'))
        )
        page_source = driver.page_source
    except Exception as e:
        print(f'Failed to fetch data for {tld}')
        return {'name': tld.lower(), 'can_register': False}

    soup = BeautifulSoup(page_source, 'html.parser')
    tld_info = {'name': tld.lower(), 'can_register': False}

    # Initialize fields with '?'
    tld_info_fields = [
        'average_price', 'min_length', 'max_length', 'restrictions',
        'registry_site', 'whois_server'
    ]
    for field in tld_info_fields:
        tld_info[field] = '?'

    # Extract Average Registrar Price (registration)
    pricing_section = soup.find('h2', id='price-info')
    if pricing_section:
        table = pricing_section.find_next('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                label_td = row.find('td')
                if label_td:
                    label_text = label_td.get_text(strip=True)
                    if re.search(r'Average Registrar Prices', label_text, re.I):
                        price_td = label_td.find_next_sibling('td')
                        if price_td:
                            # Find the registration price
                            subrows = price_td.find_all('div', class_='subrow2-row')
                            for subrow in subrows:
                                sub_label = subrow.find('div', class_='subrow2-cell text-right smaller85 nowrap')
                                sub_value = sub_label.find_next_sibling('div', class_='subrow2-cell text-right lpad-cell')
                                if sub_label and sub_value:
                                    sub_label_text = sub_label.get_text(strip=True).lower()
                                    if 'registration' in sub_label_text:
                                        avg_reg_price = sub_value.get_text(strip=True)
                                        if 'not available' not in avg_reg_price.lower():
                                            avg_reg_price = avg_reg_price.replace('$', '').strip()
                                            tld_info['average_price'] = avg_reg_price
                                            tld_info['can_register'] = True
                                        else:
                                            tld_info['average_price'] = 'Not available'
                                        break
                        break  # Exit after finding the average registrar prices

    # Extract min_length and max_length from Domain Syntax section
    domain_syntax_section = soup.find('h2', id='domain-syntax')
    if domain_syntax_section:
        table = domain_syntax_section.find_next('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                label_td = row.find('td')
                value_td = label_td.find_next_sibling('td') if label_td else None
                if label_td and value_td:
                    label = label_td.get_text(strip=True).lower()
                    value = value_td.get_text(strip=True)
                    if 'minimum registerable characters' in label:
                        tld_info['min_length'] = value
                    elif 'maximum registerable characters' in label:
                        tld_info['max_length'] = value

    # Extract Restrictions from Policy section
    policy_section = soup.find('h2', id='policy')
    if policy_section:
        table = policy_section.find_next('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                label_td = row.find('td')
                value_td = label_td.find_next_sibling('td') if label_td else None
                if label_td and value_td:
                    label = label_td.get_text(strip=True).lower()
                    value = value_td.get_text(strip=True)
                    if 'restrictions' in label:
                        tld_info['restrictions'] = value

    # Extract Registry Website and WHOIS Server from Registry section
    registry_section = soup.find('h2', id='registry')
    if registry_section:
        table = registry_section.find_next('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                label_td = row.find('td')
                value_td = label_td.find_next_sibling('td') if label_td else None
                if label_td and value_td:
                    label = label_td.get_text(strip=True).lower()
                    value = value_td.get_text(strip=True)
                    if 'registry website' in label:
                        registry_site = value.lower()
                        # Extract href if it's a link
                        link = value_td.find('a', href=True)
                        if link:
                            registry_site = link['href']
                        tld_info['registry_site'] = registry_site
                    elif 'whois server' in label:
                        tld_info['whois_server'] = value.lower()

    return tld_info

def main():
    tlds = []
    with open('all-tlds.txt') as f:
        for line in f:
            tld = line.strip()
            if tld:
                tlds.append(tld)

    tld_data_list = []

    # Initialize undetected_chromedriver
    options = uc.ChromeOptions()
    # Uncomment the next line to run Chrome in headless mode
    #options.add_argument('--headless=new')
    driver = uc.Chrome(options=options)

    try:
        for tld in tlds:
            print(f'Processing {tld}')
            tld_info = get_tld_info(tld, driver)
            tld_data_list.append(tld_info)
            print(tld_info)
    finally:
        driver.quit()

    with open('tlds.json', 'w') as f:
        json.dump(tld_data_list, f, indent=4)

if __name__ == '__main__':
    main()
