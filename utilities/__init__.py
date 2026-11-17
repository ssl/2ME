"""
Utilities Module for 2ME
Utilities run after the domain checking methods, on all domains.

Every file in this directory ending in _utility.py is loaded automatically.
"""

import importlib
import inspect
import logging
import os


class BaseUtilityMethod:
    """Base class for utilities that process domains after checking."""

    priority = 999  # Lower numbers run first

    def __init__(self, **kwargs):
        pass

    def should_process(self, **kwargs):
        """Whether this utility should run with the given configuration."""
        return True

    def run(self, domain_statuses):
        """Process the list of DomainStatus objects."""
        raise NotImplementedError("Subclasses must implement run method")


class UtilityLoader:
    """Finds the utility classes in this directory and instantiates them."""

    @staticmethod
    def load_utility_methods(**kwargs):
        """
        Load the utilities that should run for this configuration.

        Returns:
            list: Utility instances sorted by priority (lower numbers first)
        """
        utilities = []
        utilities_dir = os.path.dirname(os.path.abspath(__file__))

        for filename in sorted(os.listdir(utilities_dir)):
            if not filename.endswith('_utility.py'):
                continue
            module_name = f'utilities.{filename[:-3]}'

            try:
                module = importlib.import_module(module_name)
                for name, cls in inspect.getmembers(module, inspect.isclass):
                    if issubclass(cls, BaseUtilityMethod) and cls.__module__ == module_name:
                        instance = cls(**kwargs)
                        if instance.should_process(**kwargs):
                            utilities.append(instance)
                            logging.debug(f"Loaded utility: {name} (priority: {instance.priority})")
            except Exception as e:
                logging.warning(f"Failed to load utility {module_name}: {e}")

        utilities.sort(key=lambda utility: utility.priority)
        return utilities
