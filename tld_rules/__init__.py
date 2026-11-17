"""
TLD Rules system for 2ME Domain Checker Framework
Provides TLD-specific domain checking rules and overrides.

A rule file is named after its TLD (nl.py for .nl) and holds functions
marked with @tld_rule(method=...). The method is the name of one checking
method ('dns'), a rule group shared by several methods ('whois'), or 'all'.

A rule returns None when it does not handle the domain. Any other value
means it did, and the method stops there; the DNS method also accepts
'ignore' to skip the record it passed.
"""

import importlib
import logging
import os


class TLDRulesLoader:
    """Loads TLD-specific rules and applies them for a domain and method."""

    def __init__(self):
        self.tld_rules = {}  # TLD -> {method name or group: [rule functions]}
        self.rules_dir = os.path.dirname(os.path.abspath(__file__))

    def load_all_rules(self):
        """Load all TLD-specific rules from the tld_rules directory."""
        self.tld_rules = {}

        for filename in sorted(os.listdir(self.rules_dir)):
            if not filename.endswith('.py') or filename.startswith('__'):
                continue
            tld = filename[:-3]

            try:
                module = importlib.import_module(f'tld_rules.{tld}')
            except Exception as e:
                logging.warning(f"Error loading TLD rules for .{tld}: {e}")
                continue

            rules = {}
            for obj in vars(module).values():
                config = getattr(obj, '_tld_rule_config', None)
                if callable(obj) and config:
                    rules.setdefault(config.get('method', 'all'), []).append(obj)

            if rules:
                self.tld_rules[tld] = rules
                logging.debug(f"Loaded TLD rules for .{tld}: {sum(len(r) for r in rules.values())} rules")

    def get_tld_rules(self, tld: str, method_name: str = 'all', rule_group: str | None = None) -> list:
        """Rules for a TLD that apply to a method: its own, its group's, then the 'all' rules."""
        tld_rules = self.tld_rules.get(tld)
        if not tld_rules:
            return []

        rules = []
        for key in dict.fromkeys((method_name, rule_group, 'all')):
            if key:
                rules.extend(tld_rules.get(key, []))
        return rules

    def apply_tld_rules(self, domain_status, method_name: str, rule_group: str | None = None, **kwargs):
        """
        Apply the TLD rules for a domain and method.

        Returns the result of the first rule that handled the domain, or None
        when no rule did.
        """
        if '.' not in domain_status.domain:
            return None

        tld = domain_status.domain.rsplit('.', 1)[-1].lower()
        for rule in self.get_tld_rules(tld, method_name, rule_group):
            try:
                result = rule(domain_status, method_name, **kwargs)
            except Exception as e:
                logging.warning(f"Error applying TLD rule for .{tld} in {method_name}: {e}")
                continue
            if result is not None:
                return result

        return None


# Shared loader instance, used by the framework and by the methods
tld_rules_loader = TLDRulesLoader()


def tld_rule(method='all'):
    """Decorator to mark a function as a TLD rule for a method, a rule group, or 'all'."""
    def decorator(func):
        func._tld_rule_config = {'method': method}
        return func
    return decorator
