"""
WHOIS text parsing for 2ME Domain Checker Framework
Shared by the WHOIS methods, the WHOIS info extraction utility and TLD rules,
so availability keywords and date formats are defined in one place.
"""

import logging
import re
from datetime import datetime

QUARANTINE_KEYWORDS = ('quarantine', 'pending delete')

# Phrases that state outright that the name can be registered
AVAILABLE_PHRASES = (
    'available for purchase', 'domain is available for registration',
    'status: available', 'available for registration',
)

# Generic "no such record" phrases. These also occur in the boilerplate of
# registered domains, so they only count when no registration data was found.
NOT_FOUND_PHRASES = (
    'not found', 'no match', 'no entries found', 'not registered',
    'does not exist', 'no object found', 'no data found',
)

REGISTRATION_KEYWORDS = (
    'creation date:', 'created:', 'registered:', 'registration date:',
    'domain name:', 'registrar:', 'registrant:', 'admin contact:',
    'expiry date:', 'expires:', 'expiration date:',
)

# Phrases saying the name itself cannot be registered. Single words such as
# "prohibited" or "reserved" also occur in every registry's terms of use
# ("all rights reserved"), so only phrases about the name count.
RESERVED_PHRASES = (
    'is reserved', 'has been reserved', 'reserved name', 'reserved domain', 'reserved by',
    'status: reserved',
    'domain is restricted', 'name is restricted', 'restricted name', 'restricted domain',
    'domain is blocked', 'name is blocked', 'blocked name', 'blocked domain',
    'domain is not allowed', 'name is not allowed', 'cannot be registered',
    'prohibited string', 'not available for registration',
)

PREMIUM_KEYWORDS = (
    'premium domain is available', 'this premium domain', 'premium domain',
    'contact premium@', 'premium@', 'premium price', 'premium pricing',
    'high value domain', 'special pricing', 'premium registration',
    'premium fee', 'premium cost',
)
PREMIUM_AVAILABILITY_KEYWORDS = ('available', 'purchase', 'registration', 'register')

# Phrases in the reply python-whois raises as an error for unregistered names
NOT_REGISTERED_REPLY_PHRASES = (
    'no match for', 'not found', 'no data found', 'data not found', 'is free',
    'does not exist', 'no object found',
    'available for purchase', 'domain is available for registration',
    'status: available',
)

REGISTRATION_DATE_PATTERNS = (
    r'(?:created|creation|registered|registration)(?:\s+date)?[:\s]+([^\n\r]+)',
    r'domain name commencement date[:\s]+([^\n\r]+)',
    r'created on[:\s]+([^\n\r]+)',
)

EXPIRATION_DATE_PATTERNS = (
    r'(?:expir\w*|renewal)(?:\s+date)?[:\s]+([^\n\r]+)',
    r'paid-till[:\s]+([^\n\r]+)',
    r'expires on[:\s]+([^\n\r]+)',
)

DATE_FORMATS = (
    '%Y-%m-%d',            # 2024-01-15
    '%d-%m-%Y',            # 15-01-2024
    '%m-%d-%Y',            # 01-15-2024
    '%Y/%m/%d',            # 2024/01/15
    '%d/%m/%Y',            # 15/01/2024
    '%m/%d/%Y',            # 01/15/2024
    '%Y.%m.%d',            # 2024.01.15
    '%d.%m.%Y',            # 15.01.2024
    '%d-%b-%Y',            # 15-Jan-2024
    '%b %d %Y',            # Jan 15 2024
    '%B %d %Y',            # January 15 2024
    '%Y-%m-%dT%H:%M:%SZ',  # 2024-01-15T10:00:00Z
    '%Y-%m-%d %H:%M:%S',   # 2024-01-15 10:00:00
)

_QUARANTINE_END_RE = re.compile(
    r'date out of quarantine:\s*(\d{4}-\d{2}-\d{2})(?:t(\d{2}:\d{2}:\d{2}))?',
    re.IGNORECASE
)
_LEADING_ISO_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def _is_premium_offer(text_lower):
    return (_contains_any(text_lower, PREMIUM_KEYWORDS)
            and _contains_any(text_lower, PREMIUM_AVAILABILITY_KEYWORDS))


def is_quarantine_text(whois_text):
    """True when the WHOIS text says the domain is in quarantine or pending delete."""
    return _contains_any(whois_text.lower(), QUARANTINE_KEYWORDS)


