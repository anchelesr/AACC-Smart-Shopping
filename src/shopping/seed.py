"""Deterministic synthetic price history for demonstrations and tests. NOT real market data: prices are generated
from a seeded random walk per laptop and retailer, with one planned dip and one planned rise."""
from __future__ import annotations

import csv
import io
import random
from datetime import datetime, timedelta, timezone

LAPTOPS = [
    ("lap-001", "Acme", "AirBook 14", 899.0), ("lap-002", "Acme", "ProBook 16", 1349.0),
    ("lap-003", "Beta", "Slim 13", 749.0), ("lap-004", "Beta", "Creator 15", 1599.0),
    ("lap-005", "Gamma", "Student 14", 499.0), ("lap-006", "Gamma", "Work 15", 649.0),
]
RETAILERS = ["shop-a", "shop-b", "shop-c"]


def synthetic_csv(now: datetime, days: int = 35, seed: int = 11) -> str:
    rng = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["laptop_id", "brand", "model", "retailer", "observed_at", "price", "currency"])
    for n, (lid, brand, model, base) in enumerate(LAPTOPS):
        for ri, retailer in enumerate(RETAILERS):
            price = base * (1 + 0.02 * ri)
            for d in range(days, -1, -1):
                price *= 1 + rng.uniform(-0.012, 0.012)
                if n == 0 and d == 1:
                    price *= 0.93                       # planned dip on the first laptop: a BUY_NOW case
                if n == 1 and d == 1:
                    price *= 1.10                       # planned rise on the second laptop: a WAIT case
                ts = (now - timedelta(days=d)).replace(hour=8 + ri, minute=0, second=0, microsecond=0)
                w.writerow([lid, brand, model, retailer, ts.astimezone(timezone.utc).isoformat(timespec="seconds"), f"{price:.2f}", "EUR"])
    return out.getvalue()
