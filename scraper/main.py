"""CLI entry point: scrape competitors, classify products, write CSV + JSON.

Usage:
  python -m scraper.main                         # all competitors
  python -m scraper.main --only freshlycosmetics.com cocunat.com
  python -m scraper.main --config competitors.yaml --out output/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from scraper import backends
from scraper.categorizer import classify

FIELDS = [
    "brand", "seccion", "funcion", "tipo", "title", "product_type", "tags",
    "price", "currency", "available", "sku", "url", "image_url", "description",
]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def scrape_one(competitor: dict[str, Any], http_cfg: dict[str, Any]) -> Iterator[dict[str, Any]]:
    backend_name = competitor.get("backend", "shopify_json")
    backend_fn = getattr(backends, backend_name, None)
    if backend_fn is None:
        raise ValueError(f"unknown backend: {backend_name}")
    backend_kwargs: dict[str, Any] = {
        "brand": competitor["name"],
        "domain": competitor["domain"],
        "user_agent": http_cfg["user_agent"],
        "delay": http_cfg["delay_seconds"],
        "timeout": http_cfg["timeout_seconds"],
    }
    if competitor.get("products_url"):
        backend_kwargs["products_url"] = competitor["products_url"]
    raw = backend_fn(**backend_kwargs)
    for product in raw:
        cls = classify(
            title=product.get("title", ""),
            product_type=product.get("product_type", ""),
            tags=product.get("tags", ""),
            description=product.get("description", ""),
        )
        product["seccion"] = cls.seccion
        product["funcion"] = "; ".join(cls.funcion)
        product["tipo"] = cls.tipo
        yield product


def write_outputs(brand: str, products: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = brand.lower().replace(" ", "-")
    json_path = out_dir / f"{slug}.json"
    json_path.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = out_dir / f"{slug}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)


def write_master(all_products: list[dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out_dir / "all-competitors.csv"
    with master.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_products)
    return master


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape competitor product catalogs.")
    p.add_argument("--config", default="competitors.yaml", type=Path)
    p.add_argument("--out", default="output", type=Path)
    p.add_argument("--only", nargs="*", help="Limit to these domains")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config(args.config)
    competitors = cfg["competitors"]
    if args.only:
        competitors = [c for c in competitors if c["domain"] in args.only]
        if not competitors:
            logging.error("no competitors matched --only %s", args.only)
            return 1

    all_products: list[dict[str, Any]] = []
    summary: list[tuple[str, int]] = []
    for c in competitors:
        logging.info("== %s (%s, backend=%s) ==", c["name"], c["domain"], c.get("backend"))
        try:
            products = list(scrape_one(c, cfg["http"]))
        except Exception as e:
            logging.exception("failed scraping %s: %s", c["name"], e)
            summary.append((c["name"], 0))
            continue
        write_outputs(c["name"], products, args.out)
        all_products.extend(products)
        summary.append((c["name"], len(products)))

    master = write_master(all_products, args.out)
    logging.info("wrote %s with %d rows", master, len(all_products))
    print("\nSummary:")
    for name, n in summary:
        print(f"  {name:25s} {n:>5d} products")
    return 0


if __name__ == "__main__":
    sys.exit(main())
