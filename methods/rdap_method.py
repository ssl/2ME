"""
RDAP Method for 2ME Domain Checker Framework
Looks domains up with RDAP, the registries' structured successor to WHOIS.
"""

import collections
import json
import logging
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

from core import http_session
from core.utils import RDAP_SERVERS_FILE
from core.whois_parsing import parse_date_string
from methods import BaseMethod


def load_rdap_servers(servers_file=RDAP_SERVERS_FILE):
    """
    RDAP server per TLD.

    Only list a server that answers 200 for a registered name and 404 for a
    made-up one: a server that knows part of a TLD would report registered
    domains as having no record.

    Returns:
        dict: TLD -> base URL of its RDAP server (empty when unavailable)
    """
    try:
        with open(servers_file, 'r') as f:
            return {tld.lower(): url for tld, url in json.load(f).items()}
    except Exception as e:
        logging.warning(f"RDAP server list could not be read: {e}")
        return {}


def _parse_event_date(value):
    """RDAP event dates are ISO 8601 timestamps; returned without time zone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return parse_date_string(str(value))


def _registrar_name(rdap_data):
    """Name of the registrar entity in an RDAP domain record, or None."""
    try:
        for entity in rdap_data.get('entities') or []:
            if 'registrar' in (entity.get('roles') or []):
                for field in entity.get('vcardArray', [None, []])[1]:
                    if field[0] == 'fn':
                        return field[3]
    except (AttributeError, IndexError, TypeError):
        pass
    return None


class RDAPMethod(BaseMethod):
    """
    Settles registered domains with one fast, structured lookup at the
    registry, including their registration and expiration dates.

    A domain without a record is not registered, but may still be reserved
    or premium. It stays unknown so the registrar APIs can judge it, and is
    marked so the WHOIS methods do not look up the same absence again.
    """

    priority = 25  # After DNS (20), before WHOIS (30)
    method_name = 'rdap'

    HEADERS = {
        'Accept': 'application/rdap+json',
        'User-Agent': '2ME Domain Checker'
    }
    TIMEOUT = 6
    MAX_CONCURRENT_PER_SERVER = 8    # Many TLDs share one server; bursts get rate limited
    MAX_RETRY_WAIT = 3               # Seconds to wait before retrying a rate-limited lookup
    MAX_RATE_LIMITS_PER_SERVER = 10  # Rate limits that survive a retry before the server is skipped

    # WHOIS for .nl reports quarantine and its end date; how the .nl RDAP
    # server reports quarantine has not been verified, so .nl stays on WHOIS.
    SKIP_TLDS = frozenset({'nl'})

    # RDAP statuses of a deleted domain that is not yet released (RFC 8056)
    QUARANTINE_STATUSES = frozenset({'redemption period', 'pending delete'})

    def __init__(self, rdap_servers=None):
        super().__init__()
        self.servers = rdap_servers if rdap_servers is not None else load_rdap_servers()
        self.rate_limits = collections.Counter()  # Server host -> rate limits received
        self.rate_limit_lock = threading.Lock()
        self.server_slots = {}  # Server host -> semaphore limiting simultaneous lookups

    def _server_slot(self, host):
        with self.rate_limit_lock:
            if host not in self.server_slots:
                self.server_slots[host] = threading.BoundedSemaphore(self.MAX_CONCURRENT_PER_SERVER)
            return self.server_slots[host]

    def _lookup(self, url):
        """GET an RDAP record; a rate-limited request is retried once after a short wait."""
        response = http_session.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
        if response.status_code == 429:
            try:
                wait = float(response.headers.get('Retry-After', 1))
            except (TypeError, ValueError):
                wait = 1
            time.sleep(min(max(wait, 0), self.MAX_RETRY_WAIT))
            response = http_session.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
        return response

    def _record_rate_limit(self, host):
        with self.rate_limit_lock:
            self.rate_limits[host] += 1
            if self.rate_limits[host] == self.MAX_RATE_LIMITS_PER_SERVER:
                logging.warning(f"RDAP: {host} keeps rate limiting, skipping it for the rest of this run")

    def run(self, domain_status):
        domain = domain_status.domain.lower()
        tld = domain.rsplit('.', 1)[-1]
        base_url = self.servers.get(tld)

        if not base_url or tld in self.SKIP_TLDS or not domain.isascii():
            return

        host = urlsplit(base_url).netloc
        if self.rate_limits[host] >= self.MAX_RATE_LIMITS_PER_SERVER:
            return

        try:
            with self._server_slot(host):
                response = self._lookup(f"{base_url.rstrip('/')}/domain/{domain}")
            status_code = response.status_code
            data = response.json() if status_code == 200 else None
        except Exception as e:
            domain_status.add_reason('RDAP error', self.method_name)
            logging.debug(f"RDAPMethod error for {domain}: {e}")
            return

        if status_code == 404:
            domain_status.mark_no_registration_record(self.method_name)
            return

        # 403 is how a server answers once it blocks a client that kept going after 429s
        if status_code in (429, 403):
            self._record_rate_limit(host)
            domain_status.add_reason('RDAP rate limited', self.method_name)
            return

        if status_code != 200 or not isinstance(data, dict):
            domain_status.add_reason(f'RDAP error (HTTP {status_code})', self.method_name)
            return

        events = {event.get('eventAction'): event.get('eventDate')
                  for event in data.get('events') or [] if isinstance(event, dict)}
        statuses = [str(status).lower() for status in data.get('status') or []]
        in_quarantine = any(status in self.QUARANTINE_STATUSES for status in statuses)

        registration_date = _parse_event_date(events.get('registration'))
        expiration_date = _parse_event_date(events.get('expiration'))
        if in_quarantine:
            expiration_date = _parse_event_date(events.get('deletion')) or expiration_date

        if registration_date:
            domain_status.registration_date = registration_date
        if expiration_date:
            domain_status.expiration_date = expiration_date
        registrar = _registrar_name(data)
        if registrar:
            domain_status.registrar = registrar

        if in_quarantine:
            self.conclude(domain_status, 'Quarantine', 'Domain in quarantine')
        else:
            self.conclude(domain_status, False, 'Domain is registered')
