#!/usr/bin/env python3
"""Deterministic point-in-time news scoring and event deduplication."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from common import append_jsonl, clamp, load_json, read_jsonl, save_json

DEFAULT_PERSISTENCE_HOURS = {
    "opec_policy": 120.0,
    "sanctions_export_policy": 120.0,
    "geopolitics_shipping": 96.0,
    "refinery_outage": 72.0,
    "distillate_supply": 72.0,
    "inventory_demand": 36.0,
    "macro_fx": 24.0,
    "market_commentary": 18.0,
    "other": 36.0,
}


def parse_timestamp(value):
    if not value:
        return None, False
    text = str(value).strip()
    precise = "T" in text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, precise
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
        precise = False
    return parsed.astimezone(timezone.utc), precise


def draft_fingerprint(draft):
    encoded = json.dumps(
        draft, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def update_id(event):
    explicit = str(event.get("update_id") or "").strip()
    if explicit:
        return explicit
    sources = event.get("sources", []) if isinstance(event.get("sources"), list) else []
    identity = {
        "event_id": event.get("event_id"),
        "published_at": event.get("published_at"),
        "source_urls": sorted(str(source.get("url") or "") for source in sources),
        "reason": event.get("reason"),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def publication_time(event):
    parsed, precise = parse_timestamp(event.get("published_at"))
    if parsed:
        return parsed, precise
    candidates = []
    for source in event.get("sources", []):
        source_time, source_precise = parse_timestamp(source.get("published_at"))
        if source_time:
            candidates.append((source_time, source_precise))
    if not candidates:
        return None, False
    # The newest source/update is the point at which this event became known.
    return max(candidates, key=lambda item: item[0])


def recency_weight(age_hours, status, persistence_hours):
    if age_hours < 0:
        return 0.0
    if age_hours <= 24.0:
        return 1.0
    if age_hours <= 48.0:
        # Continuous decay from full weight to 55 percent.
        return 1.0 - 0.45 * ((age_hours - 24.0) / 24.0)
    if status not in ("ongoing", "updated"):
        return 0.0
    # Older events survive only when explicitly ongoing/updated.
    return 0.55 * math.pow(0.5, (age_hours - 48.0) / persistence_hours)


def score_news_draft(draft, now, history_rows=None):
    history_rows = history_rows or []
    seen_counts = {}
    for row in history_rows:
        key = (row.get("event_id"), row.get("update_id"))
        seen_counts[key] = seen_counts.get(key, 0) + 1

    warnings = []
    processed_events = []
    history_entries = []
    raw_score = 0.0
    effective_score = 0.0
    confidence_weighted = 0.0
    confidence_denominator = 0.0
    priced_weighted = 0.0
    priced_denominator = 0.0

    for raw_event in draft.get("events", []):
        event = dict(raw_event)
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            warnings.append("event without event_id ignored")
            continue
        published, precise = publication_time(event)
        if not published:
            warnings.append(f"{event_id}: missing/invalid published_at; ignored")
            continue
        if not precise:
            warnings.append(f"{event_id}: published_at has no precise timezone/time")

        category = str(event.get("category") or "other")
        status = str(event.get("status") or "new")
        persistence = clamp(
            float(event.get("persistence_hours") or
                  DEFAULT_PERSISTENCE_HOURS.get(category, 36.0)),
            12.0,
            168.0,
        )
        age_hours = (now - published).total_seconds() / 3600.0
        if age_hours < -0.25:
            warnings.append(f"{event_id}: publication is in the future; ignored")

        impact = clamp(float(event.get("impact") or 0.0), -2.0, 2.0)
        confidence = clamp(float(event.get("confidence", 0.5)), 0.0, 1.0)
        novelty = clamp(float(event.get("novelty", 1.0)), 0.0, 1.0)
        already_priced = clamp(float(event.get("already_priced", 0.0)), 0.0, 1.0)
        current_update_id = update_id(event)
        repeat_count = seen_counts.get((event_id, current_update_id), 0)
        repeat_factor = 1.0
        if repeat_count:
            repeat_factor = max(0.08, 0.30 / math.sqrt(repeat_count))
        effective_novelty = min(novelty, repeat_factor)
        age_factor = recency_weight(age_hours, status, persistence)
        priced_factor = 1.0 - 0.70 * already_priced
        effective_impact = (
            impact * confidence * effective_novelty * age_factor * priced_factor
        )

        processed = {
            "event_id": event_id,
            "update_id": current_update_id,
            "category": category,
            "status": status,
            "published_at": published.isoformat(),
            "age_hours": round(max(0.0, age_hours), 2),
            "impact": impact,
            "confidence": confidence,
            "novelty": novelty,
            "effective_novelty": round(effective_novelty, 4),
            "already_priced": already_priced,
            "recency_weight": round(age_factor, 4),
            "persistence_hours": persistence,
            "repeat_count_before": repeat_count,
            "effective_impact": round(effective_impact, 4),
            "reason": str(event.get("reason") or ""),
            "sources": event.get("sources", [])[:5],
        }
        processed_events.append(processed)
        raw_score += impact
        effective_score += effective_impact
        confidence_weighted += confidence * abs(effective_impact)
        confidence_denominator += abs(effective_impact)
        priced_weighted += already_priced * abs(impact)
        priced_denominator += abs(impact)
        history_entries.append(processed)

    effective_score = clamp(effective_score, -3.0, 3.0)
    net_score = clamp(raw_score, -3.0, 3.0)
    final_confidence = (
        confidence_weighted / confidence_denominator
        if confidence_denominator else 0.0
    )
    aggregate_priced = (
        priced_weighted / priced_denominator if priced_denominator else 0.0
    )
    drivers = [
        {
            "factor": event["category"],
            "impact": event["impact"],
            "effective_impact": event["effective_impact"],
            "reason": event["reason"],
        }
        for event in sorted(
            processed_events, key=lambda item: abs(item["effective_impact"]),
            reverse=True,
        )[:8]
    ]
    sources = []
    seen_urls = set()
    for event in processed_events:
        for source in event["sources"]:
            url = source.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            sources.append(source)

    final = {
        "version": 2,
        "date": draft.get("date") or now.date().isoformat(),
        "generated_at": draft.get("generated_at") or now.isoformat(),
        "processed_at": now.isoformat(),
        "draft_fingerprint": draft_fingerprint(draft),
        "net_score": round(net_score, 4),
        "already_priced": round(aggregate_priced, 4),
        "effective_score": round(effective_score, 4),
        "confidence": round(final_confidence, 4),
        "summary": str(draft.get("summary") or ""),
        "drivers": drivers,
        "sources": sources[:12],
        "events": processed_events,
        "market_override": draft.get("market_override", {}),
        "scoring": {
            "age_windows": "0-24h full; 24-48h decay to 55%; >48h only ongoing/updated",
            "repeat_updates": "same event_id/update_id receives declining novelty",
            "priced_factor": "1 - 0.70 * already_priced",
        },
        "warnings": warnings,
    }
    return final, history_entries


def process_news_files(target_dir, context=None):
    draft_path = target_dir / "news_signal_draft.json"
    final_path = target_dir / "news_signal.json"
    final = load_json(final_path, {}) or {}
    draft = load_json(draft_path, {}) or {}
    if not draft:
        return final
    context_date = (context or {}).get("date")
    if context_date and draft.get("date") != context_date:
        return final
    fingerprint = draft_fingerprint(draft)
    if final.get("draft_fingerprint") == fingerprint:
        return final

    now, _ = parse_timestamp(
        draft.get("generated_at") or (context or {}).get("generated_at")
    )
    if now is None:
        now = datetime.now(timezone.utc)
    history_path = target_dir / "news_history.jsonl"
    processed, history_entries = score_news_draft(
        draft, now, read_jsonl(history_path)
    )
    save_json(final_path, processed)
    for event in history_entries:
        append_jsonl(history_path, {
            "version": 2,
            "run_date": processed["date"],
            "processed_at": processed["processed_at"],
            **event,
        })
    return processed
