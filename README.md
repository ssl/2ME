# 2ME

2ME is a powerful domain availability checker that uses multiple methods to verify domain availability and pricing. It provides detailed information about domain status, including availability, pricing, and any restrictions.

## Features

- Multi-method domain availability checking
- Supports any TLDs
- Detailed domain status information including:
  - Availability status
  - Pricing information
  - Domain restrictions
  - Registration requirements
- Color-coded output for better readability
- Batch processing capabilities

## Requirements

- Python 3.x
- Required Python packages:
  - requests
  - prettytable
  - concurrent.futures
  - threading

## Installation

1. Clone the repository:
```bash
git clone https://github.com/ssl/2ME.git
cd 2ME
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

## Usage

Run the script with a prefix and find all available TLDs for that name:

```bash
python 2ME.py abc
```

(This is currently limited to only TLDs with max length of 2. See line `tlds = ... if len(line.strip())<=2]`)

Or process all domains in checkthis.txt:

```bash
python 2ME.py
```

## Output

The tool provides detailed output including:
- Domain name
- Availability status (Available, Not available, Premium, or Unknown)
- Price information
- Any restrictions or special requirements
- Detailed reason for the status

And is also written to `output.txt`

## Methods

The tool uses several methods and APIs for domain checking, prioritizing the 'cheapest' methods;

1. Checks for any records like A, NS, MX
2. Does a basic whois request and checks for register date
3. Uses hacked Namecheap API (no key)
4. Uses hacked Gandi API (no key)
5. Uses Domainr API for last left domains (free key)
