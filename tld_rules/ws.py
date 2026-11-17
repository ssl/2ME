"""
TLD rules for .ws domains
"""

from tld_rules import tld_rule

# Every .ws name without its own DNS gets the registry's parking page and mail server
PARKING_IP = '64.70.19.203'
PARKING_MAIL_SERVER = 'mail.hope-mail.com.'


@tld_rule(method='dns')
def ws_dns_rule(domain_status, method_name, record_type=None, answers=None, **kwargs):
    """Records pointing to the registry's parking servers say nothing about registration."""
    if not answers:
        return None
    if record_type == 'A' and getattr(answers[0], 'address', None) == PARKING_IP:
        return 'ignore'
    if record_type == 'MX' and str(getattr(answers[0], 'exchange', '')).lower() == PARKING_MAIL_SERVER:
        return 'ignore'
    return None
