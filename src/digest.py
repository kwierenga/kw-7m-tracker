from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jinja2 import Template

from .diff import DiffBuckets, regions_for
from .regions import REGIONS, by_slug

PAGE_TEMPLATE = Template(
    """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{{ subject }}</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 760px; margin: 2em auto; padding: 0 1em; color: #222; }
  h2 { margin-bottom: 0.2em; }
  h3 { margin-top: 1.6em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }
  h4 { margin-bottom: 0.4em; }
  ul { padding-left: 1.2em; }
  li { margin-bottom: 0.6em; line-height: 1.4; }
  .meta { color: #666; font-size: 90%; }
  .approx { color: #a60; }
  .note { color: #888; font-size: 85%; }
  details { margin-top: 0.6em; }
  summary { cursor: pointer; color: #06a; }
  a { color: #06a; }
  .pill-new { background: #d6f5e3; color: #086c3a; padding: 1px 6px; border-radius: 8px; font-size: 80%; }
  .topnav { color: #888; font-size: 90%; }
  .src-tag { color: #666; font-size: 85%; }
  .also-at { color: #888; font-size: 80%; margin-left: 1.5em; display: block; }
  .also-at a { color: #888; }
  .listing-row { display: flex; gap: 12px; align-items: flex-start; }
  .listing-thumb { flex: 0 0 auto; width: 120px; height: 90px; object-fit: cover; border-radius: 4px; background: #eee; }
  .listing-body { flex: 1 1 auto; min-width: 0; }
</style>
</head>
<body>
<p class="topnav">
  <a href="archive/">📚 archive</a>
</p>
<h2>Jamaica property watch — week of {{ week_label }}</h2>
<p class="meta">
  {{ summary_line }}<br>
  FX rate used: 1 USD = {{ fx_rate }} JMD.
</p>

{% for region in regions %}
<h3>{{ region.name }}</h3>

{% if region.new_this_week %}
<h4 style="color:#0a7;">🆕 New this week ({{ region.new_this_week|length }})</h4>
<ul>
{% for L in region.new_this_week %}
  <li class="listing-row">
    {% if L.photo_url %}<a href="{{ L.primary_url }}"><img class="listing-thumb" src="{{ L.photo_url }}" alt="" loading="lazy"></a>{% else %}<div class="listing-thumb"></div>{% endif %}
    <div class="listing-body">
      {% if L.keyword_boost %}⭐ {% endif %}
      <strong>{{ L.price_label }}</strong> &mdash; {{ L.title }}
      {% if L.location_text %}<span class="meta"> &middot; {{ L.location_text }}</span>{% endif %}
      {% if L.location_confidence != 'exact' %}<span class="approx"> &middot; ({{ L.location_confidence }} location)</span>{% endif %}
      <br>
      <a href="{{ L.primary_url }}">{{ L.primary_url|truncate(80) }}</a>
      {% if L.primary_source %}<span class="src-tag"> [{{ L.primary_source }}]</span>{% endif %}
      {% if L.other_sources %}
      <span class="also-at">also at:
        {% for src, url in L.other_sources %}<a href="{{ url }}">{{ src }}</a>{% if not loop.last %}, {% endif %}{% endfor %}
      </span>
      {% endif %}
      <span class="note">first seen: {{ L.first_seen_iso }}{% if L.listed_on_iso %} &middot; listed on site: {{ L.listed_on_iso }}{% endif %}</span>
    </div>
  </li>
{% endfor %}
</ul>
{% else %}
<p><em>No new listings this week.</em></p>
{% endif %}

{% if region.still_active %}
<details><summary>📋 Still active ({{ region.still_active|length }})</summary>
<ul>
{% for L in region.still_active %}
  <li>{{ L.price_label }} &mdash; {{ L.title }} &middot;
    <a href="{{ L.primary_url }}">link</a>
    {% if L.primary_source %}<span class="src-tag"> [{{ L.primary_source }}]</span>{% endif %}
    {% if L.other_sources %}<span class="src-tag"> + {{ L.other_sources|length }} other</span>{% endif %}
    &middot; <span class="note">first seen {{ L.first_seen_iso }}</span>
  </li>
{% endfor %}
</ul>
</details>
{% endif %}

{% if region.dropped_off %}
<details><summary>⚠️ Dropped off since last run ({{ region.dropped_off|length }})</summary>
<ul>
{% for L in region.dropped_off %}
  <li>{{ L.price_label }} &mdash; {{ L.title }}</li>
{% endfor %}
</ul>
</details>
{% endif %}

{% endfor %}

<hr>
<p class="note">
  Generated {{ run_iso }}. Sources scraped this run: {{ sources_label }}.
  {% if notes %}<br>Notes: {{ notes }}{% endif %}
</p>
</body>
</html>
"""
)


