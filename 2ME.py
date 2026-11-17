#!/usr/bin/env python3
"""
2ME - Domain Checker
Checks domain availability for every TLD.

Usage:
    python 2ME.py domain.com
    python 2ME.py -f domains.txt
    python 2ME.py --generate 4 --tlds .com,.net
    python 2ME.py --generate 4 --charset a-z0-9 --tlds ".com,.net" --methods dns
    python 2ME.py example.com --exclude-methods whois
"""

import argparse
import logging
import os
import sys

from core.utils import check_required_modules

check_required_modules()

from dotenv import load_dotenv
from prettytable import PrettyTable

from core import get_sort_key
from core.framework import DomainCheckerFramework
from core.utils import (
    CHARSETS,
    generate_domains,
    get_output_paths,
    load_domains_from_file,
    normalize_domains,
    parse_status_names,
    parse_tlds,
    save_results_to_files,
    should_show_domain,
)

VERSION = '3.0'
LOG_FILE = '2me-debug.log'

# API tokens come from the environment or a .env file next to 2ME.py
load_dotenv()
FASTLY_API_TOKEN = os.getenv('FASTLY_API_TOKEN') or None

# Defaults of the command line options
THREADS = 10
MAX_GENERATE = 1000000
OUTPUT_FILE = 'output.txt'
DEFAULT_CHARSET = 'a-z'


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='2ME - domain availability checker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python 2ME.py example.com
  python 2ME.py -f domains.txt
  python 2ME.py --generate 4 --tlds .com,.net
  python 2ME.py --generate 4 --charset a-z0-9 --tlds ".com,.net" --methods dns
  python 2ME.py example.com --exclude-methods whois

