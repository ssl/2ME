#!/usr/bin/env python3

import sys
import os
import json
import logging
import requests
import concurrent.futures
import threading
import argparse
import itertools
from functools import partial
from prettytable import PrettyTable
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get settings from environment variables with defaults
DOMAINR_API_KEY = os.getenv('DOMAINR_API_KEY', 'none')
MAX_TLD_LENGTH = int(os.getenv('MAX_TLD_LENGTH', '50'))
THREADS = int(os.getenv('THREADS', '25'))
MAX_GENERATE = int(os.getenv('MAX_GENERATE', '1000000'))
OUTPUT_FILE = os.getenv('OUTPUT_FILE', 'output.txt')
DEFAULT_CHARSET = os.getenv('DEFAULT_CHARSET', 'a-z')

# Version
VERSION = "2.2"

# Function to color text using ANSI codes
def color_text(text, color):
    colors = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'orange': '\033[33m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

# Initialize logging
logging.basicConfig(filename='domain_checker_errors.log', level=logging.ERROR,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Define error_messages globally to collect all error messages
error_messages = []

class DomainStatus:
    def __init__(self, domain):
        self.domain = domain
        self.is_available = None  # True, False, 'Premium', or None (Unknown)
        self.price = "N/A"
        self.reason = ""
        self.tld_info = {}
        self.restriction_flag = False  # For coloring
        self.checked_apis = []
        self.lock = threading.Lock()  # To handle concurrent updates

    def add_reason(self, reason, method_name='', positive=False):
        """
        Appends a reason to the current reason if availability is still unknown.
        """
        if method_name:
            reason_str = f"{reason} ({method_name})"
        else:
            reason_str = reason
        with self.lock:
            if self.is_available is None:
                if self.reason:
                    combined_reason = f"{self.reason}; {reason_str}"
                else:
                    combined_reason = reason_str
                # Cap the reason to 140 characters, add '...' if truncated
                if len(combined_reason) > 140:
                    self.reason = combined_reason[:137] + "..."
                else:
                    self.reason = combined_reason
            else:
                # Do not append reasons from other methods once availability is determined
                pass

    def set_availability(self, is_available, price=None, method_name='', custom_reason=None):
        """
        Sets the availability status and updates the reason accordingly.
        If a custom_reason is provided, it uses that instead of the generic reason.
        If the domain is available and has restrictions, appends the restriction reason.
        Overwrites any previous reason if availability is conclusively determined.
        """
        with self.lock:
            self.is_available = is_available
            if price and price not in ["N/A", "Unknown"]:
                self.price = price
            # Prepare the reason based on availability
            if custom_reason:
                reason_str = custom_reason
            else:
                if is_available == True:
                    reason_str = "Domain is available"
                elif is_available == 'Premium':
                    reason_str = "Domain is premium and available"
                elif is_available == False:
                    reason_str = "Domain is registered"
                else:
                    reason_str = "All data was inconclusive"

                if method_name:
                    reason_str += f" ({method_name})"

            if is_available in [True, 'Premium', False]:
                # Overwrite the reason with the current method's reason or custom_reason
                if is_available == True and self.restriction_flag and self.tld_info.get('restrictions', ''):
                    restriction = self.tld_info.get('restrictions', '')
                    combined_reason = f"{reason_str}; {restriction}"
                else:
                    combined_reason = reason_str
                # Cap the reason to 140 characters, add '...' if truncated
                if len(combined_reason) > 140:
                    self.reason = combined_reason[:137] + "..."
                else:
                    self.reason = combined_reason
            else:
                # For inconclusive, overwrite the reason
                if len(reason_str) > 140:
                    self.reason = reason_str[:137] + "..."
                else:
                    self.reason = reason_str

    def set_reason(self, reason):
        """
        Sets the reason directly, capping it to 140 characters with '...' if needed.
        """
        with self.lock:
            if len(reason) > 140:
                self.reason = reason[:137] + "..."
            else:
                self.reason = reason

    def set_tld_info(self, tld_info):
        """
        Sets TLD information and marks if there are restrictions.
        Restrictions will be appended to the reason only if the domain is available.
        Also, sets the default price from TLD's average_price.
        """
        self.tld_info = tld_info
        restrictions = tld_info.get('restrictions', '')
        if restrictions and restrictions != 'No known restrictions':
            self.restriction_flag = True
        # Set default price from TLD's average_price if available
        average_price = tld_info.get('average_price', 'N/A')
        if average_price not in ["N/A", "Unknown"]:
            # Replace comma with dot for consistency if needed
            self.price = average_price.replace(',', '.') if isinstance(average_price, str) else average_price

    def get_colored_availability(self):
        """
        Returns the availability status with appropriate color.
        """
        if self.is_available == True:
            if self.tld_info.get('premium', False):
                return color_text("Premium", 'blue')
            elif self.restriction_flag:
                return color_text("Available", 'orange')
            else:
                return color_text("Available", 'green')
        elif self.is_available == 'Premium':
            return color_text("Premium", 'blue')
        elif self.is_available == False:
            return color_text("Not available", 'red')
        else:
            return color_text("Unknown", 'yellow')

    def get_plain_availability(self):
        """
        Returns the plain text availability status.
        """
        if self.is_available == True:
            if self.tld_info.get('premium', False):
                return "Premium"
            elif self.restriction_flag:
                return "Available"
            else:
                return "Available"
        elif self.is_available == 'Premium':
            return "Premium"
        elif self.is_available == False:
            return "Not available"
        else:
            return "Unknown"

    def print_result(self, table):
        """
        Adds the domain's result to the PrettyTable.
        """
        colored_availability = self.get_colored_availability()
        table.add_row([self.domain, colored_availability, self.price, self.reason])

    def get_result_line(self):
        """
        Returns the result line suitable for file output without color codes.
        """
        availability_msg = self.get_plain_availability()
        return f"{self.domain}\t| {availability_msg}\t| {self.price}\t| {self.reason}"

class Method:
    is_batch_method = False  # Indicates whether the method operates on a batch of domains

    def run(self, domain_status):
        pass

class TLDCheck(Method):
    is_batch_method = False

    def __init__(self, tlds_dict):
        self.tlds_dict = tlds_dict

    def run(self, domain_status):
        domain = domain_status.domain
        method_name = 'TLDCheck'
        if '.' not in domain:
            domain_status.set_availability(False, method_name=method_name, custom_reason='Invalid domain format')
            return True  # Availability determined

        sld, tld = domain.rsplit('.', 1)
        tld = tld.lower()
        domain_status.set_tld_info({})  # Reset TLD info

        # Check if TLD is recognized
        tld_info = self.tlds_dict.get(tld)
        if not tld_info:
            domain_status.set_availability(False, method_name=method_name, custom_reason='TLD not recognized')
            return True  # Availability determined

        domain_status.set_tld_info(tld_info)

        # Check if TLD can be registered
        if not tld_info.get('can_register', False):
            reason = 'TLD cannot be registered'
            if tld_info.get('restrictions', ''):
                restriction = tld_info.get('restrictions', '')
                reason += f"; {restriction}"
            domain_status.set_availability(False, method_name=method_name, custom_reason=reason)
            return True  # Availability determined

        # Check domain length
        sld_length = len(sld)
        min_length = 1#tld_info.get('min_length', 'Unknown')
        max_length = tld_info.get('max_length', 'Unknown')
        try:
            min_length = int(min_length)
        except ValueError:
            min_length = None
        try:
            max_length = int(max_length)
        except ValueError:
            max_length = None

        length_issues = []
        if min_length and sld_length < min_length:
            length_issues.append(f"too short (min {min_length})")
        if max_length and sld_length > max_length:
            length_issues.append(f"too long (max {max_length})")

        if length_issues:
            domain_status.set_availability(False, method_name=method_name, custom_reason=', '.join(length_issues))
            return True  # Availability determined

        return False  # Proceed to next method

class DNSCheck(Method):
    is_batch_method = False

    def run(self, domain_status):
        import dns.resolver
        domain = domain_status.domain
        method_name = 'DNSCheck'
        record_types = ['A', 'MX', 'NS']  # Enhanced to check multiple record types
        try:
            for record_type in record_types:
                answers = dns.resolver.resolve(domain, record_type)
                if answers:
                    if domain.endswith('.ws') and record_type == 'A' and answers[0].address == '64.70.19.203':
                        return False
                    # If any record is found, the domain is registered
                    domain_status.set_availability(False, method_name=method_name, custom_reason=f'{record_type} records found (domain is registered)')
                    return True  # Availability determined
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.Timeout):
            # No records found; continue to next method
            pass
        except Exception as e:
            # Log unexpected DNS errors
            logging.error(f"DNSCheck error for {domain}: {str(e)}")
        return False  # Proceed to next method

