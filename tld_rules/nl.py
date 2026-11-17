"""
TLD rules for .nl domains
"""

import re

from core.whois_parsing import parse_quarantine_end_date
from tld_rules import tld_rule

# Status values in the .nl WHOIS output -> reason for a registered domain
REGISTERED_STATUSES = (
    ('status: active', 'Domain registered (status: active)'),
    ('status: inactive', 'Domain registered (status: inactive)'),
    ('status: not free', 'Domain not available (status: not free)'),
)


@tld_rule(method='whois')
def nl_whois_rule(domain_status, method_name, whois_text=None, **kwargs):
    """Reads the registry's status line; quarantine comes with its end date."""
    if not whois_text:
        return None

    # The registry pads its fields ("Status:      active"), so collapse runs
    # of spaces and tabs before matching.
    whois_lower = re.sub(r'[ \t]+', ' ', whois_text.lower())

    if 'quarantine' in whois_lower:
        quarantine_end = parse_quarantine_end_date(whois_lower)
        if quarantine_end:
            domain_status.expiration_date = quarantine_end
        domain_status.set_availability('Quarantine', method_name=method_name,
                                       custom_reason=f'Domain in quarantine ({method_name})')
        return True

    # A free name is left for the registrar APIs, like any name without a record
    if f'{domain_status.domain} is free' in whois_lower or 'status: free' in whois_lower:
        domain_status.mark_no_registration_record(method_name)
        return True

    for marker, reason in REGISTERED_STATUSES:
        if marker in whois_lower:
            domain_status.set_availability(False, method_name=method_name,
                                           custom_reason=f'{reason} ({method_name})')
            return True

    return None
