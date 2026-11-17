"""
Gandi API Method for 2ME Domain Checker Framework
Uses Gandi's API for bulk domain availability checking.
"""

import json
import logging
import time

from core import http_session
from core.progress_utils import create_progress_tracker
from methods import BaseBatchMethod, chunked, is_rate_limit_error


class GandiMethod(BaseBatchMethod):
    """Checks domains in batches with Gandi's domain suggestion API."""

    priority = 60
    method_name = 'gandi'

    API_URL = 'https://shop.gandi.net/api/v5/suggest/suggest'
    HEADERS = {
        'Accept': 'text/event-stream',
        'Referer': 'https://shop.gandi.net/en/domain/suggest?search=*&options=1&bulk=1'
    }
    BATCH_SIZE = 50
    BATCH_DELAY = 1.0  # Seconds between batches
    TIMEOUT = 60

    # Gandi availability value -> (status, reason)
    RESULTS = {
        'available': (True, 'Domain is available'),
        'premium': ('Premium', 'Domain is premium and available'),
        'unavailable': (False, 'Domain is registered'),
        'invalid': (False, 'Domain is invalid'),
    }

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to check
        """
        if not domain_statuses:
            return

        progress = create_progress_tracker("Gandi API requests", len(domain_statuses))

        rate_limited = False
        for index, batch in enumerate(chunked(domain_statuses, self.BATCH_SIZE)):
            if rate_limited:
                # Stop calling the API once it rate limits; the rest stays unknown
                self._add_reason(batch, "Gandi API rate limited")
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
        params = {
            'country': 'NL',
            'grid': 'A',
            'currency': 'USD',
            'lang': 'en',
            'search': ' '.join(ds.domain for ds in batch),
            'phases': 'golive',
            'lock_sentence': 'true',
            'page': '1',
            'per_page': '100',
            'required_availables': '15',
            'source': 'shop'
        }

        try:
            with http_session.get(self.API_URL, headers=self.HEADERS, params=params,
                              timeout=self.TIMEOUT, stream=True) as response:
                if response.status_code in (429, 503):
                    self._add_reason(batch, f"Gandi API rate limited (HTTP {response.status_code})")
                    return True

                if response.status_code != 200:
                    self._add_reason(batch, f"Gandi API error (HTTP {response.status_code})")
                    return False

                availability, prices = self._parse_event_stream(response)
        except Exception as e:
            logging.error(f"GandiMethod error: {e}")
            if is_rate_limit_error(e):
                self._add_reason(batch, "Gandi API rate limited")
                return True
            self._add_reason(batch, "Gandi API error")
            return False

        for ds in batch:
            result = self.RESULTS.get(availability.get(ds.domain))
            if not result:
                ds.add_reason('TLD not supported by Gandi', self.method_name)
                continue

            status, reason = result
            price = prices.get(ds.domain) if status in (True, 'Premium') else None
            self.conclude(ds, status, reason, price=price)
        return False

    @staticmethod
    def _parse_event_stream(response):
        """
        Read the server-sent events of a response.

        Returns:
            (availability, prices): dicts keyed by domain name. Availability
            is 'available', 'unavailable', 'invalid' or 'premium'.
        """
        availability = {}
        prices = {}
        event = None

        for line in response.iter_lines(decode_unicode=True):
            if isinstance(line, bytes):  # No charset in the response headers
                line = line.decode('utf-8', errors='replace')
            if not line:
                continue
            if line.startswith('event:'):
                event = line[len('event:'):].strip()
                continue
            if not line.startswith('data:') or event not in ('das', 'billing'):
                continue

            data = json.loads(line[len('data:'):].strip())
            fqdn = data.get('fqdn')

            if event == 'das':
                availability[fqdn] = 'premium' if data.get('premium', 0) == 1 else data.get('availability')
            else:
                price = GandiMethod._create_price(data)
                if price:
                    prices[fqdn] = price
            event = None

        return availability, prices

    @staticmethod
    def _create_price(billing_data):
        """First-year registration price before taxes, from a billing event."""
        try:
            for product in billing_data.get('prices', {}).get('products', []):
                if product.get('process') == 'create':
                    price = product['prices'][0].get('price_before_taxes')
                    return f"{price:.2f}" if isinstance(price, (int, float)) else None
        except (AttributeError, IndexError, KeyError, TypeError):
            pass
        return None
