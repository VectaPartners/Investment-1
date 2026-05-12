# Competitor Catalog Scraper — Lico Cosmetics

Extracts product catalogs of 8 DTC indie beauty competitors (Cluster C, España),
classifies each product into **Sección** (Facial / Corporal / Capilar) ·
**Función** (arrugas, manchas, hidratación, acné…) · **Tipo** (sérum, crema,
limpiador…), and exports per-brand JSON + CSV plus a master CSV.

## Competitors

Freshly Cosmetics · Cocunat · Yepoda · Saigu Cosmetics · Alma Secret ·
Sibari Republic · Singuladerm · Bella Aurora

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# All competitors
python -m scraper.main

# Subset
python -m scraper.main --only freshlycosmetics.com cocunat.com

# Verbose logs + custom paths
python -m scraper.main --config competitors.yaml --out output/ -v
```

Outputs land in `output/`:

- `output/<brand>.json` — full data per brand
- `output/<brand>.csv` — flat CSV per brand
- `output/all-competitors.csv` — master file for pivot tables in Excel/Sheets

## How it works

1. **Shopify `/products.json`** is the default backend. It is a public endpoint
   exposed by Shopify storefronts; paginated (`limit=250&page=N`). Polite delay
   (1.5 s) between requests, exponential backoff on 429/503.
2. **`html_sitemap` fallback**: when a site is not on Shopify, switch the
   `backend` field in `competitors.yaml` to `html_sitemap`. It walks
   `/sitemap.xml`, fetches product pages, and extracts title + price + image
   via OpenGraph / itemprop tags.
3. **Categorizer** (`scraper/categorizer.py`) applies keyword rules over
   `title + product_type + tags + description`. Sección and Tipo are
   single-label (first match wins, with priority order); Función is
   multi-label (a serum can be both "Anti-edad" and "Luminosidad").

Edit `scraper/categorizer.py` to refine the keyword lists for your taxonomy.

## Backend per competitor

If `shopify_json` returns 0 products for a brand, the site is not on Shopify
(or has the endpoint disabled). Switch the backend in `competitors.yaml`:

```yaml
- name: Bella Aurora
  domain: bellaaurora.com
  backend: html_sitemap
```

## Throttling and etiquette

- 1.5 s pause between requests (configurable in `competitors.yaml`)
- Identifying User-Agent including a contact email (update it before running)
- 3 retries with exponential backoff on transient failures

## Cloudflare-protected sites

A few brands (e.g. Singuladerm, Bella Aurora) sit behind Cloudflare with bot
challenges. Both backends will fail with HTTP 403 on those domains. Options:

1. Skip them — they often have catalogs on Amazon / pharmacy marketplaces
   where pricing is observable through other channels.
2. Add a Playwright-based backend (not included; adds ~80 MB of browser
   binaries and operates in a grey zone of the target's ToS).
3. Use a managed scraping service (Apify, BrightData) — they handle
   anti-bot and rotate residential IPs.

## Legal note

Scraping product data is a contested area. This tool only hits **public
endpoints** (`/products.json`, `sitemap.xml`, product pages with no auth
required). It respects rate limits and sends an identifying User-Agent.
Before running at scale, check each competitor's `robots.txt` and Terms of
Service. The user assumes responsibility for compliance with applicable
law (Spain LSSI, GDPR for any personal data, Directive 96/9/EC sui generis
database rights).

## Cron / scheduled runs

Out of scope for the MVP. The CLI is idempotent — re-running overwrites the
output files. To track price/SKU history, append a date column and pipe into
a database or BigQuery on a daily cron.
