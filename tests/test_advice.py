import pytest

from shopping.advice import BUY_NOW, INSUFFICIENT, WAIT, Constraints, Evidence, Forecast, advise

FRESH_DOWN, FRESH_UP, FRESH_FLAT = Forecast("FRESH", -0.05), Forecast("FRESH", 0.05), Forecast("FRESH", 0.0)
STALE, MISSING = Forecast("STALE", -0.2), Forecast("MISSING")


def ev(delta=0.0, price=1000.0, brand="Acme", sufficient=True):
    return Evidence(sufficient, delta, price, brand)


@pytest.mark.parametrize("evidence,forecast,expected", [
    (ev(sufficient=False), FRESH_DOWN, INSUFFICIENT),            # rule 1 beats everything
    (ev(delta=0.0), FRESH_DOWN, WAIT),                           # rule 2
    (ev(delta=-0.10), FRESH_DOWN, WAIT),                         # rule 2 before rule 4
    (ev(delta=0.03), FRESH_FLAT, WAIT),                          # rule 3 at the boundary
    (ev(delta=-0.03), FRESH_FLAT, BUY_NOW),                      # rule 4 at the boundary
    (ev(delta=0.0), FRESH_UP, BUY_NOW),                          # rule 5
    (ev(delta=0.02), FRESH_FLAT, INSUFFICIENT),                  # rule 6
    (ev(delta=0.02), Forecast("FRESH", -0.03), WAIT),            # rule 2 boundary
])
def test_rules(evidence, forecast, expected):
    assert advise(evidence, forecast).action == expected


@pytest.mark.parametrize("forecast", [STALE, MISSING])
def test_stale_or_missing_forecast_skips_forecast_rules_and_adds_a_caveat(forecast):
    a = advise(ev(delta=0.0), forecast)
    assert a.action == INSUFFICIENT and "no fresh forecast" in a.caveats
    assert advise(ev(delta=-0.05), forecast).action == BUY_NOW   # decided from the delta only


def test_no_budget_means_no_budget_verdict():
    a = advise(ev(delta=-0.05), FRESH_FLAT)
    assert a.within_budget is None and not a.needs_alternatives


def test_buy_now_is_withheld_above_budget_and_alternatives_are_requested():
    a = advise(ev(delta=-0.05, price=1200), FRESH_FLAT, Constraints(budget=1000))
    assert a.action == WAIT and a.within_budget is False and a.needs_alternatives
    assert "the best offer is above your budget" in a.reasons


def test_buy_now_within_budget_is_kept():
    a = advise(ev(delta=-0.05, price=900), FRESH_FLAT, Constraints(budget=1000))
    assert a.action == BUY_NOW and a.within_budget is True and not a.needs_alternatives


def test_over_budget_does_not_turn_insufficient_evidence_into_wait():
    assert advise(ev(price=1500, sufficient=False), FRESH_FLAT, Constraints(budget=1000)).action == INSUFFICIENT


def test_brand_preference_requests_alternatives_but_keeps_the_label():
    a = advise(ev(delta=-0.05, brand="Other"), FRESH_FLAT, Constraints(preferred_brands=("acme",)))
    assert a.action == BUY_NOW and a.needs_alternatives and "not one of your preferred brands" in a.caveats
    assert not advise(ev(delta=-0.05, brand="ACME"), FRESH_FLAT, Constraints(preferred_brands=("acme",))).needs_alternatives


def test_invalid_budget_is_rejected():
    with pytest.raises(ValueError):
        Constraints(budget=0)
