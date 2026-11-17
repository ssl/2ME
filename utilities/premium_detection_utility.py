"""
Premium Detection Utility for 2ME
Detects premium domains based on character length for specific TLDs.
"""

from utilities import BaseUtilityMethod

# Registries price very short names as premium. For each TLD: the longest
# name (in characters) that is premium.
PREMIUM_LENGTH_RULES = {
    'pw': 2,
    'st': 2,
    'vip': 3,
    'xyz': 2,
    'fun': 2,
    'bet': 2,
    'me': 2,
    'dev': 2,
    'pro': 2,
    'art': 3,
    'click': 2,
    'online': 2,
    'shop': 2,
    'live': 2,
    'site': 2,
    'one': 2,
    'link': 2,
    'cloud': 3,
    'digital': 2,
    'club': 2,
    'fit': 2,
    'store': 2,
    'group': 2,
    'space': 2,
    'wiki': 2,
    'solutions': 2,
    'services': 2,
    'tech': 3,
    'guru': 2,
    'capital': 2,
    'news': 2,
    'website': 2,
    'today': 2,
    'global': 2,
    'design': 3,
    'health': 2,
    'coffee': 2,
    'city': 2,
    'events': 2,
    'co': 2,
    'io': 2,
    'company': 2,
    'technology': 2,
    'gmbh': 2,
    'sarl': 2,
    'maison': 2,
    'app': 2,
    'agency': 2,
    'work': 3,
    'win': 3,
}


# Methods that ask a registrar or registry, which knows whether a name is premium
REGISTRAR_METHODS = frozenset({'vercel', 'ncapi', 'gandi', 'fastly'})


class PremiumDetectionUtility(BaseUtilityMethod):
    """
    Upgrades available domains to premium when their name is short enough
    to be premium for their TLD. Only for domains no registrar judged:
    a registrar's "available" already accounts for premium names.
    """

    priority = 200  # After all other methods and utilities

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        for domain_status in domain_statuses:
            if domain_status.is_available is not True or domain_status.decided_by in REGISTRAR_METHODS:
                continue

            sld, tld = domain_status.domain.rsplit('.', 1)
            max_premium_length = PREMIUM_LENGTH_RULES.get(tld)
            if not max_premium_length or len(sld) > max_premium_length:
                continue

            # Keep the reason of the method that found the domain available
            original_reason = domain_status.reason or 'Domain is available'
            domain_status.set_availability(
                'Premium',
                custom_reason=f"{original_reason}; premium rule for {tld} ({len(sld)} chars)"
            )
