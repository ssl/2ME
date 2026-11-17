"""
TLD Check Method for 2ME Domain Checker Framework
Validates domain format against the TLD definitions in data/tlds.json.
"""

import re

from methods import BaseMethod

# One label of a domain name: letters, digits and hyphens, not starting or
# ending with a hyphen. Internationalised names arrive in punycode (xn--).
LABEL_RE = re.compile(r'(?!-)[a-z0-9-]{1,63}(?<!-)')


class TLDCheckMethod(BaseMethod):
    """
    Validates the domain name and the TLD's registration rules, and stores
    the TLD information (default price, restrictions) on the domain.
    Runs first so the other methods only see domains that can exist.

    The min_length in tlds.json is the shortest name sold at the standard
    price; shorter names are often sold as premium, so it is not enforced.
    """

    priority = 10
    method_name = 'tld'
    aliases = ('tld_check',)

    def __init__(self, tlds_dict=None):
        super().__init__()
        self.tlds_dict = tlds_dict or {}

    def run(self, domain_status):
        domain = domain_status.domain
        labels = domain.split('.')

        if len(labels) < 2 or len(domain) > 253 or not all(LABEL_RE.fullmatch(label) for label in labels):
            self.conclude(domain_status, False, 'Invalid domain name')
            return

        sld, tld = domain.rsplit('.', 1)
        tld_info = self.tlds_dict.get(tld)
        if not tld_info:
            self.conclude(domain_status, False, 'TLD not recognized')
            return

        # Set TLD info (including price) before applying custom rules
        domain_status.set_tld_info(tld_info)

        if self.apply_tld_rules(domain_status) is not None:
            return

        if not tld_info.get('can_register', False):
            reason = 'TLD cannot be registered'
            if tld_info.get('restrictions'):
                reason += f"; {tld_info['restrictions']}"
            self.conclude(domain_status, False, reason)
            return

        try:
            max_length = int(tld_info.get('max_length', ''))
        except (TypeError, ValueError):
            max_length = None
        if max_length and len(sld) > max_length:
            self.conclude(domain_status, False, f"too long (max {max_length})")
