"""
WHOIS VU API Method for 2ME Domain Checker Framework
Uses the whois.vu API service for domain WHOIS lookups.
"""

import logging

from core import http_session
from core.whois_parsing import (
    classify_whois_text,
    extract_dates_from_whois,
    is_quarantine_text,
    parse_quarantine_end_date,
)
from methods import BaseMethod

API_URL = 'https://api.whois.vu/'
HEADERS = {'User-Agent': '2ME Domain Checker', 'Accept': 'application/json'}


def fetch_whois_vu(domain, timeout):
    """
    The whois.vu record of a domain, with the keys 'whois' (text),
    'registrar', 'statuses' and 'available' ('yes', 'no' or other).

    Raises:
        Exception: when the lookup fails or returns no record
    """
    response = http_session.get(API_URL, params={'q': domain}, headers=HEADERS, timeout=timeout)
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}")
    data = response.json()
    if not isinstance(data, dict) or 'domain' not in data:
        raise ValueError("no domain data in response")
    return data


class WhoisVUMethod(BaseMethod):
    """
    Second WHOIS source. The service often takes longer than the timeout,
    so it runs after the fast batch APIs and only sees the few domains
    those could not settle.
    """

    priority = 65
    method_name = 'whoisvuapi'
    aliases = ('whoisvu', 'whois')
    rule_group = 'whois'

    TIMEOUT = 5

    def run(self, domain_status):
        domain = domain_status.domain

        if domain_status.no_registration_record:
            return  # WHOIS would only repeat that there is no record

        try:
            data = fetch_whois_vu(domain, self.TIMEOUT)
        except Exception as e:
            domain_status.add_reason('WHOIS VU API error', self.method_name)
            logging.debug(f"WhoisVUMethod error for {domain}: {e}")
            return

        whois_text = data.get('whois') or ''
        statuses = ' '.join(str(status) for status in data.get('statuses') or [])
        if data.get('registrar'):
            domain_status.registrar = data['registrar']

        if whois_text:
            domain_status.whois_text = whois_text
            dates = extract_dates_from_whois(whois_text, domain)
            domain_status.registration_date = domain_status.registration_date or dates['registration_date']
            domain_status.expiration_date = domain_status.expiration_date or dates['expiration_date']

            if self.apply_tld_rules(domain_status, whois_text=whois_text.lower()) is not None:
                return

        if is_quarantine_text(f"{whois_text}\n{statuses}"):
            quarantine_end = parse_quarantine_end_date(whois_text)
            if quarantine_end:
                domain_status.expiration_date = quarantine_end
            self.conclude(domain_status, 'Quarantine', 'Domain in quarantine')
            return

        available = data.get('available')
        if available == 'yes':
            self.settle(domain_status, True, 'Domain is available')
            return
        if available == 'no':
            self.conclude(domain_status, False, 'WHOIS data found')
            return

        if not whois_text:
            domain_status.add_reason('API returned no WHOIS text', self.method_name)
            return

        has_registration_data = bool(domain_status.registration_date or domain_status.registrar)
        result = classify_whois_text(whois_text, has_registration_data)
        if result:
            self.settle(domain_status, *result)
        elif has_registration_data:
            self.conclude(domain_status, False, 'WHOIS data found')
        else:
            domain_status.add_reason('WHOIS data inconclusive', self.method_name)