ARCHIVE_INDEX_TEMPLATE = Template(
    """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Property watch &mdash; archive</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 600px; margin: 2em auto; padding: 0 1em; }
  a { color: #06a; }
</style>
</head>
<body>
<p><a href="../">&larr; latest</a></p>
<h2>Past digests</h2>
<ul>
{% for entry in entries %}
  <li><a href="{{ entry }}.html">{{ entry }}</a></li>
{% endfor %}
</ul>
</body>
</html>
"""
)


def _price_label(row: dict) -> str:
    usd = row.get("price_usd")
    original = row.get("price_original")
    cur = row.get("price_currency")
    if usd is not None:
        s = f"${usd:,} USD"
        if cur == "JMD" and original:
            s += f" (was {original})"
        return s
    return original or "price unknown"


SOURCE_RANK = {
    "xposure": 1,
    "realtor_com_intl": 2,
    "cb_jamaica": 3,
    "century21_jm": 4,
    "caribbean_mls": 5,
    "golden_gates": 6,
    "millennium": 7,
}


def _row_to_view(row: dict) -> dict:
    out = dict(row)
    sources = json.loads(row.get("sources_json") or "[]")
    urls = json.loads(row.get("urls_json") or "[]")
    paired = list(zip(sources, urls))
    paired.sort(key=lambda sv: SOURCE_RANK.get(sv[0], 99))
    if paired:
        out["primary_source"] = paired[0][0]
        out["primary_url"] = paired[0][1]
        out["other_sources"] = paired[1:]
    else:
        out["primary_source"] = ""
        out["primary_url"] = ""
        out["other_sources"] = []
    out["price_label"] = _price_label(row)
    return out


def build_digest(buckets: DiffBuckets, fx_rate: float, sources: list[str], run_iso: str, notes: str = "") -> tuple[str, str]:
    """Returns (page_title, html)."""
    by_region: dict[str, dict] = {}
    for r in REGIONS:
        by_region[r.slug] = {"name": r.name, "new_this_week": [], "still_active": [], "dropped_off": []}

    def assign(rows: list[dict], key: str) -> None:
        for row in rows:
            view = _row_to_view(row)
            slugs = regions_for(row) or [REGIONS[0].slug]
            for slug in slugs:
                bucket = by_region.setdefault(
                    slug,
                    {"name": (by_slug(slug).name if by_slug(slug) else slug), "new_this_week": [], "still_active": [], "dropped_off": []},
                )
                bucket[key].append(view)

    assign(buckets.new_this_week, "new_this_week")
    assign(buckets.still_active, "still_active")
    assign(buckets.dropped_off, "dropped_off")

    region_views = list(by_region.values())
    total_new = sum(len(v["new_this_week"]) for v in region_views)
    total_active = sum(len(v["still_active"]) for v in region_views)
    total_dropped = sum(len(v["dropped_off"]) for v in region_views)

    week_label = date.today().isoformat()
    per_region_new = ", ".join(f"{v['name']}: {len(v['new_this_week'])}" for v in region_views if v["new_this_week"])
    subject = f"Jamaica property watch — week of {week_label} — {total_new} new" + (f" ({per_region_new})" if per_region_new else "")
    summary_line = f"{total_new} new this week, {total_active} still active, {total_dropped} dropped off."
    html = PAGE_TEMPLATE.render(
        subject=subject,
        week_label=week_label,
        summary_line=summary_line,
        fx_rate=f"{fx_rate:.2f}",
        regions=region_views,
        sources_label=", ".join(sources) or "(none)",
        notes=notes,
        run_iso=run_iso,
    )
    return subject, html


def write_static_site(html: str, run_iso: str, root: Path | None = None) -> Path:
    """Writes docs/index.html (latest) + docs/archive/<date>.html (snapshot) +
    docs/archive/index.html (listing). Returns path to index.html."""
    root = root or Path(__file__).resolve().parent.parent
    docs = root / "docs"
    archive = docs / "archive"
    archive.mkdir(parents=True, exist_ok=True)

    date_str = run_iso[:10]  # YYYY-MM-DD
    (docs / "index.html").write_text(html, encoding="utf-8")
    (archive / f"{date_str}.html").write_text(html, encoding="utf-8")

    entries = sorted(
        {p.stem for p in archive.glob("*.html") if p.name != "index.html"},
        reverse=True,
    )
    (archive / "index.html").write_text(
        ARCHIVE_INDEX_TEMPLATE.render(entries=entries),
        encoding="utf-8",
    )
    return docs / "index.html"
