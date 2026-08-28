#!/usr/bin/env python3
from common import data_dir, load_json
from news import process_news_files


def main():
    target_dir = data_dir()
    context = load_json(target_dir / "morning_context.json", {}) or {}
    signal = process_news_files(target_dir, context)
    if not signal:
        raise SystemExit("Missing news_signal_draft.json or existing news_signal.json")
    print(
        f"News v{signal.get('version', 1)}: "
        f"effective_score={signal.get('effective_score', 0):+.2f}, "
        f"events={len(signal.get('events', []))}"
    )
    print(target_dir / "news_signal.json")


if __name__ == "__main__":
    main()
