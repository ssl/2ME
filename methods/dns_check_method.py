"""
DNS Check Method for 2ME Domain Checker Framework
Checks for existing DNS records to determine domain registration status.
"""

import logging

import dns.exception
import dns.resolver

from methods import BaseMethod


class DNSCheckMethod(BaseMethod):
    """
    Marks a domain as registered when it has DNS records (A, MX or NS).
    A domain without records is left for the next method: registered
    domains do not always have DNS set up.
    """

    priority = 20
    method_name = 'dns'
    aliases = ('dns_check',)

    RECORD_TYPES = ('A', 'MX', 'NS')
    QUERY_TIMEOUT = 2   # Seconds per nameserver
    QUERY_LIFETIME = 4  # Seconds per query in total

    # Public resolvers, tried in this order when one does not respond
    NAMESERVER_GROUPS = (
        ('1.1.1.1', '1.0.0.1'),                # Cloudflare
        ('8.8.8.8', '8.8.4.4'),                # Google
        ('9.9.9.9', '149.112.112.112'),        # Quad9
        ('208.67.222.222', '208.67.220.220'),  # OpenDNS
    )

    def try_dns_query(self, domain, record_type):
        """
        Query a record type, falling back to the next resolver on failure.

        Returns:
            (answers, try_other_types): answers is None when no records of
            this type were found. try_other_types is False when querying
            another record type is pointless: the name does not exist at
            all (NXDOMAIN), or every resolver failed (a broken zone fails
            for every record type, and each attempt can take seconds).
        """
        for nameservers in self.NAMESERVER_GROUPS:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = list(nameservers)
            resolver.timeout = self.QUERY_TIMEOUT
            resolver.lifetime = self.QUERY_LIFETIME

            try:
                return resolver.resolve(domain, record_type), True
            except dns.resolver.NXDOMAIN:
                return None, False
            except dns.resolver.NoAnswer:
                return None, True
            except Exception as e:
                # Timeout, SERVFAIL or a network problem: try the next resolver
                logging.debug(f"DNS {record_type} query for {domain} failed using {nameservers}: {e}")

        logging.debug(f"All DNS servers failed for {domain} {record_type} query")
        return None, False

    def run(self, domain_status):
        domain = domain_status.domain

        for record_type in self.RECORD_TYPES:
            answers, try_other_types = self.try_dns_query(domain, record_type)
            if not answers:
                if not try_other_types:
                    break
                continue

            custom_result = self.apply_tld_rules(domain_status, record_type=record_type, answers=answers)
            if custom_result == 'ignore':
                continue  # A TLD rule says this record does not count
            if custom_result is not None:
                return

            self.conclude(domain_status, False, f'{record_type} record found')
            return
