# 2ME

Domain availability checker for every TLD. It combines DNS, RDAP, WHOIS and registrar APIs and reports each domain as available, premium, in quarantine, not available or unknown, with a price where one is known.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# One domain
python 2ME.py example.com

# One name on every TLD
python 2ME.py example

# One name on selected TLDs
python 2ME.py example --tlds ".com,.net,.io"

# Several domains, or a file with one domain per line
python 2ME.py -d "example.com,example.org"
python 2ME.py -f domains.txt

# Every 3-letter name on .com
python 2ME.py --generate 3 --tlds ".com"

# Only show what can be registered
python 2ME.py example --show-status available,premium
```

Results are printed as a table and saved to `output.txt`. `output.json` holds every checked domain, including those hidden by a status filter, and keeps the domains of earlier runs.

## Options

| Option | Description |
|---|---|
| `-f`, `--file` | File with domains or names, one per line |
| `-d`, `--domains` | Comma-separated domains or names |
| `--generate N` | Generate every name of N characters (needs `--tlds`) |
| `--charset` | Characters for `--generate`: `a-z` (default), `a-z0-9` or `0-9` |
| `--max-generate` | Maximum number of generated domains (default 1000000) |
| `--tlds` | Comma-separated TLDs, a file with one TLD per line, or `*` for all (default) |
| `--max-tld-length` | Skip longer TLDs |
| `--methods` | Only use these methods |
| `--exclude-methods` | Skip these methods |
| `--show-status` | Only show these statuses |
| `--hide-status` | Hide these statuses |
| `-o`, `--output` | Output file (default `output.txt`); the JSON file is written next to it |
| `--threads` | Number of threads (default 10) |
| `--extract-whois-info` | Add registration and expiration dates of registered domains to the JSON file |
| `--skip-known-whois` | With `--extract-whois-info`: skip domains whose dates are already in the JSON file |
| `--debug` | Write debug details to `2me-debug.log` |

Statuses: `available`, `premium`, `quarantine`, `unavailable`, `unknown`.

## Methods

Methods run in this order. Each one only checks the domains that are still unknown.

| Name | Checks |
|---|---|
| `tld` | Valid name and existing TLD; adds price and restrictions |
| `dns` | A, MX and NS records |
| `rdap` | Registration record at the registry, with dates |
| `pywhois` | WHOIS |
| `vercel` | Vercel registrar API, with prices |
| `ncapi` | Namecheap API |
| `gandi` | Gandi API, with prices |
| `whoisvu` | WHOIS through whois.vu |
| `fastly` | Fastly Domain Research API (optional, needs a token) |

`whois` selects both `pywhois` and `whoisvu`.

Only `fastly` needs an account. It checks the domains the other methods left unknown, one per request, and is billed beyond Fastly's free monthly allowance. To use it, set `FASTLY_API_TOKEN` in the environment or in a `.env` file next to `2ME.py` (see `.env.example`). Without a token it is skipped.

A domain without a registration record can still be premium or reserved, so the registrar APIs decide. If none of them can, it is reported as available with the reason "No registration record".

## Data files

In `data/`:

| File | Contents |
|---|---|
| `all-tlds.txt` | TLDs used for `*` |
| `tlds.json` | Price and restrictions per TLD |
| `rdap-servers.json` | RDAP server per TLD |

## Extending

- **Method:** add `methods/<name>_method.py` with a class that inherits from `BaseMethod` (one domain per call) or `BaseBatchMethod` (a list per call). Set `priority` and `method_name` and implement `run()`.
- **TLD rule:** add `tld_rules/<tld>.py` with a function decorated with `@tld_rule(method=...)`. See `tld_rules/nl.py`.