def classify_whois_text(whois_text, has_registration_data=False):
    """
    Determine availability from the WHOIS text of a successful lookup.

    Args:
        whois_text: Raw WHOIS text
        has_registration_data: True when a creation date or registrar was
            parsed from the record, which rules out a "not found" reply

    Returns:
        (status, reason) or None when the text is inconclusive. Status is
        True, False, 'Premium' or 'Quarantine'.
    """
    text_lower = whois_text.lower()

    if _contains_any(text_lower, QUARANTINE_KEYWORDS):
        return 'Quarantine', 'Domain in quarantine'

    # "not available for registration" contains an availability phrase
    if _contains_any(text_lower, AVAILABLE_PHRASES) and 'not available' not in text_lower:
        return True, 'Available keyword found'

    if not has_registration_data and _contains_any(text_lower, NOT_FOUND_PHRASES):
        return True, 'Available keyword found'

    # Before the registration keywords: a reply about a reserved name often
    # echoes "Domain Name:" too
    if _contains_any(text_lower, RESERVED_PHRASES):
        return False, 'Domain is reserved or restricted'

    # Before the registration keywords too: a premium offer can echo
    # "Domain Name:". Only without registration data, as registrar
    # boilerplate of registered domains can mention premium domains.
    if not has_registration_data and _is_premium_offer(text_lower):
        return 'Premium', 'Domain is premium and available'

    if _contains_any(text_lower, REGISTRATION_KEYWORDS):
        return False, 'Registration keyword found'

    return None


def classify_not_registered_reply(message):
    """
    Determine availability from the reply python-whois raises as an error
    when a registry reports that a name is not registered.

    Returns:
        (status, reason) or None when the message is some other error.
    """
    message_lower = message.lower()

    if _is_premium_offer(message_lower):
        return 'Premium', 'Domain is premium and available'

    if _contains_any(message_lower, NOT_REGISTERED_REPLY_PHRASES):
        return True, 'Domain is available'

    return None


def parse_quarantine_end_date(whois_text):
    """Return the 'Date out of quarantine' value as a datetime, or None."""
    match = _QUARANTINE_END_RE.search(whois_text)
    if not match:
        return None
    try:
        if match.group(2):
            return datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}")
        return datetime.strptime(match.group(1), '%Y-%m-%d')
    except ValueError:
        return None


def parse_date_string(date_str):
    """
    Parse the date at the start of a WHOIS field value.

    Returns:
        datetime at midnight of that date, or None when no date is recognised.
    """
    if not date_str:
        return None

    value = ' '.join(date_str.replace(',', ' ').split())
    if not value:
        return None

    candidates = [value, value.split()[0]]
    iso_match = _LEADING_ISO_DATE_RE.match(value)
    if iso_match:
        candidates.append(iso_match.group(0))

    for candidate in candidates:
        for date_format in DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, date_format)
            except ValueError:
                continue
            return datetime(parsed.year, parsed.month, parsed.day)

    logging.debug(f"Could not parse date string: {date_str}")
    return None


def _first_date(whois_text, patterns):
    """First value that parses as a date among all matches of the patterns."""
    for pattern in patterns:
        for match in re.finditer(pattern, whois_text, re.IGNORECASE):
            parsed = parse_date_string(match.group(1))
            if parsed:
                return parsed
    return None


def extract_dates_from_whois(whois_text, domain=None):
    """
    Extract registration and expiration dates from WHOIS text.

    Active .nl domains have no expiration date; for .nl the expiration date
    is the end of the quarantine period, and only set while in quarantine.

    Returns:
        dict with 'registration_date' and 'expiration_date' (datetime or None)
    """
    dates = {'registration_date': None, 'expiration_date': None}
    if not whois_text:
        return dates

    dates['registration_date'] = _first_date(whois_text, REGISTRATION_DATE_PATTERNS)

    if domain and domain.lower().endswith('.nl'):
        if is_quarantine_text(whois_text):
            dates['expiration_date'] = (parse_quarantine_end_date(whois_text)
                                        or _first_date(whois_text, EXPIRATION_DATE_PATTERNS))
    else:
        dates['expiration_date'] = _first_date(whois_text, EXPIRATION_DATE_PATTERNS)

    return dates
