"""Backends that emit a normalized product stream from a competitor domain.

Each backend yields dicts with keys:
  brand, title, url, price, currency, sku, available, vendor,
  product_type, tags, description, image_url
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from typing import Any

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    pass


def _session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
    })
    return s


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((requests.RequestException, ScrapeError)),
)
def _get(session: requests.Session, url: str, timeout: int) -> requests.Response:
    r = session.get(url, timeout=timeout)
    if r.status_code in (429, 503):
        raise ScrapeError(f"rate-limited {r.status_code} on {url}")
    r.raise_for_status()
    return r


def shopify_json(
    brand: str,
    domain: str,
    user_agent: str,
    delay: float,
    timeout: int,
) -> Iterator[dict[str, Any]]:
    session = _session(user_agent)
    page = 1
    seen = 0
    while True:
        url = f"https://{domain}/products.json?limit=250&page={page}"
        log.info("GET %s", url)
        try:
            r = _get(session, url, timeout)
        except requests.RequestException as e:
            log.warning("%s page %d failed: %s", domain, page, e)
            break
        data = r.json()
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            variant = (p.get("variants") or [{}])[0]
            image = (p.get("images") or [{}])[0]
            yield {
                "brand": brand,
                "title": p.get("title", ""),
                "url": f"https://{domain}/products/{p.get('handle', '')}",
                "price": variant.get("price"),
                "currency": "EUR",
                "sku": variant.get("sku"),
                "available": variant.get("available"),
                "vendor": p.get("vendor"),
                "product_type": p.get("product_type", ""),
                "tags": ", ".join(p.get("tags", []) if isinstance(p.get("tags"), list) else [p.get("tags", "")]),
                "description": BeautifulSoup(p.get("body_html") or "", "lxml").get_text(" ", strip=True)[:2000],
                "image_url": image.get("src", ""),
            }
            seen += 1
        page += 1
        time.sleep(delay)
        if len(products) < 250:
            break
    log.info("%s: %d products collected", brand, seen)


_PRICE_RE = re.compile(r"(\d{1,4}[\.,]\d{2})\s*€|€\s*(\d{1,4}[\.,]\d{2})")


def _extract_price(soup: BeautifulSoup) -> str | None:
    meta = soup.find("meta", attrs={"property": "product:price:amount"}) or soup.find(
        "meta", attrs={"itemprop": "price"}
    )
    if meta and meta.get("content"):
        return meta["content"].strip()
    text = soup.get_text(" ", strip=True)
    m = _PRICE_RE.search(text)
    if m:
        return (m.group(1) or m.group(2)).replace(",", ".")
    return None


def html_sitemap(
    brand: str,
    domain: str,
    user_agent: str,
    delay: float,
    timeout: int,
    product_url_pattern: str = "/product",
) -> Iterator[dict[str, Any]]:
    session = _session(user_agent)
    sitemap_url = f"https://{domain}/sitemap.xml"
    try:
        r = _get(session, sitemap_url, timeout)
    except requests.RequestException as e:
        log.error("%s sitemap failed: %s", brand, e)
        return
    soup = BeautifulSoup(r.content, "xml")
    locs = [loc.text.strip() for loc in soup.find_all("loc")]

    # Walk nested sitemaps once.
    product_urls: list[str] = []
    for loc in locs:
        if loc.endswith(".xml"):
            try:
                rr = _get(session, loc, timeout)
            except requests.RequestException:
                continue
            sub = BeautifulSoup(rr.content, "xml")
            product_urls.extend(s.text.strip() for s in sub.find_all("loc"))
            time.sleep(delay)
        elif product_url_pattern in loc:
            product_urls.append(loc)
    product_urls = [u for u in product_urls if product_url_pattern in u]
    log.info("%s: %d candidate product URLs", brand, len(product_urls))

    for url in product_urls:
        try:
            r = _get(session, url, timeout)
        except requests.RequestException as e:
            log.warning("skip %s: %s", url, e)
            time.sleep(delay)
            continue
        page = BeautifulSoup(r.content, "lxml")
        title_tag = page.find("h1") or page.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        og_image = page.find("meta", attrs={"property": "og:image"})
        desc_tag = page.find("meta", attrs={"name": "description"}) or page.find(
            "meta", attrs={"property": "og:description"}
        )
        yield {
            "brand": brand,
            "title": title,
            "url": url,
            "price": _extract_price(page),
            "currency": "EUR",
            "sku": None,
            "available": None,
            "vendor": brand,
            "product_type": "",
            "tags": "",
            "description": (desc_tag.get("content", "") if desc_tag else "")[:2000],
            "image_url": og_image.get("content", "") if og_image else "",
        }
        time.sleep(delay)
