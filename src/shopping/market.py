"""Market Signals: recurring world topics in public news headlines that may move laptop component prices.

A deferrable batch (scheduled like the model evaluation: runs in GREEN, waits in AMBER and RED, at most 24 h) reads a
configured list of public RSS/Atom feeds, counts how many DISTINCT headlines and how many sources match a dictionary of
topics (for example "AI data centres" -> memory prices) and stores the counts. Only title, link, source and time of a
headline are kept (feed licences allow personal, non-commercial use; the default feeds are for coursework only).

What this is and is not:
- The counting is deterministic (normalised titles, whole-phrase matching). No language model decides anything.
- A signal is CONTEXT shown next to a recommendation. It never changes the price forecast or the advice rules, and a
  count of headlines is no proof of a price effect. The text shown to the shopper says so.
- Phrases are matched in the headline; feed tags (<category>), a short description and #hashtags in those texts only CONFIRM
  a headline that already matches in the title (they are shown as evidence and counted as "supporting", never towards the
  threshold). The description is read for matching only and is never stored.
- Feeds are fetched only over https, with a size limit and without any personal data. XML with a DOCTYPE or entities is
  refused (entity expansion attacks).
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse

from .energy import iso

DEFAULT_FEEDS = (                                       # public RSS feeds, personal / non-commercial use (coursework)
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://feeds.npr.org/1004/rss.xml",
    "https://feeds.npr.org/1019/rss.xml",
)
WINDOW_DAYS = 7
MIN_MENTIONS = 3                                         # distinct headlines
MIN_SOURCES = 2                                          # distinct feed hosts
SIGNAL_MAX_AGE = timedelta(hours=48)                     # an older scan is not shown any more
RETENTION = timedelta(days=30)
MAX_FEED_BYTES = 1_000_000
MAX_TITLE = 200
MAX_SAMPLES = 3
USER_AGENT = "SmartShopping/1.0 (university coursework; read-only headline counting)"
NOTICE = "Market context from public news headlines. It is not a price forecast and does not change the recommendation."


@dataclass(frozen=True)
class Topic:
    topic: str
    label: str
    categories: tuple
    phrases: tuple                                       # whole-phrase matches on the normalised title


TOPICS = (
    Topic("ai_datacentres", "AI data-centre build-out", ("memory", "storage", "gpu"),
          ("data centre", "data centres", "data center", "data centers", "datacentre", "datacentres", "datacenter", "datacenters",
           "ai infrastructure", "ai chips", "ai chip", "ai accelerators", "ai factory", "ai factories", "ai compute", "ai servers", "ai server",
           "hyperscale", "hyperscaler", "hyperscalers", "gpu cluster", "gpu clusters")),
    Topic("memory_prices", "Memory chip prices", ("memory", "storage"),
          ("dram", "hbm", "hbm3", "hbm4", "ddr4", "ddr5", "lpddr5", "memory chip", "memory chips", "memory prices", "memory price", "ram prices", "ram price",
           "ram shortage", "memory shortage", "memory supply", "memory makers", "nand flash", "nand prices", "flash memory", "ssd prices", "ssd shortage")),
    Topic("chip_supply", "Semiconductor supply and export controls", ("gpu", "cpu", "memory"),
          ("semiconductor", "semiconductors", "chip shortage", "chip shortages", "chip supply", "chipmaker", "chipmakers", "chip makers", "chip plant", "chip plants",
           "chip factory", "chip factories", "chips act", "chip export", "export controls", "supply chain disruption", "rare earths", "tsmc", "micron", "sk hynix")),
    Topic("trade_tariffs", "Tariffs and trade restrictions", ("all",),
          ("tariff", "tariffs", "trade war", "trade barriers", "trade restrictions", "import duties", "customs duties", "import tax", "import taxes", "export ban", "export bans")),
    Topic("batteries", "Battery materials and supply", ("battery",),
          ("lithium shortage", "lithium prices", "lithium supply", "lithium ion", "li ion", "battery shortage", "battery prices", "battery supply",
           "battery makers", "battery plant", "battery factory", "gigafactory", "cobalt prices", "cobalt supply")),
    Topic("displays", "Display panels", ("display",),
          ("oled", "amoled", "mini led", "micro led", "display panel", "display panels", "display shortage", "lcd panel", "lcd panels", "oled panel", "oled panels", "display makers")),
)


def load_topics(path: Optional[str]) -> tuple:
    """Dictionary from a JSON file [{"topic","label","categories":[...],"phrases":[...]}], else the built-in one."""
    if not path:
        return TOPICS
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return tuple(Topic(str(t["topic"]), str(t["label"]), tuple(t["categories"]), tuple(str(p).lower() for p in t["phrases"])) for t in raw)


@dataclass(frozen=True)
class Headline:
    title: str
    link: Optional[str]
    published: Optional[datetime]
    tags: tuple = ()                                     # <category> labels; used for matching only
    summary: str = ""                                    # short description, HTML removed; used for matching only, never stored


MAX_SUMMARY = 500
MAX_TAGS = 8
MAX_TAG = 60
_MARKUP = re.compile(r"<[^>]*>")
_HASHTAG = re.compile(r"#([A-Za-z0-9][A-Za-z0-9_\-]*)")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def clean_text(text: str, limit: int) -> str:
    """Untrusted feed text: tags removed, entities decoded, whitespace collapsed, length limited."""
    return " ".join(html.unescape(_MARKUP.sub(" ", text)).split())[:limit]


def search_text(*parts: str) -> str:
    """Normalised text for matching; #AIDataCentres is also searchable as "ai data centres"."""
    text = " ".join(p for p in parts if p)
    tags = " ".join(_CAMEL.sub(" ", h) for h in _HASHTAG.findall(text))
    return normalise(f"{text} {tags}")


