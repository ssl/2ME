"""
Python-whois Method for 2ME Domain Checker Framework
Uses the python-whois library for domain WHOIS lookups.
"""

import logging

import whois

from core.whois_parsing import (
    classify_not_registered_reply,
    classify_whois_text,
    parse_quarantine_end_date,
)
from methods import BaseMethod


def _first(value):
    """python-whois returns some fields as a list when a record has several values."""
    return value[0] if isinstance(value, list) and value else value


class PyWhoisMethod(BaseMethod):
    """Looks the domain up in WHOIS and keeps the record for later steps."""

    priority = 30
    method_name = 'pywhois'
    aliases = ('whois',)
    rule_group = 'whois'

    def run(self, domain_status):
        domain = domain_status.domain

        if domain_status.no_registration_record:
            return  # WHOIS would only repeat that there is no record

        try:
            domain_info = whois.whois(domain, quiet=True)
        except Exception as e:
            # python-whois raises the registry's reply as an error when the
            # name is not registered
            result = classify_not_registered_reply(str(e))
            if result:
                self.settle(domain_status, *result)
                return

            domain_status.add_reason('WHOIS error', self.method_name)
            logging.debug(f"PyWhoisMethod error for {domain}: {e}")
            return

        if not domain_info:
            return

        whois_text = domain_info.text
        if whois_text:
            domain_status.whois_text = whois_text
        if domain_info.creation_date:
            domain_status.registration_date = _first(domain_info.creation_date)
        if domain_info.expiration_date:
            domain_status.expiration_date = _first(domain_info.expiration_date)
        domain_status.registrar = domain_info.registrar

        has_registration_data = bool(domain_status.registration_date or domain_status.registrar)

        if whois_text:
            if self.apply_tld_rules(domain_status, whois_text=whois_text.lower()) is not None:
                return

            result = classify_whois_text(whois_text, has_registration_data)
            if result:
                status, reason = result
                if status == 'Quarantine':
                    quarantine_end = parse_quarantine_end_date(whois_text)
                    if quarantine_end:
                        domain_status.expiration_date = quarantine_end
                self.settle(domain_status, status, reason)
                return

        if has_registration_data:
            self.conclude(domain_status, False, 'WHOIS data found')
        else:
            domain_status.add_reason('WHOIS data inconclusive', self.method_name)
