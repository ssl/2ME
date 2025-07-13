# 2ME

2ME is a powerful domain availability checker that uses multiple methods to verify domain availability and pricing. It provides detailed information about domain status, including availability, pricing, and any restrictions. 2ME is able to get availabilty status for *all* TLDs.

## Setup

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. (Optional) Create a `.env` file in the same directory as the script with config:

   - `DOMAINR_API_KEY`: Your Domainr API key from RapidAPI

   You can get a Domainr API key by signing up at [RapidAPI](https://rapidapi.com/domainr/api/domainr).

   #### Or via parameters

- `--domainr-api-key` - Domainr API key

    *without this free API key, depending on the search, about 90% can still be checked.

## Usage

### Basic Usage

```bash
# Check single domain
python 2ME.py example.com

# Check domains from file
python 2ME.py -f domains.txt

# Check comma-separated domains
python 2ME.py -d "example.com,test.org,mydomain.net"

# Adjust thread count
python 2ME.py -f domains.txt --threads 50
```

### Domain Generation

```bash
# Generate 3-character domains with all TLDs
python 2ME.py --generate 3 --charset a-z

# Generate 4-character alphanumeric domains with specific TLDs
python 2ME.py --generate 4 --charset a-z0-9 --tlds ".com,.net,.org"

# Generate numeric domains
python 2ME.py --generate 5 --charset 0-9 --max-generate 100
```

### TLD Configuration

```bash
# Use specific TLDs (comma-separated)
python 2ME.py example --tlds ".com,.net,.org,.io"

# Use TLDs from file
python 2ME.py example --tlds-file my-tlds.txt

# Use all TLDs (default)
python 2ME.py example --tlds "*"
```

### Method Selection

```bash
# Use only specific methods
python 2ME.py example.com --methods tld,dns,whois

# Exclude specific methods
python 2ME.py example.com --exclude-methods whois,ncapi

# Available methods: tld, dns, whois, ncapi, gandi, domainr
```

### Status Filtering

```bash
# Show only available domains
python 2ME.py -f domains.txt --show-status available

# Hide unavailable and premium domains
python 2ME.py -f domains.txt --hide-status unavailable,premium

# Show only premium domains
python 2ME.py -f domains.txt --show-status premium
```

### Output Options

```bash
# Specify output file
python 2ME.py -f domains.txt -o results.txt
```

## Verification Methods

### Per-Domain Methods
1. **TLD Check** (`tld`) - Validates TLD format and retrieves pricing info
2. **DNS Check** (`dns`) - Checks for DNS records (A, MX, NS)
3. **WHOIS Check** (`whois`) - Queries WHOIS database
4. **NCAPI Check** (`ncapi`) - Namecheap API batch checking
5. **Gandi API Check** (`gandi`) - Gandi registrar API
6. **Domainr API Check** (`domainr`) - Domainr API (requires API key)

All methods are free to use, and only Domainr requires an actual API key. A free Domainr key gives 10K queries/month. Since all other methods are free and unlimited, 2ME will try to get all data with the other methods first. Domainr is only there to validate the last unique TLDs (if requested).

Example when checking a single domain for *all* TLDS;
- 1446 total queries
- 1011 validated by TLD validation/DNS records/WHOIS lookup.
- 262 validated by NCAPI
- 148 validated by Gandi API
- only 23 validated by Domainr (1.59%)