class WHOISCheck(Method):
    is_batch_method = False

    def run(self, domain_status):
        global error_messages
        import whois
        domain = domain_status.domain
        method_name = 'WHOISCheck'
        try:
            domain_info = whois.whois(domain, quiet=True)
            if domain_info.text:
                raw_text = domain_info.text.lower()
                if any(keyword in raw_text for keyword in [
                    #'no match for', 'not found', 'no data found',
                    'available for purchase', 'this domain is available for registration',
                    'domain status: available', #'data not found', 'is free'
                ]):
                    # Domain is available
                    domain_status.set_availability(True, method_name=method_name)
                elif any(keyword in raw_text for keyword in [
                    'this domain is not allowed', 'domain cannot be registered', 'prohibited string'
                ]):
                    # Domain is not available
                    domain_status.set_availability(False, method_name=method_name, custom_reason='Domain is not allowed or reserved')
                else:
                    if domain_info.creation_date or domain_info.registrar:
                        # Domain is registered
                        domain_status.set_availability(False, method_name=method_name)
                    else:
                        # WHOIS data inconclusive
                        domain_status.add_reason('WHOIS data inconclusive', method_name)
            else:
                domain_status.add_reason('WHOIS data empty', method_name)
        except Exception as e:
            # Handle known exceptions where WHOIS response indicates availability
            error_message = str(e).lower()
            if any(keyword in error_message for keyword in [
                'no match for', 'not found', 'no data found',
                'available for purchase', 'this domain is available for registration',
                'domain status: available', 'data not found', 'is free'
            ]):
                domain_status.set_availability(True, method_name=method_name)
            else:
                # Only add 'WHOIS error' if availability hasn't been determined by a prior method
                if domain_status.is_available is None:
                    domain_status.add_reason('WHOIS error', method_name)
                # Log the error
                logging.error(f"WHOISCheck error for {domain}: {str(e)}")
        return domain_status.is_available is not None  # Availability determined if not None

