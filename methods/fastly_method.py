"""
Fastly Method for 2ME Domain Checker Framework
Uses Fastly's Domain Research API for the domains no other method could judge.
"""

import concurrent.futures
import logging
import threading

from core import http_session
from core.progress_utils import create_progress_tracker
from methods import BaseBatchMethod, is_rate_limit_error

# Status flags -> (availability, reason), checked in this order. A domain
# carries several flags; the first group that matches decides.
STATUS_RULES = (
    ({'deleting', 'expiring'}, 'Quarantine', 'Domain in quarantine'),
    ({'active', 'parked', 'marketed', 'priced', 'transferable'}, False, 'Domain is registered'),
    ({'reserved', 'claimed', 'dpml'}, False, 'Domain is reserved'),
    ({'disallowed', 'invalid'}, False, 'Domain is not allowed'),
    ({'pending'}, False, 'TLD is not open for registration yet'),
    ({'premium'}, 'Premium', 'Domain is premium and available'),
    ({'inactive'}, True, 'Domain is available'),
)


def classify_status(status):
    """
    Availability from Fastly's space-delimited status flags, or None when
    they do not say (such as 'unknown', or 'undelegated' alone, which the
    API also returns when the registry did not answer in time).
    """
    flags = set(str(status).lower().split())
    for group, availability, reason in STATUS_RULES:
        if flags & group:
            return availability, reason
    return None


class FastlyMethod(BaseBatchMethod):
    """
    Asks the registry through Fastly, one domain per request. Optional: it
    only runs with a Fastly API token, and runs last because requests beyond
    the free monthly allowance are paid.
    """

    priority = 70
    method_name = 'fastly'

    API_URL = 'https://api.fastly.com/domain-management/v1/tools/status'
    MAX_THREADS = 5
    TIMEOUT = 35  # The API itself gives up on a registry after 30 seconds

    def __init__(self, fastly_api_token=None):
        super().__init__()
        self.token = fastly_api_token
        self.token_rejected = False

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        if not self.token or not domain_statuses:
            return

        progress = create_progress_tracker("Fastly API requests", len(domain_statuses))
        stop = threading.Event()  # Set on a rate limit or a rejected token

        def check(ds):
            try:
                if stop.is_set():
                    ds.add_reason('Fastly API skipped', self.method_name)
                elif self._check_domain(ds):
                    stop.set()
            except Exception as e:
                logging.error(f"FastlyMethod error for {ds.domain}: {e}")
            finally:
                progress.advance()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_THREADS) as executor:
            for _ in executor.map(check, domain_statuses):
                pass

        progress.complete()
        if self.token_rejected:
            print("Fastly rejected the API token; check FASTLY_API_TOKEN")

    def _check_domain(self, ds):
        """
        Check one domain.

        Returns:
            bool: True when the remaining domains should not be sent
        """
        try:
            response = http_session.get(self.API_URL, headers={'Fastly-Key': self.token},
                                        params={'domain': ds.domain}, timeout=self.TIMEOUT)

            if response.status_code in (401, 403):
                self.token_rejected = True
                ds.add_reason(f"Fastly API token rejected (HTTP {response.status_code})", self.method_name)
                return True

            if response.status_code == 429:
                ds.add_reason("Fastly API rate limited", self.method_name)
                logging.warning("FastlyMethod: rate limited, skipping the remaining domains")
                return True

            if response.status_code != 200:
                ds.add_reason(f"Fastly API error (HTTP {response.status_code})", self.method_name)
                return False

            data = response.json()
        except Exception as e:
            logging.debug(f"FastlyMethod error for {ds.domain}: {e}")
            if is_rate_limit_error(e):
                ds.add_reason("Fastly API rate limited", self.method_name)
                return True
            ds.add_reason("Fastly API error", self.method_name)
            return False

        # A status record, or a list of them as in the former Domainr API
        if isinstance(data, dict) and isinstance(data.get('status'), list):
            data = next((item for item in data['status'] if isinstance(item, dict)), {})
        status = data.get('status', '') if isinstance(data, dict) else ''

        result = classify_status(status)
        if result:
            self.conclude(ds, *result)
        else:
            ds.add_reason(f"Fastly status: {status or 'none'}", self.method_name)
        return False
