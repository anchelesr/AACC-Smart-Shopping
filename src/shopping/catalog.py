"""Catalog Query: current offers and comparable alternatives (read only)."""
from __future__ import annotations

import sqlite3
from typing import Optional

from .advice import Constraints


def current_offers(db: sqlite3.Connection, laptop_id: str) -> list[dict]:
    """The latest observation of each retailer (comparable offers; the demonstration data is all in EUR)."""
    rows = db.execute("""
        SELECT o.retailer, o.price, o.observed_at FROM observations o
        WHERE o.laptop_id = ? AND o.observed_at = (SELECT MAX(observed_at) FROM observations
                                                   WHERE laptop_id = o.laptop_id AND retailer = o.retailer)
        ORDER BY o.price, o.retailer""", (laptop_id,)).fetchall()
    return [{"retailer": r, "price": p, "observed_at": t} for r, p, t in rows]


def lowest_offer(db: sqlite3.Connection, laptop_id: str) -> Optional[dict]:
    offers = current_offers(db, laptop_id)
    return offers[0] if offers else None


def find_alternatives(db: sqlite3.Connection, constraints: Constraints, exclude_laptop: str, limit: int = 3) -> list[dict]:
    """Other laptops whose lowest current offer fits the budget (and a preferred brand if given), cheapest first."""
    out = []
    for laptop_id, brand, model in db.execute("SELECT laptop_id, brand, model FROM products WHERE laptop_id <> ? ORDER BY laptop_id", (exclude_laptop,)):
        if constraints.preferred_brands and (brand or "").lower() not in {b.lower() for b in constraints.preferred_brands}:
            continue
        offer = lowest_offer(db, laptop_id)
        if offer is None or (constraints.budget is not None and offer["price"] > constraints.budget):
            continue
        out.append({"laptop_id": laptop_id, "brand": brand, "model": model, **offer})
    out.sort(key=lambda a: (a["price"], a["laptop_id"]))
    return out[:limit]
