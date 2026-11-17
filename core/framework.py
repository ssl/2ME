"""
Domain Checker Framework for 2ME
Core framework that orchestrates domain checking methods and utilities.
"""

import concurrent.futures
import logging

from core.progress_utils import create_progress_tracker
from core.status import DomainStatus
from core.utils import load_tlds_dict
from methods import MethodLoader
from tld_rules import tld_rules_loader
from utilities import UtilityLoader


def _parse_names(names_arg):
    """Split a comma-separated command line value into lowercase names."""
    if not names_arg:
        return set()
    return {name.strip().lower() for name in names_arg.split(',') if name.strip()}


class DomainCheckerFramework:
    """
    Runs the selected checking methods over a list of domains.

    The methods run in priority order, per-domain and batch methods alike,
    each over the domains that are still unknown. Utilities then run over
    all domains.
    """

    def __init__(self, methods=None, exclude_methods=None, threads=10, **config):
        """
        Args:
            methods: Comma-separated method names to use (default: all)
            exclude_methods: Comma-separated method names to leave out
            threads: Number of threads for per-domain methods
            **config: Passed on to methods and utilities (for example
                fastly_api_token, extract_whois_info, skip_known_whois)
        """
        self.threads = max(1, int(threads))

        self.tlds_dict = load_tlds_dict()
        logging.info(f"Loaded {len(self.tlds_dict)} TLD definitions")

        loaded_methods = MethodLoader().load_all_methods(tlds_dict=self.tlds_dict, **config)
        self.available_methods = sorted(set().union(*(m.selection_names() for m in loaded_methods)))

        # All selected methods in the order they run (sorted by priority)
        self.pipeline = self._select_methods(loaded_methods, methods, exclude_methods)
        self.methods = [m for m in self.pipeline if not m.is_batch_method]
        self.batch_methods = [m for m in self.pipeline if m.is_batch_method]

        self.utility_methods = UtilityLoader.load_utility_methods(**config)

        # The methods apply rules through this same shared loader
        self.tld_rules_loader = tld_rules_loader
        self.tld_rules_loader.load_all_rules()

        logging.info(f"Framework initialized with {len(self.methods)} individual methods, "
                     f"{len(self.batch_methods)} batch methods, and {len(self.utility_methods)} utilities")

    def _select_methods(self, loaded_methods, methods_arg, exclude_methods_arg):
        """Apply --methods and --exclude-methods to the loaded methods."""
        include = _parse_names(methods_arg)
        exclude = _parse_names(exclude_methods_arg)

        unknown = sorted((include | exclude) - set(self.available_methods))
        if unknown:
            raise ValueError(f"Unknown method(s): {', '.join(unknown)}. "
                             f"Available: {', '.join(self.available_methods)}")

        selected = loaded_methods
        if include:
            selected = [m for m in selected if m.selection_names() & include]
        if exclude:
            selected = [m for m in selected if not m.selection_names() & exclude]
        return selected

    def check_domains(self, domains):
        """
        Check domains for availability.

        Args:
            domains: List of domain names to check

        Returns:
            list: DomainStatus objects, in the order of `domains`
        """
        domain_statuses = [DomainStatus(domain) for domain in domains]
        logging.info(f"Checking {len(domains)} domains using up to {self.threads} threads")

        for method in self.pipeline:
            pending = [ds for ds in domain_statuses if ds.is_available is None]
            if not pending:
                break
            if method.is_batch_method:
                self._run_on_list(method, pending)
            else:
                self._run_individual_method(method, pending)

        for utility in self.utility_methods:
            self._run_on_list(utility, domain_statuses)

        return domain_statuses

    def _run_individual_method(self, method, domain_statuses):
        """Run a per-domain method over the domains, using the thread pool."""
        method_label = method.__class__.__name__
        logging.debug(f"Running {method_label} (priority {method.priority}) on {len(domain_statuses)} domains")
        progress = create_progress_tracker(method_label.replace('Method', ''), len(domain_statuses))

        def run_one(domain_status):
            try:
                method.run(domain_status)
            except Exception as e:
                logging.error(f"Error in {method_label} for {domain_status.domain}: {e}")
            finally:
                progress.advance()

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.threads)
        try:
            for _ in executor.map(run_one, domain_statuses):
                pass
        except KeyboardInterrupt:
            # Drop the queued lookups so Ctrl-C does not wait for all of them
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        executor.shutdown()
        progress.complete()

    @staticmethod
    def _run_on_list(method, domain_statuses):
        """Run a batch method or utility on a list of domains."""
        if not domain_statuses:
            return
        method_label = method.__class__.__name__
        logging.debug(f"Running {method_label} on {len(domain_statuses)} domains")
        try:
            method.run(domain_statuses)
        except Exception as e:
            logging.error(f"Error in {method_label}: {e}")

    def get_loaded_methods(self):
        """Class names of the methods and utilities that are in use."""
        return {
            'individual_methods': [m.__class__.__name__ for m in self.methods],
            'batch_methods': [m.__class__.__name__ for m in self.batch_methods],
            'utility_methods': [m.__class__.__name__ for m in self.utility_methods],
        }
