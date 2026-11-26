"""Small RSS/Atom documents for tests/test_market.py (invented headlines, no network)."""


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link>" + (f"<pubDate>{d}</pubDate>" if d else "") + "</item>" for t, l, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'.encode()


def atom(items):
    body = "".join(f'<entry><title>{t}</title><link href="{l}"/><updated>{d}</updated></entry>' for t, l, d in items)
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>{body}</feed>'.encode()


FEED_A = rss([("Tech giants announce new AI data centres", "https://a.example/1", "Tue, 24 Nov 2026 10:00:00 GMT"),
              ("AI infrastructure spending doubles, data centres planned across Europe", "https://a.example/2", "Tue, 24 Nov 2026 12:00:00 GMT"),
              ("Local football results", "https://a.example/3", "Tue, 24 Nov 2026 13:00:00 GMT")])
FEED_B = rss([("Why new data centres are straining power grids", "https://b.example/1", "Mon, 23 Nov 2026 09:00:00 GMT"),
              ("DRAM supply tightens as AI demand grows", "https://b.example/2", "Mon, 23 Nov 2026 10:00:00 GMT"),
              ("Recipe of the week", "https://b.example/3", None)])


def rich(items):
    """Items as dicts: title, link, tags (list), description."""
    body = ""
    for it in items:
        body += f"<item><title>{it['title']}</title><link>{it.get('link', 'https://x.example/r')}</link>"
        body += "".join(f"<category>{t}</category>" for t in it.get("tags", []))
        body += f"<description>{it.get('description', '')}</description></item>"
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'.encode()
