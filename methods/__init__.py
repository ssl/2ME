"""
Methods system for 2ME Domain Checker Framework
Base classes for domain checking methods and the loader that finds them.

Every file in this directory ending in _method.py is loaded automatically.
"""

import importlib
import inspect
import logging
import os

from tld_rules import tld_rules_loader

RATE_LIMIT_PHRASES = ('rate limit', 'too many requests', 'throttled')


def is_rate_limit_error(error) -> bool:
    """True when an exception message points at rate limiting."""
    message = str(error).lower()
    return any(phrase in message for phrase in RATE_LIMIT_PHRASES)


def chunked(items: list, size: int):
    """Yield consecutive slices of `items` with at most `size` elements."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


class BaseMethod:
    """
    Base class for all domain checking methods.

    A method sets the availability of the domains it can judge and leaves
    the others unknown; the next method only sees the unknown ones.

    Class attributes:
        priority: Lower numbers run first
        enabled: Set to False to keep the method from being loaded
        method_name: Short name shown in reasons and used by --methods
        aliases: Other names --methods / --exclude-methods accept for it
        rule_group: Name of a TLD rule group this method shares with others
    """

    priority = 999
    enabled = True
    is_batch_method = False
    method_name = ''
    aliases = ()
    rule_group = None

    def __init__(self):
        if not self.method_name:
            self.method_name = self.__class__.__name__.lower().replace('method', '')

    def run(self, domain_status):
        """Check one domain. Must be implemented by subclasses."""
        raise NotImplementedError("Method must implement run()")

    def selection_names(self) -> set:
        """Names that select this method on the command line."""
        return {self.method_name, *self.aliases}

    def format_reason(self, base_reason: str) -> str:
        """Format a reason as "reason (method)"."""
        return f"{base_reason} ({self.method_name})"

    def conclude(self, domain_status, status, reason, price=None):
        """Set the availability with this method's reason."""
        domain_status.set_availability(status, price=price, method_name=self.method_name,
                                       custom_reason=self.format_reason(reason))

    def settle(self, domain_status, status, reason):
        """
        Conclude a registry lookup (RDAP or WHOIS), except when it only shows
        that the name is not registered: such a name can still be premium or
        reserved, which the registrar APIs know and the registry lookup does
        not. It stays unknown and is marked as having no registration record.
        """
        if status is True:
            domain_status.mark_no_registration_record(self.method_name)
        else:
            self.conclude(domain_status, status, reason)

    def apply_tld_rules(self, domain_status, **kwargs):
        """
        Apply the TLD rules registered for this method or its rule group.

        Returns the rule's result, or None when no rule handled the domain.
        """
        return tld_rules_loader.apply_tld_rules(
            domain_status, self.method_name, rule_group=self.rule_group, **kwargs
        )


class BaseBatchMethod(BaseMethod):
    """Base class for methods that check a list of domains in one go."""

    is_batch_method = True

    def run(self, domain_statuses):
        """Check a list of domains. Must be implemented by subclasses."""
        raise NotImplementedError("Batch method must implement run() with list parameter")


class MethodLoader:
    """Finds the method classes in this directory and instantiates them."""

    methods_dir = os.path.dirname(os.path.abspath(__file__))

    def load_all_methods(self, **config) -> list[BaseMethod]:
        """
        Load all methods from the methods directory, sorted by priority.

        Each method receives the configuration values its constructor asks
        for by name (for example tlds_dict).
        """
        methods = []

        for filename in sorted(os.listdir(self.methods_dir)):
            if not filename.endswith('_method.py'):
                continue
            module_name = f'methods.{filename[:-3]}'

            try:
                module = importlib.import_module(module_name)
                for name, cls in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(cls, BaseMethod) and cls.__module__ == module_name
                            and cls.enabled):
                        instance = self._instantiate(cls, config)
                        methods.append(instance)
                        logging.debug(f"Loaded method: {name} (priority: {instance.priority}, "
                                      f"batch: {instance.is_batch_method})")
            except Exception as e:
                logging.warning(f"Error loading method {module_name}: {e}")

        methods.sort(key=lambda method: method.priority)
        return methods

    @staticmethod
    def _instantiate(cls, config: dict):
        """Create a method, passing only the configuration its constructor accepts."""
        parameters = inspect.signature(cls.__init__).parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            return cls(**config)
        return cls(**{key: value for key, value in config.items() if key in parameters})
