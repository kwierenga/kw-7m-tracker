from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jinja2 import Template

from .diff import DiffBuckets, regions_for
from .regions import REGIONS, by_slug

# Each region is really three searches: Homes (higher budget), Land (lower
# budget), and listings whose property_type couldn't be determined. Render
# them as separate sub-sections so the per-search status (new/active/stale/
# dropped) is visible at a glance.
PROPERTY_TYPE_ORDER = ("home", "land", "unknown")
PROPERTY_TYPE_LABELS = {
    "home": "🏠 Homes",
    "land": "🌿 Land",
    "unknown": "❓ Type unclear",
}

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
  h4 { margin-bottom: 0.4em; margin-top: 1.2em; }
  h5 { margin-bottom: 0.3em; margin-top: 0.8em; color: #444; }
  .section-header { color: #333; }
  .section-budget { color: #888; font-weight: normal; font-size: 85%; margin-left: 0.4em; }
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
  .src-fail { color: #c44; font-weight: 600; }
  .also-at { color: #888; font-size: 80%; margin-left: 1.5em; display: block; }
  .also-at a { color: #888; }
  .listing-row { display: flex; gap: 12px; align-items: flex-start; }
  .listing-thumb { flex: 0 0 auto; width: 120px; height: 90px; object-fit: cover; border-radius: 4px; background: #eee; }
  .listing-body { flex: 1 1 auto; min-width: 0; }
  .stale-summary { color: #888; }
</style>
</head>
<body>
<p class="topnav">
  <a href="archive/">📚 archive</a>
</p>
<h2>Jamaica property watch — {{ date_label }}</h2>
<p class="meta">
  {{ summary_line }}<br>
  FX rate used: 1 USD = {{ fx_rate }} JMD.
</p>

{% for region in regions %}
<h3>{{ region.name }}</h3>

{% for section in region.visible_sections %}
<h4 class="section-header">{{ section.label }}{% if section.budget_label %}<span class="section-budget">({{ section.budget_label }})</span>{% endif %}</h4>

{% if section.new_since_last_run %}
<h5 style="color:#0a7;">🆕 New since last run ({{ section.new_since_last_run|length }})</h5>
<ul>
{% for L in section.new_since_last_run %}
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
<p><em>No new listings since last run.</em></p>
{% endif %}

{% if section.still_active %}
<details><summary>📋 Still active ({{ section.still_active|length }})</summary>
<ul>
{% for L in section.still_active %}
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

{% if section.stale %}
<details class="stale-summary"><summary>🕸 Stale (90+ days on market) ({{ section.stale|length }})</summary>
<ul>
{% for L in section.stale %}
  <li>{{ L.price_label }} &mdash; {{ L.title }} &middot;
    <a href="{{ L.primary_url }}">link</a>
    {% if L.primary_source %}<span class="src-tag"> [{{ L.primary_source }}]</span>{% endif %}
    &middot; <span class="note">first seen {{ L.first_seen_iso }}{% if L.listed_on_iso %} &middot; listed on site {{ L.listed_on_iso }}{% endif %}</span>
  </li>
{% endfor %}
</ul>
</details>
{% endif %}

{% if section.dropped_off %}
<details><summary>⚠️ Dropped off since last run ({{ section.dropped_off|length }})</summary>
<ul>
{% for L in section.dropped_off %}
  <li>{{ L.price_label }} &mdash; {{ L.title }}</li>
{% endfor %}
</ul>
</details>
{% endif %}

{% endfor %}
{% endfor %}

<hr>
<p class="note">
  Generated {{ run_iso }}.
  {% if sources_counts %}
  Per-source counts: {% for name, count in sources_counts.items() %}{% if count < 0 %}<span class="src-fail">{{ name }}=FAILED</span>{% else %}{{ name }}={{ count }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}.
  {% else %}
  Sources scraped this run: {{ sources_label }}.
  {% endif %}
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


def _empty_section(pt: str, region) -> dict:
    if pt == "home":
        budget_label = f"budget ${region.home_budget_usd:,} USD" if region else ""
    elif pt == "land":
        budget_label = f"budget ${region.land_budget_usd:,} USD" if region else ""
    else:
        budget_label = ""
    return {
        "key": pt,
        "label": PROPERTY_TYPE_LABELS[pt],
        "budget_label": budget_label,
        "new_since_last_run": [],
        "still_active": [],
        "stale": [],
        "dropped_off": [],
    }


def _empty_region_buckets(name: str, region=None) -> dict:
    return {
        "name": name,
        "sections": {pt: _empty_section(pt, region) for pt in PROPERTY_TYPE_ORDER},
    }


def _section_has_anything(section: dict) -> bool:
    return bool(
        section["new_since_last_run"]
        or section["still_active"]
        or section["stale"]
        or section["dropped_off"]
    )


def build_digest(
    buckets: DiffBuckets,
    fx_rate: float,
    sources: list[str],
    run_iso: str,
    notes: str = "",
    sources_counts: dict[str, int] | None = None,
) -> tuple[str, str]:
    """Returns (page_title, html)."""
    by_region: dict[str, dict] = {}
    for r in REGIONS:
        by_region[r.slug] = _empty_region_buckets(r.name, r)

    def assign(rows: list[dict], key: str) -> None:
        for row in rows:
            view = _row_to_view(row)
            slugs = regions_for(row) or [REGIONS[0].slug]
            pt = (row.get("property_type") or "unknown").lower()
            if pt not in PROPERTY_TYPE_ORDER:
                pt = "unknown"
            for slug in slugs:
                region = by_slug(slug)
                bucket = by_region.setdefault(
                    slug,
                    _empty_region_buckets(region.name if region else slug, region),
                )
                bucket["sections"][pt][key].append(view)

    assign(buckets.new_since_last_run, "new_since_last_run")
    assign(buckets.still_active, "still_active")
    assign(buckets.stale, "stale")
    assign(buckets.dropped_off, "dropped_off")

    # Show home/land sections always so empty searches stay visible. Hide the
    # unknown section unless it has something to show.
    region_views = list(by_region.values())
    for v in region_views:
        v["visible_sections"] = [
            v["sections"][pt]
            for pt in PROPERTY_TYPE_ORDER
            if pt in ("home", "land") or _section_has_anything(v["sections"][pt])
        ]
        v["new_since_last_run_count"] = sum(
            len(s["new_since_last_run"]) for s in v["sections"].values()
        )

    def _sum(key: str) -> int:
        return sum(
            len(s[key]) for v in region_views for s in v["sections"].values()
        )

    total_new = _sum("new_since_last_run")
    total_active = _sum("still_active")
    total_stale = _sum("stale")
    total_dropped = _sum("dropped_off")

    date_label = date.today().isoformat()
    per_region_new = ", ".join(
        f"{v['name']}: {v['new_since_last_run_count']}"
        for v in region_views
        if v["new_since_last_run_count"]
    )
    subject = f"Jamaica property watch — {date_label} — {total_new} new" + (f" ({per_region_new})" if per_region_new else "")
    summary_line = (
        f"{total_new} new since last run, "
        f"{total_active} still active, "
        f"{total_stale} stale, "
        f"{total_dropped} dropped off."
    )
    html = PAGE_TEMPLATE.render(
        subject=subject,
        date_label=date_label,
        summary_line=summary_line,
        fx_rate=f"{fx_rate:.2f}",
        regions=region_views,
        sources_label=", ".join(sources) or "(none)",
        sources_counts=sources_counts or {},
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
