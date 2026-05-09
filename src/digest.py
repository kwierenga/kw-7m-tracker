from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
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
    "home": "Homes",
    "land": "Land",
    "unknown": "Type unclear",
}
PROPERTY_TYPE_ICONS = {
    "home": "🏠",
    "land": "🌿",
    "unknown": "❓",
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
  :root {
    --bg: #fafaf6;
    --surface: #ffffff;
    --surface-2: #f1efe8;
    --text: #1c1c1c;
    --text-muted: #5e5e5e;
    --text-faint: #8a8a8a;
    --accent: #0a6c5a;
    --accent-bg: #d8f1e7;
    --new-bg: #fff2c4;
    --new-text: #6b4f00;
    --boost: #b87900;
    --border: #e6e3da;
    --link: #0a5a8d;
    --warn: #b85400;
    --shadow: 0 1px 2px rgba(0,0,0,0.04);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #15181a;
      --surface: #1e2123;
      --surface-2: #272a2c;
      --text: #ececec;
      --text-muted: #b0b0b0;
      --text-faint: #7a7a7a;
      --accent: #5cd8b0;
      --accent-bg: #163a30;
      --new-bg: #4a3a00;
      --new-text: #ffe57a;
      --boost: #ffba4a;
      --border: #353a3d;
      --link: #6db8ee;
      --warn: #ffa14a;
      --shadow: 0 1px 2px rgba(0,0,0,0.3);
    }
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    max-width: 920px;
    margin: 0 auto;
    padding: 1rem 1.25rem 4rem;
    line-height: 1.5;
    font-size: 16px;
  }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--text-faint);
    padding-bottom: 0.6rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.25rem;
  }
  .topbar a { color: var(--text-faint); }
  .topbar .nav-links a { margin-left: 0.9rem; }

  h1 {
    font-size: 1.75rem;
    font-weight: 700;
    margin: 0 0 0.4rem;
    letter-spacing: -0.02em;
  }
  .summary {
    color: var(--text-muted);
    font-size: 0.95rem;
    margin: 0 0 1.5rem;
  }
  .count-new { color: var(--accent); font-weight: 700; }
  .count-drops {
    color: var(--accent);
    font-weight: 700;
    cursor: pointer;
    border-radius: 4px;
    padding: 0 0.25rem;
    transition: background 0.1s, color 0.1s;
    user-select: none;
  }
  .count-drops:hover { background: var(--accent-bg); }
  .count-drops[aria-pressed="true"] {
    background: var(--accent);
    color: var(--bg);
  }
  .price-was {
    color: var(--accent);
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .region-jump {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0 0 2rem;
  }
  .region-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.75rem;
    border-radius: 999px;
    background: var(--surface);
    border: 1px solid var(--border);
    font-size: 0.85rem;
    color: var(--text-muted);
    transition: background 0.1s;
  }
  .region-chip:hover { text-decoration: none; background: var(--surface-2); }
  .region-chip.has-new {
    background: var(--accent-bg);
    border-color: transparent;
    color: var(--accent);
    font-weight: 600;
  }
  .region-chip-empty { opacity: 0.55; }
  .region-chip-count { font-variant-numeric: tabular-nums; }

  .region {
    margin-bottom: 2.5rem;
    scroll-margin-top: 1rem;
  }
  .region-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 0 0 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid var(--border);
  }
  .region-header h2 {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.01em;
  }
  .region-stats {
    color: var(--text-faint);
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }

  .subsection { margin: 1.1rem 0 0.5rem; }
  .subsection h3 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.5rem;
  }
  .subsection h3 .budget {
    font-weight: 400;
    color: var(--text-faint);
    font-size: 0.8rem;
    margin-left: 0.5rem;
  }
  .empty-line {
    color: var(--text-faint);
    font-size: 0.85rem;
    font-style: italic;
    margin: 0.25rem 0 0;
  }

  .listings { list-style: none; padding: 0; margin: 0.5rem 0 0; }
  .card {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 1rem;
    padding: 0.85rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 0.6rem;
    box-shadow: var(--shadow);
  }
  .card.is-new { border-color: var(--accent); }
  /* Boost adds an inset stripe so it can coexist with is-new's green border */
  .card.is-boost { box-shadow: inset 4px 0 0 var(--boost), var(--shadow); }
  .card-thumb-link {
    display: block;
    width: 140px;
    aspect-ratio: 4 / 3;
    border-radius: 6px;
    background: var(--surface-2);
    overflow: hidden;
    flex-shrink: 0;
  }
  .card-thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .card-thumb.hidden { display: none; }
  .card-thumb-empty {
    width: 140px;
    aspect-ratio: 4 / 3;
    border-radius: 6px;
    background: var(--surface-2);
  }
  .card-body { min-width: 0; }
  .card-line1 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.2rem;
  }
  .card-price {
    font-weight: 700;
    font-size: 1.05rem;
    font-variant-numeric: tabular-nums;
  }
  .pill {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .pill-new {
    background: var(--new-bg);
    color: var(--new-text);
  }
  .pill-boost {
    color: var(--boost);
    font-size: 1rem;
    line-height: 1;
  }
  .card-title {
    font-size: 0.95rem;
    margin: 0;
  }
  .card-title a {
    color: var(--text);
    text-decoration: underline;
    text-decoration-color: var(--border);
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
  }
  .card-title a:hover {
    color: var(--link);
    text-decoration-color: var(--link);
  }
  .card-loc { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.15rem; }
  .card-loc-approx::after { content: " (approx)"; color: var(--warn); font-size: 0.8rem; }
  .card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.85rem;
    margin-top: 0.5rem;
    font-size: 0.78rem;
    color: var(--text-faint);
    align-items: center;
  }
  .src-pill {
    display: inline-block;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    background: var(--surface-2);
    color: var(--text-muted);
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 0.72rem;
  }
  .also-at a { color: var(--text-faint); margin-right: 0.4rem; text-decoration: underline; text-decoration-color: var(--border); }

  details { margin-top: 0.7rem; }
  details > summary {
    cursor: pointer;
    color: var(--text-muted);
    font-size: 0.88rem;
    list-style: none;
    padding: 0.3rem 0;
    user-select: none;
  }
  details > summary::-webkit-details-marker { display: none; }
  details > summary::before {
    content: "▸";
    display: inline-block;
    margin-right: 0.4rem;
    transition: transform 0.15s;
  }
  details[open] > summary::before { transform: rotate(90deg); }
  details > summary:hover { color: var(--text); }

  .compact-list { list-style: none; padding: 0; margin: 0.4rem 0 0; }
  .compact-list li {
    padding: 0.4rem 0;
    border-bottom: 1px dashed var(--border);
    font-size: 0.88rem;
    color: var(--text-muted);
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 0.55rem;
    align-items: center;
  }
  .compact-list li:last-child { border-bottom: 0; }
  .compact-list .price { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
  .compact-list .age { color: var(--text-faint); font-size: 0.8rem; }
  .compact-list .dropped-title { color: var(--text-muted); text-decoration: line-through; }

  /* favorites: a JS-populated section at the top showing every listing the
     user has starred, regardless of region/property-type. Cloned from the
     originals further down the page so click handlers (event-delegated)
     keep working from either copy. */
  .favorites { margin: 0 0 2rem; }
  .favorites-h {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid var(--border);
    letter-spacing: -0.01em;
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }
  .favorites-h .star { color: var(--boost); }
  .favorites-count {
    font-weight: 400;
    color: var(--text-faint);
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }
  /* Compact-row clones from still-active/stale sections render inside a
     bare ul.listings rather than inside a details-wrapped compact-list, so
     give them a card-like outer frame for visual consistency. */
  #favorites-list .compact-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 0.55rem;
    align-items: center;
    padding: 0.55rem 0.85rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 0.5rem;
    box-shadow: var(--shadow);
    font-size: 0.92rem;
  }
  #favorites-list .compact-row .price { font-weight: 700; }

  .quiet-note { margin-top: 1.5rem; }
  .quiet-note summary { color: var(--text-faint); }
  .quiet-note ul { list-style: none; padding-left: 1.2rem; color: var(--text-faint); font-size: 0.85rem; }

  .footer {
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    font-size: 0.78rem;
    color: var(--text-faint);
    line-height: 1.6;
  }
  .footer .src-fail { color: #d44; font-weight: 700; }

  /* --- status tracking (localStorage) --- */
  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.75rem;
    align-items: center;
    margin: 0 0 1rem;
    padding: 0.55rem 0.75rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.85rem;
  }
  .filter-bar label {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }
  .filter-bar input[type="checkbox"] { accent-color: var(--accent); }
  .filter-bar .filter-counts {
    margin-left: auto;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }
  .filter-bar .filter-counts .star { color: var(--boost); }
  .filter-bar .filter-counts .contacted { color: var(--link); }

  .status-controls {
    display: inline-flex;
    gap: 0.2rem;
    margin-left: auto;
  }
  .status-controls.compact { margin-left: 0.2rem; }
  .status-btn {
    appearance: none;
    -webkit-appearance: none;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-faint);
    border-radius: 6px;
    padding: 0.15rem 0.4rem;
    font-size: 0.85rem;
    line-height: 1.1;
    cursor: pointer;
    transition: background 0.1s, color 0.1s, border-color 0.1s;
  }
  .status-btn:hover { background: var(--surface-2); color: var(--text); }
  .status-btn[aria-pressed="true"] { color: var(--text); border-color: transparent; }
  .status-btn[data-status="interested"][aria-pressed="true"] {
    background: var(--new-bg);
    color: var(--new-text);
  }
  .status-btn[data-status="contacted"][aria-pressed="true"] {
    background: var(--accent-bg);
    color: var(--accent);
  }
  .status-btn[data-status="dismissed"][aria-pressed="true"] {
    background: var(--surface-2);
    color: var(--text-muted);
  }

  /* card decorations driven by data-status attribute set by JS */
  .card[data-status="interested"] { box-shadow: inset 4px 0 0 var(--boost), var(--shadow); }
  .card[data-status="contacted"] { box-shadow: inset 4px 0 0 var(--accent), var(--shadow); }
  .compact-list li[data-status="interested"] .row-title { font-weight: 600; }
  .compact-list li[data-status="contacted"] .row-title::after {
    content: " ✉";
    color: var(--link);
    font-weight: 600;
  }

  /* dismissed: hide unless body.show-dismissed; show as faded when revealed */
  body:not(.show-dismissed) .card[data-status="dismissed"],
  body:not(.show-dismissed) .compact-list li[data-status="dismissed"] {
    display: none;
  }
  body.show-dismissed .card[data-status="dismissed"],
  body.show-dismissed .compact-list li[data-status="dismissed"] {
    opacity: 0.5;
  }

  /* only-interested filter: hide everything that isn't interested */
  body.only-interested .card:not([data-status="interested"]),
  body.only-interested .compact-list li:not([data-status="interested"]) {
    display: none;
  }
  /* in only-interested mode, collapse empty subsections gracefully */
  body.only-interested .empty-line { display: none; }

  /* only-drops filter: hide every listing that doesn't have a price drop.
     data-drop is set by tagDrops() on any [data-id] containing a .price-was
     descendant, so this picks up cards, compact rows, and favorites clones. */
  body.only-drops [data-id]:not([data-drop]) { display: none; }
  body.only-drops .empty-line { display: none; }

  @media (max-width: 600px) {
    body { padding: 0.75rem 0.85rem 3rem; font-size: 15px; }
    .card {
      grid-template-columns: 96px 1fr;
      gap: 0.7rem;
      padding: 0.65rem;
    }
    .card-thumb, .card-thumb-empty { width: 96px; }
    h1 { font-size: 1.4rem; }
    .region-header h2 { font-size: 1.15rem; }
    .status-btn { padding: 0.25rem 0.5rem; font-size: 0.95rem; }
  }
