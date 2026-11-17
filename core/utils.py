"""
Utility functions for 2ME Domain Checker Framework
Input loading, domain generation, result filtering and output files.
"""

import itertools
import json
import os
import sys

# Data files that ship with 2ME, found wherever 2ME.py is run from.
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
TLDS_JSON_FILE = os.path.join(DATA_DIR, 'tlds.json')
ALL_TLDS_FILE = os.path.join(DATA_DIR, 'all-tlds.txt')
RDAP_SERVERS_FILE = os.path.join(DATA_DIR, 'rdap-servers.json')

CHARSETS = {
    'a-z': 'abcdefghijklmnopqrstuvwxyz',
    'a-z0-9': 'abcdefghijklmnopqrstuvwxyz0123456789',
    '0-9': '0123456789',
}

# Plain status label (lowercase) -> name used by --show-status / --hide-status
STATUS_FILTER_NAMES = {
    'available': 'available',
    'not available': 'unavailable',
    'premium': 'premium',
    'quarantine': 'quarantine',
    'unknown': 'unknown',
}

REQUIRED_MODULES = [
    ('dns.resolver', 'dnspython'),
    ('whois', 'python-whois'),
    ('requests', 'requests'),
    ('prettytable', 'prettytable'),
    ('dotenv', 'python-dotenv'),
]

ANSI_COLORS = {
    'green': '\033[92m',
    'red': '\033[91m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'orange': '\033[33m',
    'purple': '\033[35m',
    'bold': '\033[1m',
    'reset': '\033[0m',
}


def color_text(text, color):
    """Colour text using ANSI codes."""
    return f"{ANSI_COLORS.get(color, '')}{text}{ANSI_COLORS['reset']}"


def _read_lines(file_path):
    """Non-empty, stripped lines of a file. Exits when the file is missing."""
    if not os.path.isfile(file_path):
        print(f"File '{file_path}' not found.")
        sys.exit(1)
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def load_domains_from_file(file_path):
    """Load domains from a file, one per line."""
    return _read_lines(file_path)


def load_tlds_from_file(file_path):
    """Load TLDs from a file, one per line. A leading dot is optional."""
    return [line.lstrip('.').lower() for line in _read_lines(file_path)]


def load_tlds_dict(tlds_file=TLDS_JSON_FILE):
    """Load the TLD definitions as a dictionary keyed by TLD name."""
    if not os.path.isfile(tlds_file):
        raise FileNotFoundError(f"TLD definitions file '{tlds_file}' not found.")
    with open(tlds_file, 'r') as f:
        return {tld['name']: tld for tld in json.load(f)}


def parse_tlds(tlds_arg):
    """Parse the --tlds argument: empty or "*" for all TLDs, a file path, or a comma-separated list."""
    if not tlds_arg or tlds_arg == '*':
        return load_tlds_from_file(ALL_TLDS_FILE)
    if os.path.isfile(tlds_arg):
        return load_tlds_from_file(tlds_arg)
    return [tld.strip().lstrip('.').lower() for tld in tlds_arg.split(',') if tld.strip()]


def _to_ascii(domain):
    """Punycode for internationalised names ("café.nl" -> "xn--caf-dma.nl")."""
    try:
        return domain.encode('idna').decode('ascii')
    except UnicodeError:
        return domain  # Rejected later as an invalid name


def normalize_domains(domains):
    """Lowercase, strip, punycode and de-duplicate domains, keeping their order."""
    cleaned = (_to_ascii(domain.strip().lower().rstrip('.')) for domain in domains)
    return list(dict.fromkeys(domain for domain in cleaned if domain))


def generate_domains(length, charset, tlds, max_generate):
    """Generate every name of `length` characters combined with each TLD, up to max_generate domains."""
    if charset not in CHARSETS:
        raise ValueError(f"Unknown charset: {charset}")

    names = (''.join(chars) for chars in itertools.product(CHARSETS[charset], repeat=length))
    combinations = (f"{name}.{tld}" for name in names for tld in tlds)
    return list(itertools.islice(combinations, max_generate))


def parse_status_names(names_arg):
    """
    Statuses named in --show-status / --hide-status, as a set.

    Raises:
        ValueError: for a name that is not a status
    """
    names = {name.strip().lower() for name in (names_arg or '').split(',') if name.strip()}
    unknown = names - set(STATUS_FILTER_NAMES.values())
    if unknown:
        raise ValueError(f"unknown status: {', '.join(sorted(unknown))} "
                         f"(choose from {', '.join(STATUS_FILTER_NAMES.values())})")
    return names


def should_show_domain(domain_status, show_statuses, hide_statuses):
    """Apply the --show-status / --hide-status filters (sets of status names) to one domain."""
    status = STATUS_FILTER_NAMES[domain_status.get_plain_availability().lower()]
    if show_statuses and status not in show_statuses:
        return False
    return status not in hide_statuses


def get_output_paths(output_file):
    """
    Return (text_file, json_file) for the -o argument. Results are written
    in both formats: "results.txt" pairs with "results.json", and the other
    way round when a .json name is given.
    """
    root, extension = os.path.splitext(output_file)
    if extension.lower() == '.json':
        return root + '.txt', output_file
    if extension.lower() == '.txt':
        return output_file, root + '.json'
    return output_file, output_file + '.json'


def _load_existing_domains(json_file):
    """Domains stored by earlier runs, keyed by domain name."""
    try:
        with open(json_file, 'r') as f:
            domains = json.load(f).get('domains')
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return {}

    return domains if isinstance(domains, dict) else {}


def save_results_to_files(shown_statuses, checked_statuses, output_file, version, methods_info):
    """
    Write the shown results to the text file, and merge all checked domains
    into the JSON file, which keeps the domains of earlier runs.

    Registration and expiration dates found earlier are kept when this run
    found none, unless the domain has since become available.
    """
    text_file, json_file = get_output_paths(output_file)

    with open(text_file, 'w') as f:
        for ds in shown_statuses:
            f.write(f"{ds.get_result_line()}\n")

    domains = _load_existing_domains(json_file)
    for ds in checked_statuses:
        entry = ds.to_dict()
        previous = domains.get(ds.domain)
        if previous:
            became_available = (
                str(previous.get('availability', '')).lower() in ('quarantine', 'not available')
                and entry['availability'].lower() in ('available', 'premium')
            )
            if not became_available:
                for field in ('registration_date', 'expiration_date'):
                    if field in previous and field not in entry:
                        entry[field] = previous[field]
        domains[ds.domain] = entry

    json_data = {
        'metadata': {
            'version': version,
            'total_domains': len(domains),
            'methods_used': methods_info,
        },
        'domains': domains,
    }
    with open(json_file, 'w') as f:
        json.dump(json_data, f, indent=2, default=str)

    return json_file


def check_required_modules():
    """Exit with install instructions when a required Python module is missing."""
    missing = []
    for module_name, pip_name in REQUIRED_MODULES:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print("Missing required modules:")
        for pip_name in missing:
            print(f"  - {pip_name}")
        print("\nInstall them with:")
        print(f"pip install {' '.join(missing)}")
        sys.exit(1)
