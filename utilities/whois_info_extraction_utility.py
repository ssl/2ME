"""
WHOIS Info Extraction Utility for 2ME
Adds registration and expiration dates to registered domains, for output.json.
Only runs when enabled with --extract-whois-info.
"""

import concurrent.futures
import json
import logging

from core.progress_utils import create_progress_tracker
from core.whois_parsing import extract_dates_from_whois
from methods.whoisvu_method import fetch_whois_vu
from utilities import BaseUtilityMethod


class WHOISInfoExtractionUtility(BaseUtilityMethod):
    """
    Fills in missing registration and expiration dates. Reuses the WHOIS
    text a checking method already fetched, and otherwise looks the domain
    up with the whois.vu API.
    """

    priority = 100  # After the checking methods, before premium detection

    TIMEOUT = 8
    MAX_THREADS = 15

    def __init__(self, extract_whois_info=False, skip_known_whois=False,
                 json_output_file='output.json', **kwargs):
        super().__init__()
        self.extract_whois_info = extract_whois_info
        self.skip_known_whois = skip_known_whois
        self.existing_data = self._load_existing_data(json_output_file) if skip_known_whois else {}

    def should_process(self, **kwargs):
        """Only run when extract_whois_info is enabled."""
        return self.extract_whois_info

    @staticmethod
    def _load_existing_data(json_output_file):
        """Domains stored in the JSON output of earlier runs, keyed by domain name."""
        try:
            with open(json_output_file, 'r') as f:
                domains = json.load(f).get('domains')
        except FileNotFoundError:
            return {}
        except Exception as e:
            logging.warning(f"WHOIS extraction: Failed to load existing data: {e}")
            return {}

        if not isinstance(domains, dict):
            return {}
        logging.info(f"WHOIS extraction: Loaded {len(domains)} existing domain records")
        return domains

    def _has_known_dates(self, domain):
        """True when an earlier run already stored all dates this domain can have."""
        known = self.existing_data.get(domain)
        if not known or not known.get('registration_date'):
            return False
        # Active .nl domains have no expiration date
        return bool(known.get('expiration_date')) or domain.endswith('.nl')

    def _needs_lookup(self, ds):
        # Domains that can be registered now have no registration to look up
        if ds.is_available in (True, 'Premium') or ds.no_registration_record:
            return False
        if ds.registration_date and ds.expiration_date:
            return False
        return not self._has_known_dates(ds.domain)

    def _fetch_whois_text(self, domain):
        """WHOIS text for a domain from the whois.vu API, or None."""
        try:
            whois_text = fetch_whois_vu(domain, self.TIMEOUT).get('whois') or ''
        except Exception as e:
            logging.debug(f"WHOIS extraction: whois.vu failed for {domain}: {e}")
            return None
        if not whois_text or 'Incorrect Domain Name' in whois_text:
            return None
        return whois_text

    def _process(self, ds):
        if not ds.whois_text:
            ds.whois_text = self._fetch_whois_text(ds.domain)
            if not ds.whois_text:
                return

        dates = extract_dates_from_whois(ds.whois_text, ds.domain)
        ds.registration_date = ds.registration_date or dates['registration_date']
        ds.expiration_date = ds.expiration_date or dates['expiration_date']

    def run(self, domain_statuses):
        """
        Args:
            domain_statuses: List of DomainStatus objects to process
        """
        pending = [ds for ds in domain_statuses if self._needs_lookup(ds)]
        if not pending:
            logging.info("WHOIS extraction: No domains need additional WHOIS data")
            return

        logging.info(f"WHOIS extraction: Processing {len(pending)} domains")
        progress = create_progress_tracker("WHOIS extraction", len(pending))

        def process(ds):
            try:
                self._process(ds)
            except Exception as e:
                logging.error(f"WHOIS extraction error for {ds.domain}: {e}")
            finally:
                progress.advance()

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.MAX_THREADS, len(pending))) as executor:
            for _ in executor.map(process, pending):
                pass

        progress.complete()