</style>
</head>
<body>

<header class="topbar">
  <span>{{ date_label }} &middot; 1 USD = {{ fx_rate }} JMD</span>
  <span class="nav-links">
    <a href="archive/">📚 archive</a>
  </span>
</header>

<h1>Jamaica property watch</h1>
<p class="summary">
  <span class="count-new">{{ total_new }} new</span> &middot;
  {% if total_drops %}<span class="count-drops" id="toggle-only-drops" role="button" tabindex="0" aria-pressed="false" title="Click to filter to price drops only">↓ {{ total_drops }} price drop{{ '' if total_drops == 1 else 's' }}</span> &middot;{% endif %}
  {{ total_active }} still active &middot;
  {{ total_stale }} stale &middot;
  {{ total_dropped }} dropped off
</p>

<div class="filter-bar" id="filter-bar" hidden>
  <label><input type="checkbox" id="filter-only-interested"> Only interested</label>
  <label><input type="checkbox" id="filter-show-dismissed"> Show dismissed</label>
  <span class="filter-counts" id="filter-counts"></span>
</div>

<section class="favorites" id="favorites-section" hidden>
  <h2 class="favorites-h">
    <span class="star">⭐</span> Favorites
    <span class="favorites-count" id="favorites-count"></span>
  </h2>
  <ul class="listings" id="favorites-list"></ul>
