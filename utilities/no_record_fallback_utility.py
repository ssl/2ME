"""
No Record Fallback Utility for 2ME
Decides domains that have no registration record and that no method could judge.
"""

from utilities import BaseUtilityMethod


class NoRecordFallbackUtility(BaseUtilityMethod):
    """
    A domain the registry has no record of is left unknown by the RDAP
    and WHOIS methods, so the registrar APIs can tell whether it is premium
    or reserved. When none of them could judge it either, the missing
    record is the best evidence there is: the domain is reported as
    available.
    """

    priority = 50  # Before WHOIS info extraction (100) and premium detection (200)

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        for domain_status in domain_statuses:
            if domain_status.is_available is None and domain_status.no_registration_record:
                source = domain_status.no_record_source
                reason = f'No registration record ({source})' if source else 'No registration record'
                domain_status.set_availability(True, custom_reason=reason)
