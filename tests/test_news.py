import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from common import read_jsonl
from news import process_news_files, score_news_draft


NOW = datetime(2026, 8, 28, 7, 0, tzinfo=timezone.utc)


def event(published_at, status="new"):
    return {
        "event_id": "refinery-example",
        "update_id": "outage-start",
        "category": "refinery_outage",
        "status": status,
        "published_at": published_at,
        "impact": 2.0,
        "confidence": 1.0,
        "novelty": 1.0,
        "already_priced": 0.0,
        "persistence_hours": 72,
        "reason": "test",
        "sources": [],
    }


def draft(item):
    return {
        "version": 2,
        "date": "2026-08-28",
        "generated_at": NOW.isoformat(),
        "summary": "test",
        "events": [item],
        "market_override": {},
    }


def test_age_windows():
    recent, _ = score_news_draft(draft(event("2026-08-28T01:00:00Z")), NOW)
    assert recent["effective_score"] == 2.0

    older, _ = score_news_draft(draft(event("2026-08-26T19:00:00Z")), NOW)
    assert older["events"][0]["age_hours"] == 36.0
    assert older["events"][0]["recency_weight"] == 0.775
    assert older["effective_score"] == 1.55

    expired, _ = score_news_draft(draft(event("2026-08-25T19:00:00Z")), NOW)
    assert expired["effective_score"] == 0.0
    ongoing, _ = score_news_draft(
        draft(event("2026-08-25T19:00:00Z", status="ongoing")), NOW
    )
    assert 0.9 < ongoing["effective_score"] < 1.1


def test_repeat_deduplication():
    history = [{"event_id": "refinery-example", "update_id": "outage-start"}]
    repeated, _ = score_news_draft(
        draft(event("2026-08-28T01:00:00Z")), NOW, history
    )
    assert repeated["events"][0]["effective_novelty"] == 0.3
    assert repeated["effective_score"] == 0.6


def test_file_processing_is_idempotent():
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory)
        payload = draft(event("2026-08-28T01:00:00Z"))
        (target / "news_signal_draft.json").write_text(json.dumps(payload))
        context = {"date": "2026-08-28", "generated_at": NOW.isoformat()}
        first = process_news_files(target, context)
        second = process_news_files(target, context)
        assert first == second
        assert len(read_jsonl(target / "news_history.jsonl")) == 1


def test_legacy_fallback():
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory)
        legacy = {"version": 1, "effective_score": 0.5}
        (target / "news_signal.json").write_text(json.dumps(legacy))
        assert process_news_files(target) == legacy


if __name__ == "__main__":
    test_age_windows()
    test_repeat_deduplication()
    test_file_processing_is_idempotent()
    test_legacy_fallback()
    print("OK")