</section>

{% if regions %}
<nav class="region-jump" aria-label="region jump">
  {% for r in regions %}
    {% if r.has_anything %}
    <a class="region-chip{% if r.new_count %} has-new{% endif %}" href="#region-{{ r.slug }}">
      {{ r.name }}{% if r.new_count %} <span class="region-chip-count">+{{ r.new_count }}</span>{% endif %}
    </a>
    {% else %}
    <span class="region-chip region-chip-empty" title="no listings tracked yet">{{ r.name }}</span>
    {% endif %}
  {% endfor %}
</nav>
{% endif %}

{% for region in active_regions %}
<section class="region" id="region-{{ region.slug }}">
  <div class="region-header">
    <h2>{{ region.name }}</h2>
    <div class="region-stats">
      {% if region.new_count %}<span class="count-new">{{ region.new_count }} new</span> &middot; {% endif %}
      {{ region.active_count }} active{% if region.stale_count %} &middot; {{ region.stale_count }} stale{% endif %}{% if region.dropped_count %} &middot; {{ region.dropped_count }} dropped{% endif %}
    </div>
  </div>

  {% for section in region.visible_sections %}
  <div class="subsection">
    <h3>{{ section.icon }} {{ section.label }}{% if section.budget_label %}<span class="budget">{{ section.budget_label }}</span>{% endif %}</h3>

    {% if section.new_since_last_run %}
      <ul class="listings">
      {% for L in section.new_since_last_run %}
        <li class="card is-new{% if L.keyword_boost %} is-boost{% endif %}"{% if L.track_id %} data-id="{{ L.track_id }}"{% endif %}>
          {% if L.photo_url %}
          <a class="card-thumb-link" href="{{ L.primary_url }}" tabindex="-1"><img class="card-thumb" src="{{ L.photo_url }}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.classList.add('hidden')"></a>
          {% else %}
          <div class="card-thumb-empty"></div>
          {% endif %}
          <div class="card-body">
            <div class="card-line1">
              <span class="pill pill-new">New</span>
              {% if L.keyword_boost %}<span class="pill-boost" title="matches boost keywords">⭐</span>{% endif %}
              <span class="card-price">{{ L.price_label }}</span>
              {% if L.price_was_label %}<span class="price-was">↓ {{ L.price_was_label }}</span>{% endif %}
            </div>
            <p class="card-title"><a href="{{ L.primary_url }}">{{ L.title }}</a></p>
            {% if L.location_text %}
            <div class="card-loc{% if L.location_confidence != 'exact' %} card-loc-approx{% endif %}">{{ L.location_text }}</div>
            {% endif %}
            <div class="card-meta">
              {% if L.primary_source %}<span class="src-pill">{{ L.primary_source }}</span>{% endif %}
              {% if L.other_sources %}
              <span class="also-at">also at:
                {% for src, url in L.other_sources %}<a href="{{ url }}">{{ src }}</a>{% endfor %}
              </span>
              {% endif %}
              <span>first seen {{ L.first_seen_label }}{% if L.listed_on_iso %} &middot; listed {{ L.listed_on_label }}{% endif %}</span>
              {% if L.track_id %}
              <span class="status-controls" role="group" aria-label="status">
                <button type="button" class="status-btn" data-status="interested" aria-pressed="false" title="Mark as interested">⭐</button>
                <button type="button" class="status-btn" data-status="contacted" aria-pressed="false" title="Mark as contacted">✉</button>
                <button type="button" class="status-btn" data-status="dismissed" aria-pressed="false" title="Dismiss (hide)">✕</button>
              </span>
              {% endif %}
            </div>
          </div>
        </li>
      {% endfor %}
      </ul>
    {% else %}
      <p class="empty-line">{{ section.empty_line }}</p>
    {% endif %}

    {% if section.still_active %}
    <details>
      <summary>{{ section.still_active|length }} still active</summary>
      <ul class="compact-list">
        {% for L in section.still_active %}
        <li{% if L.track_id %} data-id="{{ L.track_id }}"{% endif %}>
          <span class="price">{{ L.price_label }}</span>
          {% if L.price_was_label %}<span class="price-was">↓ {{ L.price_was_label }}</span>{% endif %}
          <span class="row-title"><a href="{{ L.primary_url }}">{{ L.title|truncate(70) }}</a></span>
          {% if L.primary_source %}<span class="src-pill">{{ L.primary_source }}</span>{% endif %}
          {% if L.other_sources %}<span class="age">+{{ L.other_sources|length }} other</span>{% endif %}
          <span class="age">first seen {{ L.first_seen_label }}</span>
          {% if L.track_id %}
          <span class="status-controls compact" role="group" aria-label="status">
            <button type="button" class="status-btn" data-status="interested" aria-pressed="false" title="Mark as interested">⭐</button>
            <button type="button" class="status-btn" data-status="contacted" aria-pressed="false" title="Mark as contacted">✉</button>
            <button type="button" class="status-btn" data-status="dismissed" aria-pressed="false" title="Dismiss (hide)">✕</button>
          </span>
          {% endif %}
        </li>
        {% endfor %}
      </ul>
    </details>
    {% endif %}

    {% if section.stale %}
    <details>
      <summary>{{ section.stale|length }} stale (90+ days)</summary>
      <ul class="compact-list">
        {% for L in section.stale %}
        <li{% if L.track_id %} data-id="{{ L.track_id }}"{% endif %}>
          <span class="price">{{ L.price_label }}</span>
          <span class="row-title"><a href="{{ L.primary_url }}">{{ L.title|truncate(70) }}</a></span>
          {% if L.primary_source %}<span class="src-pill">{{ L.primary_source }}</span>{% endif %}
          <span class="age">first seen {{ L.first_seen_label }}</span>
          {% if L.track_id %}
          <span class="status-controls compact" role="group" aria-label="status">
            <button type="button" class="status-btn" data-status="interested" aria-pressed="false" title="Mark as interested">⭐</button>
            <button type="button" class="status-btn" data-status="contacted" aria-pressed="false" title="Mark as contacted">✉</button>
            <button type="button" class="status-btn" data-status="dismissed" aria-pressed="false" title="Dismiss (hide)">✕</button>
          </span>
          {% endif %}
        </li>
        {% endfor %}
      </ul>
    </details>
    {% endif %}

    {% if section.dropped_off %}
    <details>
      <summary>{{ section.dropped_off|length }} dropped off this run</summary>
      <ul class="compact-list">
        {% for L in section.dropped_off %}
        <li>
          <span class="price">{{ L.price_label }}</span>
          <span class="dropped-title">{{ L.title|truncate(70) }}</span>
          {% if L.primary_source %}<span class="src-pill">{{ L.primary_source }}</span>{% endif %}
          <span class="age">URL likely 404</span>
        </li>
        {% endfor %}
      </ul>
    </details>
    {% endif %}
  </div>
  {% endfor %}