Available methods: tld,dns,rdap,whois (pywhois,whoisvu),vercel,ncapi,gandi,fastly
        '''
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-f', '--file', help='File containing domains (one per line)')
    input_group.add_argument('-d', '--domains', help='Comma-separated list of domains')
    input_group.add_argument('--generate', type=int, help='Generate domains of specified length')
    input_group.add_argument('domain', nargs='?', help='Single domain to check')

    # TLD options
    parser.add_argument('--tlds', help='TLDs to use: comma-separated list, file path, or "*" for all (default)')

    # Generation options
    parser.add_argument('--charset', choices=list(CHARSETS), default=DEFAULT_CHARSET,
                        help=f'Character set for domain generation (default: {DEFAULT_CHARSET})')
    parser.add_argument('--max-generate', type=int, default=MAX_GENERATE,
                        help=f'Maximum number of domains to generate (default: {MAX_GENERATE})')

    # Method selection
    parser.add_argument('--methods',
                        help='Comma-separated list of methods to use: tld,dns,rdap,whois,vercel,ncapi,gandi,fastly')
    parser.add_argument('--exclude-methods', help='Comma-separated list of methods to exclude')

    # Status filtering
    parser.add_argument('--show-status',
                        help='Only show domains with these statuses: available,unavailable,premium,quarantine,unknown')
    parser.add_argument('--hide-status',
                        help='Hide domains with these statuses: available,unavailable,premium,quarantine,unknown')

    # Output options
    parser.add_argument('-o', '--output', default=OUTPUT_FILE, help=f'Output file (default: {OUTPUT_FILE})')
    parser.add_argument('--threads', type=int, default=THREADS, help=f'Number of threads (default: {THREADS})')

    # WHOIS info extraction
    parser.add_argument('--extract-whois-info', action='store_true',
                        help='Extract registration and expiration dates from WHOIS for registered domains')
    parser.add_argument('--skip-known-whois', action='store_true',
                        help='Skip WHOIS extraction for domains that already have complete date info '
                             'in the JSON output file (requires --extract-whois-info)')

    # Other options
    parser.add_argument('--max-tld-length', type=int,
                        help='Skip TLDs longer than this (default: no limit)')
    parser.add_argument('--debug', action='store_true', help=f'Write debug details to {LOG_FILE}')
    parser.add_argument('--version', action='version', version=f'2ME {VERSION}')

    args = parser.parse_args()

    if args.threads < 1:
        parser.error('--threads must be at least 1')
    if args.generate is not None and args.generate < 1:
        parser.error('--generate must be at least 1')
    if args.skip_known_whois and not args.extract_whois_info:
        parser.error('--skip-known-whois requires --extract-whois-info')
    if args.generate is not None and not args.tlds:
        parser.error('--generate requires --tlds')

    try:
        args.show_status = parse_status_names(args.show_status)
        args.hide_status = parse_status_names(args.hide_status)
    except ValueError as e:
        parser.error(str(e))

    return args


def setup_logging(debug=False):
    """
    Log to a file with --debug, otherwise nowhere: the console shows just
    progress and results, and each domain's reason already names its errors.
    """
    logger = logging.getLogger()
    logger.handlers.clear()

    if not debug:
        logger.addHandler(logging.NullHandler())
        return

    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)


def resolve_tlds(args):
    """TLDs selected with --tlds (all TLDs when not given), up to --max-tld-length."""
    tlds = parse_tlds(args.tlds)
    if args.max_tld_length:
        tlds = [tld for tld in tlds if len(tld) <= args.max_tld_length]
    return tlds


def expand_names(names, args):
    """Keep full domains as they are and combine names without a TLD with the selected TLDs."""
    domains = [name for name in names if '.' in name]
    base_names = [name for name in names if '.' not in name]

    if base_names:
        tlds = resolve_tlds(args)
        domains.extend(f"{name}.{tld}" for name in base_names for tld in tlds)
    return domains


def collect_domains(args):
    """Build the list of domains to check from the input arguments."""
    if args.domain:
        return expand_names([args.domain.strip()], args)
    if args.file:
        return expand_names(load_domains_from_file(args.file), args)
    if args.domains:
        return expand_names([name.strip() for name in args.domains.split(',') if name.strip()], args)
    return generate_domains(args.generate, args.charset, resolve_tlds(args), args.max_generate)


def print_results(domain_statuses):
    """Show the results as a table."""
    if not domain_statuses:
        return

    table = PrettyTable()
    table.field_names = ["Domain", "Availability", "Price (USD)", "Reason"]
    table.align = "l"
    for ds in domain_statuses:
        ds.print_result(table)
    print(f"\n{table}")


def main():
    """Main function."""
    args = parse_arguments()
    setup_logging(args.debug)

    try:
        domains = normalize_domains(collect_domains(args))
        if not domains:
            print("No domains to check.")
            sys.exit(1)

        text_file, json_file = get_output_paths(args.output)

        print(f"2ME {VERSION}")
        print(f"Checking {len(domains)} domains using up to {args.threads} threads...\n")

        framework = DomainCheckerFramework(
            methods=args.methods,
            exclude_methods=args.exclude_methods,
            threads=args.threads,
            fastly_api_token=FASTLY_API_TOKEN,
            extract_whois_info=args.extract_whois_info,
            skip_known_whois=args.skip_known_whois,
            json_output_file=json_file,
        )
        domain_statuses = framework.check_domains(domains)

        shown = [ds for ds in domain_statuses if should_show_domain(ds, args.show_status, args.hide_status)]
        shown.sort(key=get_sort_key)

        methods_info = framework.get_loaded_methods()
        save_results_to_files(shown, domain_statuses, args.output, VERSION, methods_info)
        print_results(shown)

        print(f"\nResults saved to {text_file} and {json_file}")
        print(f"Showing {len(shown)} of {len(domains)} domains")
        print(f"Used {len(methods_info['individual_methods'])} individual methods, "
              f"{len(methods_info['batch_methods'])} batch methods, and "
              f"{len(methods_info['utility_methods'])} utilities")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
