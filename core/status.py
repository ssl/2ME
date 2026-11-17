"""
Domain status for 2ME Domain Checker Framework
Holds the result of checking one domain and how it is displayed.
"""

import re
import threading

MAX_REASON_LENGTH = 140

# Status labels, in display/sort order. `is_available` holds one of:
#   True, 'Premium', 'Quarantine', False, or None (unknown).
STATUS_LABELS = {
    True: 'Available',
    'Premium': 'Premium',
    'Quarantine': 'Quarantine',
    False: 'Not available',
    None: 'Unknown',
}

STATUS_COLORS = {
    'Available': 'green',
    'Premium': 'blue',
    'Quarantine': 'purple',
    'Not available': 'red',
    'Unknown': 'yellow',
}

DEFAULT_REASONS = {
    True: 'Domain is available',
    'Premium': 'Domain is premium and available',
    'Quarantine': 'Domain in quarantine',
    False: 'Domain is registered',
}


def _truncate(reason):
    """Cap a reason at MAX_REASON_LENGTH characters."""
    if len(reason) > MAX_REASON_LENGTH:
        return reason[:MAX_REASON_LENGTH - 3] + "..."
    return reason


def _normalize_price(price):
    """
    Turn a price from tlds.json into a plain decimal string: "2,625.98" and
    "1.645,95" become "2625.98" and "1645.95", "12,50" becomes "12.50".
    """
    if not isinstance(price, str):
        return price

    value = price.strip()
    if ',' in value and '.' in value:
        # The separator that comes last is the decimal one
        if value.rfind(',') > value.rfind('.'):
            return value.replace('.', '').replace(',', '.')
        return value.replace(',', '')
    if re.fullmatch(r'\d{1,3}(,\d{3})+', value):
        return value.replace(',', '')  # Thousands separators only
    return value.replace(',', '.')     # Decimal comma


def _format_date(value):
    """Dates are datetimes when parsed, strings when taken over as-is."""
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


class DomainStatus:
    """Result of checking one domain. Safe to update from several threads."""

    def __init__(self, domain):
        self.domain = domain
        self.is_available = None  # True, False, 'Premium', 'Quarantine', or None (Unknown)
        self.price = "N/A"
        self.reason = ""
        self.tld_info = {}
        self.restriction_flag = False  # TLD has registration restrictions
        self.decided_by = ''  # Method that set the availability
        self.no_registration_record = False  # A registry lookup found no record of this domain
        self.no_record_source = ''  # Method that found no record
        self.registration_date = None
        self.expiration_date = None
        self.lock = threading.Lock()
        self.registrar = None
        self.whois_text = None  # Kept so WHOIS info extraction does not look it up again

    def add_reason(self, reason, method_name='', positive=False):
        """Append a reason while availability is still unknown."""
        if method_name:
            reason = f"{reason} ({method_name})"
        with self.lock:
            if self.is_available is not None:
                return  # A conclusive result keeps its own reason
            combined = f"{self.reason}; {reason}" if self.reason else reason
            self.reason = _truncate(combined)

    def set_availability(self, is_available, price=None, method_name='', custom_reason=None):
        """
        Set the availability and replace the reason.

        Uses custom_reason when given, otherwise a standard reason for the
        status. For an available domain on a restricted TLD the restriction
        is appended.
        """
        with self.lock:
            self.is_available = is_available
            self.decided_by = method_name
            if price and price not in ("N/A", "Unknown"):
                self.price = price

            if custom_reason:
                reason = custom_reason
            else:
                reason = DEFAULT_REASONS.get(is_available, 'All data was inconclusive')
                if method_name:
                    reason = f"{reason} ({method_name})"

            restrictions = self.tld_info.get('restrictions', '')
            if is_available is True and self.restriction_flag and restrictions:
                reason = f"{reason}; {restrictions}"

            self.reason = _truncate(reason)

    def mark_no_registration_record(self, method_name=''):
        """
        Note that a registry lookup (RDAP or WHOIS) found no record.

        The domain is not registered, but it can still be premium or
        reserved, so its availability is left for the registrar APIs.
        """
        with self.lock:
            if not self.no_registration_record:
                self.no_registration_record = True
                self.no_record_source = method_name

    def set_tld_info(self, tld_info):
        """Store TLD information; takes the default price and restrictions from it."""
        self.tld_info = tld_info
        restrictions = tld_info.get('restrictions', '')
        self.restriction_flag = bool(restrictions) and restrictions != 'No known restrictions'

        average_price = tld_info.get('average_price', 'N/A')
        if average_price not in ("N/A", "Unknown"):
            self.price = _normalize_price(average_price)

    def get_plain_availability(self):
        """Status label without colour codes."""
        return STATUS_LABELS.get(self.is_available, 'Unknown')

    def get_colored_availability(self):
        """Status label with ANSI colour for the terminal."""
        from core.utils import color_text  # Imported here to avoid a circular import

        label = self.get_plain_availability()
        color = STATUS_COLORS[label]
        if label == 'Available' and self.restriction_flag:
            color = 'orange'
        return color_text(label, color)

    def print_result(self, table):
        """Add this domain as a row to a PrettyTable."""
        table.add_row([self.domain, self.get_colored_availability(), self.price, self.reason])

    def get_result_line(self):
        """Line for the text output file."""
        return f"{self.domain}\t| {self.get_plain_availability()}\t| {self.price}\t| {self.reason}"

    def to_dict(self):
        """Dictionary for the JSON output file. Dates are only included when known."""
        result = {
            'domain': self.domain,
            'availability': self.get_plain_availability(),
            'price': self.price,
            'reason': self.reason,
        }
        if self.registration_date is not None:
            result['registration_date'] = _format_date(self.registration_date)
        if self.expiration_date is not None:
            result['expiration_date'] = _format_date(self.expiration_date)
        return result


def get_sort_key(ds):
    """Sort by status (available first, unknown last), then by price."""
    if ds.is_available is True:
        priority = 2 if ds.restriction_flag else 1
    elif ds.is_available == 'Premium':
        priority = 3
    elif ds.is_available == 'Quarantine':
        priority = 4
    elif ds.is_available is False:
        priority = 5
    else:
        priority = 6

    try:
        price = float(ds.price)
    except (TypeError, ValueError):
        price = float('inf')

    return (priority, price)
