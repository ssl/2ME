"""
Vercel Method for 2ME Domain Checker Framework
Uses Vercel's public registrar API for bulk availability and pricing.
"""

import logging
import time

from core import http_session
from core.progress_utils import create_progress_tracker
from methods import BaseBatchMethod, chunked, is_rate_limit_error


class VercelMethod(BaseBatchMethod):
    """
    Checks up to 200 domains per request, without an account or API key,
    and returns the real price in USD for the ones that can be bought.

    Only "available" answers are used. "Not available" can mean the domain
    is registered, but also that Vercel does not sell that name, so those
    domains stay unknown for the next methods.
    """

    priority = 45  # Before NCAPI (50): fewer requests, and it leaves NCAPI less to do
    method_name = 'vercel'

    SEARCH_URL = 'https://api.vercel.com/v1/registrar/domains/search'
    SUPPORTED_TLDS_URL = 'https://api.vercel.com/v1/registrar/tlds/supported'
    BATCH_SIZE = 200
    BATCH_DELAY = 0.2  # Seconds between batches
    TIMEOUT = 60

    def __init__(self):
        super().__init__()
        self.supported_tlds = None  # Fetched on first use

    def _load_supported_tlds(self):
        """
        TLDs Vercel sells. For any other TLD the API answers "not
        available", which says nothing about the domain.
        """
        try:
            response = http_session.get(self.SUPPORTED_TLDS_URL, timeout=20)
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            return {str(tld).lower().lstrip('.') for tld in response.json()}
        except Exception as e:
            logging.warning(f"VercelMethod: supported TLD list unavailable, skipping Vercel: {e}")
            return set()

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        if self.supported_tlds is None:
            self.supported_tlds = self._load_supported_tlds()

        supported = [ds for ds in domain_statuses if ds.domain.rsplit('.', 1)[-1] in self.supported_tlds]
        if not supported:
            return

        progress = create_progress_tracker("Vercel API requests", len(supported))

        rate_limited = False
        for index, batch in enumerate(chunked(supported, self.BATCH_SIZE)):
            if rate_limited:
                # Stop calling the API once it rate limits; the rest stays unknown
                self._add_reason(batch, "Vercel API rate limited")
            else:
                if index:
                    time.sleep(self.BATCH_DELAY)
                rate_limited = self._check_batch(batch)
            progress.advance(len(batch))

        progress.complete()

    def _add_reason(self, batch, reason):
        for ds in batch:
            ds.add_reason(reason, self.method_name)

    def _check_batch(self, batch):
        """
        Check one batch of domains.

        Returns:
            bool: True when the API rate limited the request
        """
        by_domain = {ds.domain: ds for ds in batch}

        try:
            response = http_session.post(self.SEARCH_URL, json={'domains': list(by_domain)},
                                         timeout=self.TIMEOUT)

            if response.status_code == 429:
                self._add_reason(batch, "Vercel API rate limited")
                logging.warning("VercelMethod rate limited, skipping the remaining domains")
                return True

            if response.status_code != 200:
                self._add_reason(batch, f"Vercel API error (HTTP {response.status_code})")
                return False

            results = response.json().get('results') or []
        except Exception as e:
            logging.error(f"VercelMethod error: {e}")
            if is_rate_limit_error(e):
                self._add_reason(batch, "Vercel API rate limited")
                return True
            self._add_reason(batch, "Vercel API error")
            return False

        for result in results:
            if not isinstance(result, dict):
                continue
            ds = by_domain.get(result.get('domain'))
            if not ds:
                continue

            if result.get('available') not in (True, 'true'):
                continue  # Registered, or not sold by Vercel: left for the next methods

            price = result.get('price')
            price = f"{price:.2f}" if isinstance(price, (int, float)) else None
            if result.get('premium'):
                self.conclude(ds, 'Premium', 'Domain is premium and available', price=price)
            else:
                self.conclude(ds, True, 'Domain is available', price=price)
        return False
