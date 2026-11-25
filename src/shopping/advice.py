"""Advice Engine: the rules of docs/project-specification.md ("Price and recommendation semantics"),
plus the optional budget and brand constraints (FR-22).

Pure and deterministic: no I/O. Alternatives are looked up by the caller (Shopping API -> Catalog Query),
so the rules stay free of data access and a model never changes the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BUY_NOW, WAIT, INSUFFICIENT = "BUY_NOW", "WAIT", "INSUFFICIENT_EVIDENCE"
FRESH, STALE, MISSING = "FRESH", "STALE", "MISSING"
THRESHOLD = 0.03          # demonstration value, configurable


@dataclass(frozen=True)
class Evidence:
    sufficient: bool
    delta: Optional[float] = None            # current lowest price / 30-day reference - 1
    current_price: Optional[float] = None
    brand: Optional[str] = None


@dataclass(frozen=True)
class Forecast:
    status: str = MISSING                    # FRESH | STALE | MISSING
    change: Optional[float] = None           # change from today to day 7 (f)


@dataclass(frozen=True)
class Constraints:
    budget: Optional[float] = None
    preferred_brands: tuple = ()

    def __post_init__(self):
        if self.budget is not None and self.budget <= 0:
            raise ValueError("budget must be positive")


@dataclass(frozen=True)
class Advice:
    action: str
    reasons: tuple
    caveats: tuple
    within_budget: Optional[bool]            # None when no budget was given
    needs_alternatives: bool                 # over budget or not a preferred brand


def advise(evidence: Evidence, forecast: Forecast, constraints: Optional[Constraints] = None,
           threshold: float = THRESHOLD) -> Advice:
    constraints = constraints or Constraints()
    reasons: list[str] = []
    caveats: list[str] = []
    fresh = forecast.status == FRESH and forecast.change is not None
    if forecast.status != FRESH:
        caveats.append("no fresh forecast")

    if not evidence.sufficient or evidence.delta is None:                       # rule 1
        action = INSUFFICIENT
        reasons.append("too few observation days for a reliable reference")
    elif fresh and forecast.change <= -threshold:                               # rule 2
        action = WAIT
        reasons.append("a fall is expected within seven days")
    elif evidence.delta >= threshold:                                           # rule 3
        action = WAIT
        reasons.append("the price is above the 30-day reference")
    elif evidence.delta <= -threshold:                                          # rule 4
        action = BUY_NOW
        reasons.append("the price is below the 30-day reference")
    elif fresh and forecast.change >= threshold:                                # rule 5
        action = BUY_NOW
        reasons.append("a rise is expected within seven days")
    else:                                                                       # rule 6
        action = INSUFFICIENT
        reasons.append("no clear signal")

    within_budget: Optional[bool] = None
    needs_alt = False
    if constraints.budget is not None and evidence.current_price is not None:
        within_budget = evidence.current_price <= constraints.budget
        if not within_budget:
            needs_alt = True
            reasons.append("the best offer is above your budget")
            if action == BUY_NOW:                      # Buy Now only when the purchase fits the constraints
                action = WAIT
    if constraints.preferred_brands and evidence.brand and evidence.brand.lower() not in {b.lower() for b in constraints.preferred_brands}:
        needs_alt = True
        caveats.append("not one of your preferred brands")
    return Advice(action, tuple(reasons), tuple(caveats), within_budget, needs_alt)