</section>
{% endfor %}

{% if quiet_regions %}
<details class="quiet-note">
  <summary>{{ quiet_regions|length }} quiet region{{ '' if quiet_regions|length == 1 else 's' }} (no listings tracked yet)</summary>
  <ul>{% for r in quiet_regions %}<li>{{ r.name }}</li>{% endfor %}</ul>
</details>
{% endif %}

<footer class="footer">
  Generated {{ run_iso }}.<br>
  {% if sources_counts %}
  Per-source counts:
  {% for name, count in sources_counts.items() %}{% if count < 0 %}<span class="src-fail">{{ name }}=FAILED</span>{% else %}{{ name }}={{ count }}{% endif %}{% if not loop.last %} &middot; {% endif %}{% endfor %}.
  {% else %}
  Sources: {{ sources_label }}.
  {% endif %}
  {% if notes %}<br>Notes: {{ notes }}{% endif %}
</footer>

<script>
(function () {
  // Per-listing status persisted in localStorage. Keyed by track_id (canonical_id
  // when available, stable_id otherwise). One status per listing — mutually
  // exclusive (interested / contacted / dismissed). Clicking the active button
  // clears the status. Filter prefs persist separately.
  var STATUS_KEY = 'kw7m_status_v1';
  var FILTER_KEY = 'kw7m_filters_v1';

  function readJSON(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }
  function writeJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  }

  var statuses = readJSON(STATUS_KEY, {}) || {};
  var filters = readJSON(FILTER_KEY, {showDismissed: false, onlyInterested: false, onlyDrops: false}) || {};

  function applyRow(el) {
    var id = el.getAttribute('data-id');
    if (!id) return;
    var s = statuses[id] && statuses[id].s;
    if (s) {
      el.setAttribute('data-status', s);
    } else {
      el.removeAttribute('data-status');
    }
    var btns = el.querySelectorAll('.status-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', btns[i].getAttribute('data-status') === s ? 'true' : 'false');
    }
  }

  function applyAll() {
    var rows = document.querySelectorAll('[data-id]');
    for (var i = 0; i < rows.length; i++) applyRow(rows[i]);
    document.body.classList.toggle('show-dismissed', !!filters.showDismissed);
    document.body.classList.toggle('only-interested', !!filters.onlyInterested);
    document.body.classList.toggle('only-drops', !!filters.onlyDrops);
    tagDrops();
    updateCounts();
    refreshFavorites();
  }

  function tagDrops() {
    // Mark every [data-id] row that contains a .price-was as data-drop="1"
    // so the only-drops filter can target it. Idempotent — also re-applied
    // to clones inside #favorites-list.
    var rows = document.querySelectorAll('[data-id]');
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].querySelector('.price-was')) {
        rows[i].setAttribute('data-drop', '1');
      } else {
        rows[i].removeAttribute('data-drop');
      }
    }
  }

  function refreshFavorites() {
    var section = document.getElementById('favorites-section');
    var list = document.getElementById('favorites-list');
    var countEl = document.getElementById('favorites-count');
    if (!section || !list) return;

    // Collect ids whose status === 'interested'.
    var starred = [];
    for (var id in statuses) {
      if (Object.prototype.hasOwnProperty.call(statuses, id)
          && statuses[id] && statuses[id].s === 'interested') {
        starred.push(id);
      }
    }

    // Rebuild from scratch — cheap (single-digit clones in practice) and
    // avoids tracking which clones came from which star toggle.
    list.innerHTML = '';
    var added = 0;
    starred.forEach(function (id) {
      var matches = document.querySelectorAll('[data-id="' + cssEscape(id) + '"]');
      // Skip any matches that live inside the favorites list itself —
      // we want to clone the canonical instance from a region section.
      var original = null;
      for (var i = 0; i < matches.length; i++) {
        if (!list.contains(matches[i])) { original = matches[i]; break; }
      }
      if (!original) return;
      var clone = original.cloneNode(true);
      // Compact-list rows have no card chrome; tag clones so CSS can give
      // them a card-like frame inside #favorites-list.
      if (original.tagName === 'LI' && !clone.classList.contains('card')) {
        clone.classList.add('compact-row');
      }
      list.appendChild(clone);
      added++;
    });

    section.hidden = added === 0;
    if (countEl) countEl.textContent = added ? '(' + added + ')' : '';
    // Re-tag clones so they participate in the only-drops filter too.
    tagDrops();
  }

  function updateCounts() {
    var n = {interested: 0, contacted: 0, dismissed: 0};
    for (var id in statuses) {
      if (Object.prototype.hasOwnProperty.call(statuses, id)) {
        var s = statuses[id] && statuses[id].s;
        if (n.hasOwnProperty(s)) n[s]++;
      }
    }
    var el = document.getElementById('filter-counts');
    if (!el) return;
    var parts = [];
    if (n.interested) parts.push('<span class="star">⭐ ' + n.interested + ' interested</span>');
    if (n.contacted) parts.push('<span class="contacted">✉ ' + n.contacted + ' contacted</span>');
    if (n.dismissed) parts.push(n.dismissed + ' dismissed');
    el.innerHTML = parts.join(' &middot; ');
  }

  function setStatus(id, newStatus) {
    if (!id) return;
    if (newStatus) {
      statuses[id] = {s: newStatus, ts: Date.now()};
    } else {
      delete statuses[id];
    }
    writeJSON(STATUS_KEY, statuses);
    var rows = document.querySelectorAll('[data-id="' + cssEscape(id) + '"]');
    for (var i = 0; i < rows.length; i++) applyRow(rows[i]);
    updateCounts();
    refreshFavorites();
  }

  function cssEscape(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/["\\\\]/g, '\\\\$&');
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('.status-btn');
    if (!btn) return;
    ev.preventDefault();
    var row = btn.closest('[data-id]');
    if (!row) return;
    var id = row.getAttribute('data-id');
    var clicked = btn.getAttribute('data-status');
    var current = statuses[id] && statuses[id].s;
    setStatus(id, current === clicked ? null : clicked);
  });

  function bindFilter(checkboxId, key) {
    var cb = document.getElementById(checkboxId);
    if (!cb) return;
    cb.checked = !!filters[key];
    cb.addEventListener('change', function () {
      filters[key] = cb.checked;
      writeJSON(FILTER_KEY, filters);
      document.body.classList.toggle(checkboxId === 'filter-show-dismissed' ? 'show-dismissed' : 'only-interested', cb.checked);
    });
  }

  // Reveal the filter bar only when JS is active (it's hidden by default so
  // a JS-disabled visitor doesn't see non-functional toggles).
  var bar = document.getElementById('filter-bar');
  if (bar) bar.removeAttribute('hidden');

  bindFilter('filter-show-dismissed', 'showDismissed');
  bindFilter('filter-only-interested', 'onlyInterested');

  var dropsToggle = document.getElementById('toggle-only-drops');
  if (dropsToggle) {
    function syncDropsToggle() {
      dropsToggle.setAttribute('aria-pressed', filters.onlyDrops ? 'true' : 'false');
    }
    function flipDrops() {
      filters.onlyDrops = !filters.onlyDrops;
      writeJSON(FILTER_KEY, filters);
      document.body.classList.toggle('only-drops', !!filters.onlyDrops);
      syncDropsToggle();
    }
    dropsToggle.addEventListener('click', flipDrops);
    dropsToggle.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        flipDrops();
      }
    });
    syncDropsToggle();
  }

  applyAll();
})();
</script>

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
  :root {
    --bg: #fafaf6; --surface: #ffffff; --text: #1c1c1c; --text-faint: #8a8a8a;
    --border: #e6e3da; --link: #0a5a8d;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #15181a; --surface: #1e2123; --text: #ececec; --text-faint: #7a7a7a;
      --border: #353a3d; --link: #6db8ee;
    }
  }
  body {
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 600px; margin: 0 auto; padding: 1.5rem 1.25rem 3rem;
    line-height: 1.6;
  }
  a { color: var(--link); }
  h1 { font-size: 1.4rem; margin: 0 0 1rem; letter-spacing: -0.01em; }
  .back { color: var(--text-faint); font-size: 0.85rem; }
  ul { list-style: none; padding: 0; margin: 1rem 0 0; }
  li { padding: 0.5rem 0; border-bottom: 1px dashed var(--border); }
  li:last-child { border-bottom: 0; }