def normalise(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _when(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    for parse in (parsedate_to_datetime, lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))):
        try:
            d = parse(text)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def parse_feed(data: bytes) -> list[Headline]:
    """RSS 2.0 items and Atom entries. Refuses DOCTYPE/ENTITY, keeps only http(s) links."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head or b"<!entity" in data.lower():
        raise ValueError("feed contains a DOCTYPE or entity declaration")
    root = ET.fromstring(data)
    out = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        tags: list[str] = []
        for ch in node:
            name = _local(ch.tag)
            if name == "link" and not (ch.text or "").strip() and ch.get("href"):
                fields.setdefault("link", ch.get("href"))
            elif name in ("category", "subject"):
                label = clean_text(ch.get("term") or ch.text or "", MAX_TAG)
                if label and len(tags) < MAX_TAGS:
                    tags.append(label)
            elif name in ("title", "link", "pubDate", "published", "updated", "description", "summary") and (ch.text or "").strip():
                fields.setdefault(name, ch.text.strip())
        title = " ".join(fields.get("title", "").split())[:MAX_TITLE]
        if not title:
            continue
        link = fields.get("link")
        link = link if link and urlparse(link).scheme in ("http", "https") else None
        out.append(Headline(title, link, _when(fields.get("pubDate") or fields.get("published") or fields.get("updated")), tuple(tags),
                            clean_text(fields.get("description") or fields.get("summary") or "", MAX_SUMMARY)))
    return out


def fetch_url(url: str, timeout: float = 10.0) -> bytes:
    if urlparse(url).scheme != "https":
        raise ValueError("only https feeds are fetched")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:                     # noqa: S310 (scheme checked above)
        data = resp.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("feed larger than the limit")
    return data


class MarketScanner:
    def __init__(self, db, feeds: Iterable[str] = DEFAULT_FEEDS, topics: tuple = TOPICS, fetch: Callable[[str], bytes] = fetch_url,
                 window_days: int = WINDOW_DAYS, min_mentions: int = MIN_MENTIONS, min_sources: int = MIN_SOURCES) -> None:
        self.db, self.feeds, self.topics, self.fetch = db, tuple(feeds), topics, fetch
        self.window_days, self.min_mentions, self.min_sources = window_days, min_mentions, min_sources

    def scan(self, now: datetime, mode: Optional[str] = None) -> dict:
        window_start = now - timedelta(days=self.window_days)
        ok = failed = 0
        errors: list[str] = []
        seen: dict[str, dict] = {}                                                  # normalised title -> headline, sources
        for url in self.feeds:
            host = urlparse(url).hostname or url
            try:
                headlines = parse_feed(self.fetch(url))
            except Exception as exc:                                                # one broken feed must not stop the others
                failed += 1
                errors.append(f"{host}: {type(exc).__name__}")
                continue
            ok += 1
            for hl in headlines:
                if hl.published is not None and hl.published < window_start:
                    continue
                entry = seen.setdefault(normalise(hl.title), {"title": hl.title, "link": hl.link, "sources": set(), "head": search_text(hl.title), "tags": "", "summary": ""})
                entry["sources"].add(host)
                entry["tags"] = (entry["tags"] + " " + search_text(*hl.tags))[:1000]
                entry["summary"] = (entry["summary"] + " " + search_text(hl.summary))[:2 * MAX_SUMMARY]
        outcome = "failed" if ok == 0 else ("partial" if failed else "ok")
        rows = []
        if ok:
            for t in self.topics:
                phrases = [f" {normalise(ph)} " for ph in t.phrases]
                found = lambda text: any(ph in f" {text} " for ph in phrases)       # noqa: E731
                hits = [n for n, e in seen.items() if found(e["head"])]
                supporting = [n for n, e in seen.items() if n not in hits and (found(e["tags"]) or found(e["summary"]))]   # not counted, only reported
                if not hits and not supporting:
                    continue
                sources = set().union(*(seen[n]["sources"] for n in hits)) if hits else set()
                active = int(len(hits) >= self.min_mentions and len(sources) >= self.min_sources)
                samples = {"examples": [{"title": seen[n]["title"], "link": seen[n]["link"],
                                         "evidence": ["title"] + (["tag"] if found(seen[n]["tags"]) else []) + (["summary"] if found(seen[n]["summary"]) else [])}
                                        for n in hits[:MAX_SAMPLES]], "supporting": len(supporting)}
                rows.append((iso(now), t.topic, t.label, ",".join(t.categories), len(hits), len(sources), self.window_days, active, json.dumps(samples)))
        with self.db:
            for r in rows:
                self.db.execute("INSERT INTO market_signals (computed_at, topic, label, categories, mentions, sources, window_days, active, samples) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", r)
            self.db.execute("INSERT INTO market_scan_runs (run_at, mode, feeds, failed, headlines, signals, outcome, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (iso(now), mode, len(self.feeds), failed, len(seen), sum(r[7] for r in rows), outcome, "; ".join(errors)[:500] or None))
            self.db.execute("DELETE FROM market_signals WHERE computed_at < ?", (iso(now - RETENTION),))
        return {"outcome": outcome, "feeds": len(self.feeds), "failed": failed, "headlines": len(seen), "signals": sum(r[7] for r in rows), "errors": errors}


def current_signals(db, now: datetime) -> list[dict]:
    """Active signals of the newest successful scan (not older than 48 h) and operator events still valid."""
    out: list[dict] = []
    last = db.execute("SELECT MAX(run_at) FROM market_scan_runs WHERE outcome IN ('ok', 'partial')").fetchone()[0]
    if last and now - datetime.fromisoformat(last) <= SIGNAL_MAX_AGE:
        for topic, label, cats, mentions, sources, days, samples in db.execute(
                "SELECT topic, label, categories, mentions, sources, window_days, samples FROM market_signals WHERE computed_at=? AND active=1 ORDER BY mentions DESC, topic", (last,)):
            data = json.loads(samples or "[]")
            examples, supporting = (data.get("examples", []), data.get("supporting", 0)) if isinstance(data, dict) else (data, 0)
            out.append({"origin": "news", "topic": topic, "label": label, "categories": cats.split(","), "mentions": mentions, "sources": sources,
                        "supporting_mentions": supporting, "window_days": days, "computed_at": last, "examples": examples})
    for topic, category, note, until, by in db.execute("SELECT topic, category, note, valid_until, set_by FROM market_events WHERE valid_until > ? ORDER BY id DESC", (iso(now),)):
        out.append({"origin": "operator", "topic": topic, "label": topic, "categories": [category] if category else ["all"], "note": note, "valid_until": until})
    return out