class NCAPICheck(Method):
    is_batch_method = True

    def __init__(self):
        pass

    def run(self, domain_statuses):
        global error_messages
        method_name = 'NCAPICheck'
        # domain_statuses is a list of DomainStatus objects with is_available == True or == None
        # We need to process these domains via the API in batches

        # Collect the domains
        domains = [ds.domain for ds in domain_statuses]

        if not domains:
            return

        # Define batch size
        batch_size = 50

        total_domains = len(domains)
        processed_domains = 0

        # Process in batches
        for i in range(0, len(domains), batch_size):
            batch = domains[i:i+batch_size]

            # Update status
            processed_domains += len(batch)
            print(f"\rProcessing NCAPI requests: {processed_domains}/{total_domains}", end='', flush=True)

            # Prepare the request
            api_url = 'https://production.ncapi.io/api/v1/domain/status'

            # Prepare headers
            headers = {
                'User-Agent': 'Namecheap-iOS 3.18.5-1 (iPhone 15 Pro iOS 18.1.1)',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }

            params = {'domains': ','.join(batch)}

            # Make the GET request
            try:
                response = requests.get(api_url, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    # Process the response
                    data = response.json()
                    if 'status' in data:
                        for domain_info in data['status']:
                            domain_name = domain_info.get('domain', '')
                            # Find the corresponding DomainStatus object
                            ds = next((d for d in domain_statuses if d.domain == domain_name), None)
                            if ds:
                                ds.checked_apis.append('NCAPICheck')
                                source = domain_info.get('source', '')
                                if source == 'n/a':
                                    # API cannot retrieve this TLD info, domain remains 'Unknown'
                                    ds.add_reason('Inconclusive', method_name=method_name)
                                else:
                                    available = domain_info.get('available', False)
                                    premium = domain_info.get('premium', False)
                                    average_price = domain_info.get('average_price', 'Unknown')
                                    if available:
                                        if premium:
                                            ds.set_availability('Premium', price=average_price, method_name=method_name)
                                        else:
                                            ds.set_availability(True, price=average_price, method_name=method_name)
                                    else:
                                        ds.set_availability(False, method_name=method_name)
                    else:
                        # Unexpected response format
                        error_messages.append(f"NCAPICheck API response format unexpected for batch starting with {batch[0]}")
                else:
                    # API request failed
                    error_messages.append(f"NCAPICheck API request failed with status code {response.status_code}")
            except Exception as e:
                # Handle exceptions
                error_messages.append(f"NCAPICheck error: {str(e)}")

        # Replace the progress line with a checkmark and message
        print(f"\r{color_text('✓', 'green')} NCAPI requests completed for {processed_domains}/{total_domains} domains{' ' * 10}")

class GandiAPICheck(Method):
    is_batch_method = True

    def __init__(self):
        pass

    def run(self, domain_statuses):
        global error_messages
        method_name = 'GandiAPICheck'
        # domain_statuses is a list of DomainStatus objects needing additional API check
        domains = [ds.domain for ds in domain_statuses]

        if not domains:
            return

        # Define batch size
        batch_size = 50
        total_domains = len(domains)
        processed_domains = 0

        # Process in batches of 50
        for i in range(0, len(domains), batch_size):
            batch = domains[i:i+batch_size]
            current_batch_statuses = domain_statuses[i:i+batch_size]  # Get corresponding DomainStatus objects

            # Update status
            processed_domains += len(batch)
            print(f"\rProcessing Gandi API requests for {processed_domains}/{total_domains} domains...", end='', flush=True)

            # Prepare the request
            api_url = 'https://shop.gandi.net/api/v5/suggest/suggest'

            # Prepare headers
            headers = {
                'Accept': 'text/event-stream',
                'Referer': 'https://shop.gandi.net/en/domain/suggest?search=*&options=1&bulk=1'
            }

            params = {
                'country': 'NL',
                'grid': 'A',
                'currency': 'EUR',
                'lang': 'en',
                'search': ' '.join(batch),
                'phases': 'golive',
                'lock_sentence': 'true',
                'page': '1',
                'per_page': '100',
                'required_availables': '15',
                'source': 'shop'
            }

            try:
                response = requests.get(api_url, headers=headers, params=params, timeout=60, stream=True)
                if response.status_code == 200:
                    # Process the event stream
                    domain_availability = {}
                    domain_prices = {}

                    lines = response.iter_lines(decode_unicode=True)

                    for line in lines:
                        if line.startswith('event: das'):
                            # Next line should be data
                            try:
                                data_line = next(lines)
                            except StopIteration:
                                break
                            data_content = data_line.replace('data: ', '')
                            data = json.loads(data_content)
                            fqdn = data.get('fqdn')
                            availability = data.get('availability')
                            premium = data.get('premium', 0)
                            if premium == 1:
                                domain_availability[fqdn] = 'premium'
                            else:
                                domain_availability[fqdn] = availability

                        elif line.startswith('event: billing'):
                            # Next line should be data
                            try:
                                data_line = next(lines)
                            except StopIteration:
                                break
                            data_content = data_line.replace('data: ', '')
                            data = json.loads(data_content)
                            fqdn = data.get('fqdn')
                            prices = data.get('prices', {})
                            # Extract the create price
                            try:
                                products = prices.get('products', [])
                                for product in products:
                                    if product.get('process') == 'create':
                                        price_info = product.get('prices', [])[0]
                                        average_price = price_info.get('average_price')
                                        if average_price:
                                            domain_prices[fqdn] = average_price
                                        break
                            except Exception:
                                pass

                    # Update domain statuses for the current batch only
                    for ds in current_batch_statuses:
                        ds.checked_apis.append('GandiAPICheck')
                        availability = domain_availability.get(ds.domain)
                        if availability == 'available':
                            # Only update if not already marked as Premium
                            if ds.is_available != 'Premium':
                                average_price = domain_prices.get(ds.domain, 'Unknown')
                                ds.set_availability(True, price=average_price, method_name=method_name)
                        elif availability == 'unavailable':
                            ds.set_availability(False, method_name=method_name)
                        elif availability == 'invalid':
                            ds.set_availability(False, method_name=method_name)
                        elif availability == 'premium':
                            average_price = domain_prices.get(ds.domain, 'Unknown')
                            ds.set_availability('Premium', price=average_price, method_name=method_name)
                        else:
                            # Append reason if API cannot determine status
                            ds.add_reason('Inconclusive', method_name=method_name)
                else:
                    # API request failed
                    error_messages.append(f"GandiAPICheck API request failed with status code {response.status_code}")
            except Exception as e:
                # Handle exceptions
                error_messages.append(f"GandiAPICheck error: {str(e)}")

        # Replace the progress line with a checkmark and message
        print(f"\r{color_text('✓', 'green')} Gandi API requests completed for {processed_domains}/{total_domains} domains{' ' * 10}")

class DomainrAPICheck(Method):
    is_batch_method = True

    def __init__(self, domainr_api_key):
        self.domainr_api_key = domainr_api_key

    def run(self, domain_statuses):
        global error_messages
        method_name = 'DomainrAPICheck'
        domains = [ds.domain for ds in domain_statuses]

        if not domains:
            return

        # Define number of threads
        max_threads = 5

        # Initialize progress counter
        progress = 0
        progress_lock = threading.Lock()

        total_domains = len(domains)

        # Function to process a single domain
        def process_single_domain(domain):
            nonlocal progress
            ds = next((d for d in domain_statuses if d.domain == domain), None)
            if not ds:
                return
            try:
                params = {'domain': domain}
                response = requests.get('https://domainr.p.rapidapi.com/v2/status', headers={
                    'X-RapidAPI-Key': self.domainr_api_key,
                    'X-RapidAPI-Host': 'domainr.p.rapidapi.com'
                }, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    status_list = data.get('status', [])
                    if status_list:
                        status_info = status_list[0]
                        summary = status_info.get('summary')
                        ds.checked_apis.append('DomainrAPICheck')
                        if summary in ['inactive', 'undelegated']:
                            # Confirm availability
                            if ds.is_available == True:
                                # Already marked as available by previous checks
                                pass
                            elif ds.is_available is None:
                                ds.set_availability(True, method_name=method_name)
                                # Append restriction reason if available
                                if ds.restriction_flag and ds.tld_info.get('restrictions', ''):
                                    restriction = ds.tld_info.get('restrictions', '')
                                    ds.add_reason(restriction, method_name=method_name)
                        elif summary in ['active', 'reserved', 'parked']:
                            ds.set_availability(False, method_name=method_name)
                        elif summary == 'disallowed':
                            ds.set_availability(False, method_name=method_name)
                        elif summary == 'premium':
                            average_price = status_info.get('average_price', ds.price)  # Fetch average_price from status_info
                            if average_price not in ["N/A", "Unknown"]:
                                ds.set_availability('Premium', price=average_price, method_name=method_name)
                            else:
                                ds.set_availability('Premium', price=ds.price, method_name=method_name)  # Retain existing price
                        else:
                            ds.add_reason(summary, method_name=method_name)
                else:
                    # API request failed
                    error_messages.append(f"DomainrAPICheck API request failed for {domain} with status code {response.status_code}")
            except Exception as e:
                # Handle exceptions
                error_messages.append(f"DomainrAPICheck error for {domain}: {str(e)}")
            finally:
                with progress_lock:
                    progress += 1
                    print(f"\rProcessing Domainr API requests: {progress}/{total_domains}", end='', flush=True)

        # Use ThreadPoolExecutor with 5 threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {executor.submit(process_single_domain, domain): domain for domain in domains}
            for future in concurrent.futures.as_completed(futures):
                pass  # All processing is handled within process_single_domain

        # After all domains are processed
        print(f"\r{color_text('✓', 'green')} Domainr API requests completed for {progress}/{total_domains} domains{' ' * 10}")

def load_tlds(tlds_file):
    if not os.path.isfile(tlds_file):
        print(f"File '{tlds_file}' not found.")
        sys.exit(1)
    with open(tlds_file, 'r') as f:
        tlds_data = json.load(f)
    # Convert the list to a dictionary for faster access
    tlds_dict = {tld['name']: tld for tld in tlds_data}
    return tlds_dict

def process_domain(domain, methods_sequence):
    domain_status = DomainStatus(domain)
    for method in methods_sequence:
        if not method.is_batch_method:
            availability_determined = method.run(domain_status)
            if availability_determined and domain_status.is_available is not None:
                # If the domain is unavailable, stop further per-domain checks
                if domain_status.is_available == False:
                    break
                # If the domain is available, continue to allow batch methods to process premium status
    return domain_status

def get_sort_key(ds):
    """
    Defines the sort key based on availability priority and price.
    """
    # Assign priority based on availability
    if ds.is_available == True:
        if ds.restriction_flag:
            availability_priority = 2  # Available (orange)
        else:
            availability_priority = 1  # Available (green)
    elif ds.is_available == 'Premium':
        availability_priority = 3
    elif ds.is_available == False:
        availability_priority = 4
    else:
        availability_priority = 5  # Unknown

    # Convert price to float, handle "N/A" or "Unknown" as very high
    try:
        price = float(ds.price)
    except:
        price = float('inf')

    return (availability_priority, price)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=f'2ME {VERSION} - Advanced domain checker for all TLDs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check domains from file
  python 2ME.py -f domains.txt

  # Check specific domains with specific TLDs
  python 2ME.py -d "example,test" --tlds ".com,.net,.org"

  # Generate 3-character domains with all TLDs
  python 2ME.py --generate 3 --charset a-z

  # Generate 4-character domains with specific TLDs, only DNS method
  python 2ME.py --generate 4 --charset a-z0-9 --tlds ".com,.net" --methods dns

  # Check single domain with all methods except WHOIS
  python 2ME.py example.com --exclude-methods whois

  # Only show available domains
  python 2ME.py -f domains.txt --show-status available

  # Hide unavailable and premium domains
  python 2ME.py -f domains.txt --hide-status unavailable,premium

  # Use custom API key
  python 2ME.py example.com --domainr-api-key YOUR_API_KEY
        """
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('domain', nargs='?', help='Single domain to check')
    input_group.add_argument('-f', '--file', help='File containing domains to check')
    input_group.add_argument('-d', '--domains', help='Comma-separated list of domains')
    input_group.add_argument('--generate', type=int, help='Generate domains of specified length')
    
    # TLD options
    parser.add_argument('--tlds', help='TLDs to use: file path, comma-separated list, or "*" for all')
    parser.add_argument('--tlds-file', help='File containing TLDs (one per line)')
    
    # Generation options
    parser.add_argument('--charset', choices=['a-z', 'a-z0-9', '0-9'], default=DEFAULT_CHARSET,
                       help=f'Character set for domain generation (default: {DEFAULT_CHARSET})')
    parser.add_argument('--max-generate', type=int, default=MAX_GENERATE,
                       help=f'Maximum number of domains to generate (default: {MAX_GENERATE})')
    
    # Method selection
    parser.add_argument('--methods', help='Comma-separated list of methods to use: tld,dns,whois,ncapi,gandi,domainr')
    parser.add_argument('--exclude-methods', help='Comma-separated list of methods to exclude')
    
    # Status filtering
    parser.add_argument('--show-status', help='Only show domains with these statuses: available,unavailable,premium,unknown')
    parser.add_argument('--hide-status', help='Hide domains with these statuses: available,unavailable,premium,unknown')
    
    # Output options
    parser.add_argument('-o', '--output', default=OUTPUT_FILE, help=f'Output file (default: {OUTPUT_FILE})')
    parser.add_argument('--threads', type=int, default=THREADS, help=f'Number of threads (default: {THREADS})')
    
    # API configuration
    parser.add_argument('--domainr-api-key', default=DOMAINR_API_KEY, 
                       help=f'Domainr API key (default: from environment or "none")')
    
    # Other options
    parser.add_argument('--max-tld-length', type=int, default=MAX_TLD_LENGTH,
                       help=f'Maximum TLD length (default: {MAX_TLD_LENGTH})')
    parser.add_argument('--version', action='version', version=f'2ME {VERSION}')
    
    return parser.parse_args()

def load_domains_from_file(file_path):
    """Load domains from a file."""
    if not os.path.isfile(file_path):
        print(f"File '{file_path}' not found.")
        sys.exit(1)
    with open(file_path, 'r') as f:
        domains = [line.strip() for line in f if line.strip()]
    return domains

def load_tlds_from_file(file_path):
    """Load TLDs from a file."""
    if not os.path.isfile(file_path):
        print(f"File '{file_path}' not found.")
        sys.exit(1)
    with open(file_path, 'r') as f:
        tlds = [line.strip().lstrip('.').lower() for line in f if line.strip()]
    return tlds

def parse_tlds(tlds_arg, max_tld_length):
    """Parse TLDs from argument."""
    if not tlds_arg or tlds_arg == '*':
        # Load all TLDs
        all_tlds_file = 'all-tlds.txt'
        if not os.path.isfile(all_tlds_file):
            print(f"File '{all_tlds_file}' not found for loading all TLDs.")
            sys.exit(1)
        return load_tlds_from_file(all_tlds_file)
    elif os.path.isfile(tlds_arg):
        # Load from file
        return load_tlds_from_file(tlds_arg)
    else:
        # Parse comma-separated list
        tlds = [tld.strip().lstrip('.').lower() for tld in tlds_arg.split(',') if tld.strip()]
        return [tld for tld in tlds if len(tld) <= max_tld_length]

def generate_domains(length, charset, max_generate):
    """Generate domains of specified length using given character set."""
    if charset == 'a-z':
        chars = 'abcdefghijklmnopqrstuvwxyz'
    elif charset == 'a-z0-9':
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    elif charset == '0-9':
        chars = '0123456789'
    else:
        raise ValueError(f"Unknown charset: {charset}")
    
    domains = []
    count = 0
    for domain in itertools.product(chars, repeat=length):
        if count >= max_generate:
            break
        domains.append(''.join(domain))
        count += 1
    
    return domains

def get_available_methods():
    """Get list of available method names."""
    return ['tld', 'dns', 'whois', 'ncapi', 'gandi', 'domainr']

def create_methods_sequence(tlds_dict, methods_arg=None, exclude_methods_arg=None, domainr_api_key=DOMAINR_API_KEY):
    """Create methods sequence based on arguments."""
    available_methods = get_available_methods()
    
    if methods_arg:
        # Only use specified methods
        specified_methods = [m.strip().lower() for m in methods_arg.split(',')]
        use_methods = [m for m in specified_methods if m in available_methods]
    else:
        # Use all methods by default
        use_methods = available_methods.copy()
    
    if exclude_methods_arg:
        # Remove excluded methods
        excluded_methods = [m.strip().lower() for m in exclude_methods_arg.split(',')]
        use_methods = [m for m in use_methods if m not in excluded_methods]
    
    # Create method instances
    methods_sequence = []
    batch_methods = []
    
    for method in use_methods:
        if method == 'tld':
            methods_sequence.append(TLDCheck(tlds_dict))
        elif method == 'dns':
            methods_sequence.append(DNSCheck())
        elif method == 'whois':
            methods_sequence.append(WHOISCheck())
        elif method == 'ncapi':
            batch_methods.append(('ncapi', NCAPICheck()))
        elif method == 'gandi':
            batch_methods.append(('gandi', GandiAPICheck()))
        elif method == 'domainr':
            batch_methods.append(('domainr', DomainrAPICheck(domainr_api_key)))
    
    return methods_sequence, batch_methods

def should_show_domain(domain_status, show_status_arg, hide_status_arg):
    """Determine if domain should be shown based on status filters."""
    status = domain_status.get_plain_availability().lower()
    
    # Map status to standard names
    status_map = {
        'available': 'available',
        'not available': 'unavailable',
        'premium': 'premium',
        'unknown': 'unknown'
    }
    
    normalized_status = status_map.get(status, status)
    
    # Check show filter
    if show_status_arg:
        show_statuses = [s.strip().lower() for s in show_status_arg.split(',')]
        if normalized_status not in show_statuses:
            return False
    
    # Check hide filter
    if hide_status_arg:
        hide_statuses = [s.strip().lower() for s in hide_status_arg.split(',')]
        if normalized_status in hide_statuses:
            return False
    
    return True

def main():
    global error_messages
    
    # Parse arguments
    args = parse_arguments()
    
    # Use arguments for all configuration (command line overrides environment variables)
    domainr_api_key = args.domainr_api_key
    max_tld_length = args.max_tld_length
    threads = args.threads
    max_generate = args.max_generate
    output_file = args.output
    charset = args.charset
    tlds_json_file = 'tlds.json' # Hardcoded default
    all_tlds_file = 'all-tlds.txt' # Hardcoded default
    default_domains_file = 'checkthis.txt' # Hardcoded default
    
    # Determine input domains
    domains = []
    
    if args.domain:
        # Single domain
        if '.' in args.domain:
            domains = [args.domain]
        else:
            # Base domain, need TLDs
            base_domain = args.domain
            tlds = parse_tlds(args.tlds, max_tld_length)
            domains = [f"{base_domain}.{tld}" for tld in tlds]
    elif args.file:
        # Load from file
        domains = load_domains_from_file(args.file)
    elif args.domains:
        # Comma-separated domains
        input_domains = [d.strip() for d in args.domains.split(',') if d.strip()]
        domains = []
        
        # Check if any domain lacks a TLD (no dot)
        base_domains = [d for d in input_domains if '.' not in d]
        full_domains = [d for d in input_domains if '.' in d]
        
        # Add full domains as-is
        domains.extend(full_domains)
        
        # For base domains, combine with TLDs if provided
        if base_domains:
            if args.tlds:
                tlds = parse_tlds(args.tlds, max_tld_length)
                for base_domain in base_domains:
                    for tld in tlds:
                        domains.append(f"{base_domain}.{tld}")
            else:
                # If no TLDs specified, treat as invalid
                for base_domain in base_domains:
                    domains.append(base_domain)  # This will fail validation
    elif args.generate:
        # Generate domains
        base_domains = generate_domains(args.generate, charset, max_generate)
        tlds = parse_tlds(args.tlds, max_tld_length)
        
        # Limit total combinations
        domains = []
        for base_domain in base_domains:
            for tld in tlds:
                if len(domains) >= max_generate:
                    break
                domains.append(f"{base_domain}.{tld}")
            if len(domains) >= max_generate:
                break
    else:
        # Default: check default domains file
        if not os.path.isfile(default_domains_file):
            print(f"No input specified and default file '{default_domains_file}' not found.")
            print("Use -h for help.")
            sys.exit(1)
        domains = load_domains_from_file(default_domains_file)

    if not domains:
        print("No domains to process.")
        sys.exit(0)

    # Load TLDs information
    tlds_dict = load_tlds(tlds_json_file)

    # Create methods sequence
    methods_sequence, batch_methods = create_methods_sequence(
        tlds_dict, args.methods, args.exclude_methods, domainr_api_key
    )

    # Initialize PrettyTable
    table = PrettyTable()
    table.field_names = ["Domain", "Availability", "Price (USD)", "Reason"]
    table.align["Domain"] = "l"
    table.align["Availability"] = "l"
    table.align["Price (USD)"] = "l"
    table.align["Reason"] = "l"
    table.hrules = 1

    domain_statuses = []
    total_domains = len(domains)

    # Print header
    print(f"2ME {VERSION} - Advanced domain checker for all TLDs")
    print(f"Processing {total_domains} domains with {len(methods_sequence)} per-domain methods and {len(batch_methods)} batch methods")
    print(f"Using up to {threads} threads...\n")

    # Process per-domain methods with multithreading
    if methods_sequence:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            process_func = partial(process_domain, methods_sequence=methods_sequence)
            futures = {executor.submit(process_func, domain): domain for domain in domains}
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                domain_status = future.result()
                domain_statuses.append(domain_status)
                completed += 1
                if completed % 10 == 0 or completed == total_domains:
                    print(f"\rProcessed {completed}/{total_domains} domains", end='', flush=True)
        print(f"\n{color_text('✓', 'green')} Domains processed ({total_domains}/{total_domains})")
    else:
        # No per-domain methods, create DomainStatus objects
        for domain in domains:
            domain_statuses.append(DomainStatus(domain))

    # Process batch methods
    for method_name, method_instance in batch_methods:
        if method_name == 'ncapi':
            batch_domains = [ds for ds in domain_statuses if ds.is_available == True or ds.is_available is None]
        elif method_name == 'gandi':
            batch_domains = [ds for ds in domain_statuses if ds.is_available is None]
        elif method_name == 'domainr':
            batch_domains = [ds for ds in domain_statuses if ds.is_available is None]
        else:
            batch_domains = domain_statuses
        
        if batch_domains:
            method_instance.run(batch_domains)

    print()
    
    # Sort the domain_statuses list
    sorted_domain_statuses = sorted(domain_statuses, key=get_sort_key)

    # Filter domains based on status
    filtered_statuses = []
    for ds in sorted_domain_statuses:
        if should_show_domain(ds, args.show_status, args.hide_status):
            filtered_statuses.append(ds)

    # Add filtered domain statuses to table and write to output file
    with open(output_file, 'w') as outfile:  # Changed to 'w' to overwrite
        for ds in filtered_statuses:
            ds.print_result(table)
            result_line = ds.get_result_line()
            outfile.write(f"{result_line}\n")

    print(table)

    print(f"\nShowing {len(filtered_statuses)} of {len(sorted_domain_statuses)} domains")
    print(f"Results written to {output_file}")

    # Print any errors collected
    if error_messages:
        print(f"\n{len(error_messages)} errors encountered during processing (check domain_checker_errors.log)")

if __name__ == "__main__":
    # Suppress all logging messages in console
    logging.getLogger().setLevel(logging.CRITICAL)
    # Check for required modules
    try:
        import dns.resolver
    except ImportError:
        print("The 'dnspython' module is required. Install it by running 'pip install dnspython'")
        sys.exit(1)
    try:
        import whois
    except ImportError:
        print("The 'python-whois' module is required. Install it by running 'pip install python-whois'")
        sys.exit(1)
    try:
        import requests
    except ImportError:
        print("The 'requests' module is required. Install it by running 'pip install requests'")
        sys.exit(1)
    try:
        from prettytable import PrettyTable
    except ImportError:
        print("The 'PrettyTable' module is required. Install it by running 'pip install prettytable'")
        sys.exit(1)
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("The 'python-dotenv' module is required. Install it by running 'pip install python-dotenv'")
        sys.exit(1)
    main()