</style>
</head>
<body>
<p><a class="back" href="../">&larr; latest</a></p>
<h1>Past digests</h1>
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
        # Show the source's original price for any non-USD currency so the
        # listing's local-currency ask is visible alongside the converted
        # USD figure. JMD/GBP/CAD/EUR all qualify; 'unknown' means we
        # couldn't classify so don't pretend.
        if cur and cur not in ("USD", "unknown") and original:
            # Real-world price strings often contain newlines and run-on
            # spaces from source HTML — collapse them so the label renders
            # on one line.
            cleaned = re.sub(r"\s+", " ", original).strip()
            s += f" (was {cleaned})"
        return s
    return original or "price unknown"


SOURCE_RANK = {
    "xposure": 1,
    "realtor_com_intl": 2,
    "cb_jamaica": 3,
    "remax_elite": 4,
    "century21_jm": 5,
    "caribbean_mls": 6,
    "golden_gates": 7,
    "millennium": 8,
    "keez": 9,
}


def _relative_time(iso: str | None, now: datetime | None = None) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso[:10]
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    days = delta.days
    if days < 0:
        return "in the future"
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = max(1, days // 30)
        return f"{months} month{'s' if months > 1 else ''} ago"
    years = max(1, days // 365)
    return f"{years} year{'s' if years > 1 else ''} ago"


def _row_to_view(
    row: dict,
    price_drops: dict[str, tuple[int, int]] | None = None,
) -> dict:
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
    out["first_seen_label"] = _relative_time(row.get("first_seen_iso"))
    out["listed_on_label"] = _relative_time(row.get("listed_on_iso")) if row.get("listed_on_iso") else ""
    # Stable identity for client-side status tracking (localStorage keys).
    # canonical_id is preferred; stable_id is the legacy fallback.
    out["track_id"] = row.get("canonical_id") or row.get("stable_id") or ""
    out["price_was_label"] = ""
    if price_drops:
        cid = row.get("canonical_id")
        if cid and cid in price_drops:
            old, _new = price_drops[cid]
            out["price_was_label"] = f"was ${old:,} USD"
    return out


_EMPTY_LINES = {
    "home": "No new homes this run.",
    "land": "No new land this run.",
    "unknown": "No new uncategorized listings this run.",
}


def _empty_section(pt: str, region) -> dict:
    if pt == "home":
        budget_label = f"≤ ${region.home_budget_usd:,} USD" if region else ""
    elif pt == "land":
        budget_label = f"≤ ${region.land_budget_usd:,} USD" if region else ""
    else:
        budget_label = ""
    return {
        "key": pt,
        "label": PROPERTY_TYPE_LABELS[pt],
        "label_lower": PROPERTY_TYPE_LABELS[pt].lower(),
        "icon": PROPERTY_TYPE_ICONS[pt],
        "budget_label": budget_label,
        "empty_line": _EMPTY_LINES[pt],
        "new_since_last_run": [],
        "still_active": [],
        "stale": [],
        "dropped_off": [],
    }


def _empty_region_buckets(slug: str, name: str, region=None) -> dict:
    return {
        "slug": slug,
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
    price_drops: dict[str, tuple[int, int]] | None = None,
) -> tuple[str, str]:
    """Returns (page_title, html)."""
    by_region: dict[str, dict] = {}
    for r in REGIONS:
        by_region[r.slug] = _empty_region_buckets(r.slug, r.name, r)

    def assign(rows: list[dict], key: str) -> None:
        for row in rows:
            view = _row_to_view(row, price_drops=price_drops)
            slugs = regions_for(row) or [REGIONS[0].slug]
            pt = (row.get("property_type") or "unknown").lower()
            if pt not in PROPERTY_TYPE_ORDER:
                pt = "unknown"
            for slug in slugs:
                region = by_slug(slug)
                bucket = by_region.setdefault(
                    slug,
                    _empty_region_buckets(slug, region.name if region else slug, region),
                )
                bucket["sections"][pt][key].append(view)

    assign(buckets.new_since_last_run, "new_since_last_run")
    assign(buckets.still_active, "still_active")
    assign(buckets.stale, "stale")
    assign(buckets.dropped_off, "dropped_off")

    region_views = list(by_region.values())
    for v in region_views:
        v["visible_sections"] = [
            v["sections"][pt]
            for pt in PROPERTY_TYPE_ORDER
            if pt in ("home", "land") or _section_has_anything(v["sections"][pt])
        ]
        v["new_count"] = sum(len(s["new_since_last_run"]) for s in v["sections"].values())
        v["active_count"] = sum(len(s["still_active"]) for s in v["sections"].values())
        v["stale_count"] = sum(len(s["stale"]) for s in v["sections"].values())
        v["dropped_count"] = sum(len(s["dropped_off"]) for s in v["sections"].values())
        v["has_anything"] = (
            v["new_count"] + v["active_count"] + v["stale_count"] + v["dropped_count"] > 0
        )

    active_regions = [v for v in region_views if v["has_anything"]]
    quiet_regions = [v for v in region_views if not v["has_anything"]]

    total_new = sum(v["new_count"] for v in region_views)
    total_active = sum(v["active_count"] for v in region_views)
    total_stale = sum(v["stale_count"] for v in region_views)
    total_dropped = sum(v["dropped_count"] for v in region_views)
    total_drops = len(price_drops or {})

    date_label = date.today().isoformat()
    per_region_new = ", ".join(
        f"{v['name']}: {v['new_count']}"
        for v in region_views
        if v["new_count"]
    )
    subject = f"Jamaica property watch — {date_label} — {total_new} new" + (
        f" ({per_region_new})" if per_region_new else ""
    )
    html = PAGE_TEMPLATE.render(
        subject=subject,
        date_label=date_label,
        fx_rate=f"{fx_rate:.2f}",
        regions=region_views,
        active_regions=active_regions,
        quiet_regions=quiet_regions,
        total_new=total_new,
        total_active=total_active,
        total_stale=total_stale,
        total_dropped=total_dropped,
        total_drops=total_drops,
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
