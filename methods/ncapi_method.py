"""
NCAPI Method for 2ME Domain Checker Framework
Uses NCAPI (Namecheap API) for bulk domain availability checking.
"""

import logging
import time

from core import http_session
from core.progress_utils import create_progress_tracker
from methods import BaseBatchMethod, chunked, is_rate_limit_error


class NCAPIMethod(BaseBatchMethod):
    """Checks domains in batches with the Namecheap status API."""

    priority = 50
    method_name = 'ncapi'

    API_URL = 'https://production.ncapi.io/api/v1/domain/status'
    # Mobile user agent, for a better success rate
    HEADERS = {
        'User-Agent': 'Namecheap-iOS 3.18.5-1 (iPhone 15 Pro iOS 18.1.1)',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    BATCH_SIZE = 50
    BATCH_DELAY = 0.1  # Seconds between batches
    TIMEOUT = 15

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        if not domain_statuses:
            return

        logging.info(f"NCAPIMethod processing {len(domain_statuses)} domains")
        progress = create_progress_tracker("NCAPI requests", len(domain_statuses))

        rate_limited = False
        for index, batch in enumerate(chunked(domain_statuses, self.BATCH_SIZE)):
            if rate_limited:
                # Stop calling the API once it rate limits; the rest stays unknown
                self._add_reason(batch, "Rate limited")
            else:
                if index:
                    time.sleep(self.BATCH_DELAY)
                rate_limited = self._check_batch(batch)
            progress.advance(len(batch))

        progress.complete()

    def _add_reason(self, batch, reason):
        for ds in batch:
            ds.add_reason(self.format_reason(reason))

    def _check_batch(self, batch):
        """
        Check one batch of domains.

        Returns:
            bool: True when the API rate limited the request
        """
        by_domain = {ds.domain: ds for ds in batch}

        try:
            response = http_session.get(self.API_URL, headers=self.HEADERS,
                                    params={'domains': ','.join(by_domain)}, timeout=self.TIMEOUT)

            if response.status_code in (429, 503):
                self._add_reason(batch, f"Rate limited (HTTP {response.status_code})")
                logging.warning(f"NCAPIMethod rate limited for batch starting with {batch[0].domain} "
                                f"(HTTP {response.status_code})")
                return True

            if response.status_code != 200:
                self._add_reason(batch, f"API error (HTTP {response.status_code})")
                logging.error(f"NCAPIMethod API request failed with status code {response.status_code}")
                return False

            data = response.json()
        except Exception as e:
            logging.error(f"NCAPIMethod error: {e}")
            if is_rate_limit_error(e):
                self._add_reason(batch, "Rate limited")
                return True
            self._add_reason(batch, "API error")
            return False

        if not isinstance(data, dict) or 'status' not in data:
            self._add_reason(batch, "Response format error")
            logging.error(f"NCAPIMethod API response format unexpected for batch starting with {batch[0].domain}")
            return False

        for domain_info in data['status']:
            if not isinstance(domain_info, dict):
                continue
            ds = by_domain.get(domain_info.get('domain', ''))
            if ds:
                self._apply_result(ds, domain_info)
        return False

    def _apply_result(self, ds, domain_info):
        if domain_info.get('source', '') == 'n/a':
            # The API has no data for this TLD; the domain stays unknown
            ds.add_reason(self.format_reason('TLD not supported'))
            return

        # The API returns no prices; the TLD's average price stays
        if not domain_info.get('available', False):
            status, reason = False, 'Domain is registered'
        elif domain_info.get('premium', False):
            status, reason = 'Premium', 'Domain is premium and available'
        else:
            status, reason = True, 'Domain is available'

        self.conclude(ds, status, reason)
