# Market signals (optional extension, not part of the assignment)

**Status:** implemented and unit-tested without network; **never run against the real feeds** and not deployed. Off by default.

## What it does
A deferrable batch reads public RSS/Atom feeds and counts how often topics that may affect laptop component prices
(for example AI data-centre build-out and memory prices) appear in recent headlines. The counts are shown on the product
page as "Market context" next to the recommendation.

## What it is not
- It is **not a price forecast** and it **does not change** the forecast, the advice rules or the recommendation
  (`tests/test_market.py::test_recommendation_and_forecast_do_not_change_when_signals_exist`).
- A count of headlines does not prove a price effect. The shopper sees this sentence with every signal.
- No language model is involved; matching is whole-phrase on normalised text (`src/shopping/market.py`).

## How it works
| Part | Behaviour |
|---|---|
| Scheduling | Same pattern as the model evaluation (`Scheduler.run_market`): runs in GREEN, waits in AMBER and RED, at most 24 h; at most one run per 6 h (`SHOPPING_MARKET_INTERVAL_HOURS`). Decisions are logged in `job_log` as `defer_market` / `run_market` with estimated energy (power x measured duration). |
| Sources | `SHOPPING_NEWS_FEEDS` (comma separated https URLs) or the defaults: BBC News world and technology, NPR world (1004) and technology (1019). Enabled only with `SHOPPING_MARKET_SCAN=on`. |
| Fields read | Title (decides), feed tags (`<category>`, Atom `category term`, `dc:subject`; up to 8, 60 characters each) and a short description (`description`/`summary`, markup removed, 500 characters). `#hashtags` in these texts are also matched in their spoken form (`#AIDataCentres`, `#ai-data-centres`, `#ai_data_centres` all match "ai data centres"). No social networks, no API keys, no full articles. |
| Role of tags and description | They only **confirm** a headline that already matches in the title: shown as `evidence` (`title`, `tag`, `summary`) and never counted towards the threshold. A headline that matches only in a tag or description is reported as `supporting_mentions` (not counted). Chosen by the authors; to count them the rule in `MarketScanner.scan` would change. |
| Topics | Built-in dictionary of 6 topics (AI data-centre build-out, memory chip prices, semiconductor supply and export controls, tariffs and trade restrictions, battery materials and supply, display panels) or a JSON file in `SHOPPING_MARKET_TOPICS_FILE`. |
| Signal | A topic is a signal when at least 3 distinct headlines from at least 2 sources match within 7 days. The same story in two feeds counts once. |
| Stored | Title, link, source, counts and the evidence labels only; the description and tags are never stored (`tests/test_market.py::test_description_text_is_not_stored_in_the_database`). Scan runs, signals and operator events in `market_scan_runs`, `market_signals`, `market_events`. Signals older than 48 h are not shown; data older than 30 days is deleted. |
| Failures | A broken feed is skipped (`partial`); all feeds failing is `failed`, the previous signals stay until they are 48 h old. |
| Safety | https only, 1 MB limit, 10 s timeout, DOCTYPE/entity XML refused, only http(s) links kept, links open with `rel=noopener`. |
| Operator | `GET /ops/market` (feeds, last runs, current signals); `POST /ops/market-events` adds a manual event (topic, category, note, valid_days 1-90), audited. |
| Metrics | `shopping_market_scan_runs_total`, `_source_errors_total`, `_headlines_scanned`, `_active_signals`, `_last_success_age_seconds`, `_estimated_energy_kwh_total`. |

## Licences and limits
Both outlets offer these feeds for personal, non-commercial use (the BBC asks that feeds and branding stay unchanged and link to BBC News;
NPR labels its feed "For Personal Use Only"). Use here is coursework only; do not enable it for a commercial deployment. The feed URLs were
found through search; NPR 1004 was fetched once and is valid RSS, BBC and NPR 1019 were **not** fetched from this environment.
The cluster needs outbound https (kind has it by default; not verified).

## Phrase policy
Cautious: multi-word or unambiguous phrases only. Single words that mean something else in common news (for example "fab", "flash", "wafer", "sanctions", "panel prices" which also matches solar panels) are deliberately **not** in the dictionary; `tests/test_market.py::test_ambiguous_single_words_do_not_match` guards this.
Known weaker phrases, kept because the authors approved them: "export ban" and "supply chain disruption" also occur in unrelated news; the threshold (3 headlines from 2 sources) limits, but does not remove, false signals.

## Open points
- Topic dictionary, phrases and thresholds are demonstration values; the phrases were proposed by the tool and not tested on real feeds, so some will miss and some will over-match.
- Signals are not mapped to individual laptops (every laptop shows the same list); mapping by component would need product data the project does not have.
