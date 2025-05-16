# 2ME

2ME is a powerful domain availability checker that uses multiple methods to verify domain availability and pricing. It provides detailed information about domain status, including availability, pricing, and any restrictions. 2ME is able to get availabilty status for *all* TLDs.

![2ME Demo](https://imgur.com/TdcmX2P.gif)

## Setup

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. (Optional) Create a `.env` file in the same directory as the script with the following content:

   - `DOMAINR_API_KEY`: Your Domainr API key from RapidAPI
   - `MAX_TLD_LENGTH`: Maximum TLD length to check

   You can get a Domainr API key by signing up at [RapidAPI](https://rapidapi.com/domainr/api/domainr).

    *without this free API key, depending on the search, about 90% can still be checked.

## Usage

### Check domains from a file:
```
python 2ME.py
```
This will read domains from `checkthis.txt` and check their availability.

### Check a base domain with all TLDs:
```
python 2ME.py example
```
This will check the availability of `example.tld` for all TLDs listed in `all-tlds.txt` with length <= MAX_TLD_LENGTH.

## Output

Results are displayed in a table and also saved to `output.txt`.

## Features

- Multiple checking methods (DNS, WHOIS, API)
- Support for premium domain detection
- Price information
- Color-coded output for better readability
- Batch processing capabilities

## Methods

The tool uses multiple methods (in this order) to check domain availability fast and free:
- TLD validation
- DNS record checking
- WHOIS lookup
- Namecheap API
- Gandi API
- Domainr API

All methods are free to use, and only Domainr requires an actual API key. A free Domainr key gives 10K queries/month. Since all other methods are free and unlimited, 2ME will try to get all data with the other methods first. Domainr is only there to validate the last unique TLDs (if requested).

Example when checking a single domain for *all* TLDS;
- 1446 total queries
- 1011 validated by TLD validation/DNS records/WHOIS lookup.
- 262 validated by NCAPI
- 148 validated by Gandi API
- only 23 validated by Domainr (1.59%)