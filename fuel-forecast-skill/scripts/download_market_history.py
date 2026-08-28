#!/usr/bin/env python3
"""Build a leakage-safe market history aligned to bootstrap fuel dates.

For each date in bootstrap_noon.jsonl, only observations published before that
calendar date are used. This intentionally maps a fuel target to the previous
available futures close/reference rate, never to a same-day close that happened
after the 11:50 target.

Outputs:
- bootstrap_market.jsonl
- bootstrap_market_manifest.json
"""
from __future__ import annotations

import bisect
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from common import data_dir, load_json, read_jsonl, save_json, pct_change
from market import UA, yahoo_series_between

ECB_HISTORY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
US_GALLON_LITERS = 3.785411784


def dated_values(rows):
    """Convert Yahoo timestamp/value rows to one UTC-date close per day."""
    by_date = {}
    for timestamp, value in rows:
        day = datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat()
        by_date[day] = float(value)
    return sorted(by_date.items())


def fetch_ecb_eurusd_history():
    """Return the ECB's complete USD-per-EUR reference-rate history."""
    req = urllib.request.Request(ECB_HISTORY_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.parse(response).getroot()
    rows = []
    for day_node in root.iter():
        day = day_node.attrib.get("time")
        if not day:
            continue
        for child in list(day_node):
            if child.attrib.get("currency") == "USD":
                rows.append((day, float(child.attrib["rate"])))
                break
    return sorted(rows)


def combine_cost_with_fx(cost_rows, fx_rows, divisor=1.0):
    """Convert a USD cost series to EUR using the latest ECB rate on that day."""
    fx_dates = [d for d, _ in fx_rows]
    fx_values = [v for _, v in fx_rows]
    out = []
    for day, usd_value in cost_rows:
        pos = bisect.bisect_right(fx_dates, day) - 1
        if pos >= 0 and fx_values[pos] not in (None, 0):
            out.append((day, float(usd_value) / fx_values[pos] / divisor))
    return out


def snapshot_before(rows, target_day):
    """Describe the latest point strictly before target_day plus trading lags."""
    dates = [d for d, _ in rows]
    values = [v for _, v in rows]
    pos = bisect.bisect_left(dates, target_day) - 1
    if pos < 0:
        return {}
    latest = values[pos]

    def change(points):
        old_pos = pos - points
        return pct_change(latest, values[old_pos]) if old_pos >= 0 else None

    return {
        "source_date": dates[pos],
        "latest": latest,
        "d1_pct": change(1),
        "d5_pct": change(5),
        "d10_pct": change(10),
    }


def main():
    target_dir = data_dir()
    config = load_json(target_dir / "config.json")
    if not config:
        raise SystemExit(f"Missing {target_dir/'config.json'}")

    fuel_rows = read_jsonl(target_dir / "bootstrap_noon.jsonl")
    target_dates = sorted({r.get("date") for r in fuel_rows if r.get("date")})
    if not target_dates:
        raise SystemExit("Missing bootstrap_noon.jsonl; run the tankzeit bootstrap first.")

    first = date.fromisoformat(target_dates[0])
    last = date.fromisoformat(target_dates[-1])
    # Extra history is required for d10 and holiday/weekend gaps.
    fetch_start = first - timedelta(days=35)
    fetch_end = max(last, date.today())
    market_config = config.get("market", {})
    brent_symbol = market_config.get("brent_symbol", "BZ=F")
    distillate_symbol = market_config.get("distillate_symbol", "HO=F")

    print(f"Fetching {brent_symbol} history {fetch_start} .. {fetch_end}...")
    brent = dated_values(yahoo_series_between(brent_symbol, fetch_start, fetch_end))
    print(f"Fetching {distillate_symbol} history {fetch_start} .. {fetch_end}...")
    distillate = dated_values(
        yahoo_series_between(distillate_symbol, fetch_start, fetch_end)
    )
    print("Fetching ECB EUR/USD history...")
    eurusd = fetch_ecb_eurusd_history()

    brent_eur = combine_cost_with_fx(brent, eurusd)
    distillate_eur_liter = combine_cost_with_fx(
        distillate, eurusd, divisor=US_GALLON_LITERS
    )

    output_rows = []
    for target_day in target_dates:
        row = {
            "version": 1,
            "date": target_day,
            "alignment": "latest published value strictly before fuel target date",
            "brent_usd_per_barrel": snapshot_before(brent, target_day),
            "distillate_usd_per_gallon": snapshot_before(distillate, target_day),
            "eurusd_usd_per_eur": snapshot_before(eurusd, target_day),
            "brent_eur_per_barrel": snapshot_before(brent_eur, target_day),
            "distillate_eur_per_liter": snapshot_before(
                distillate_eur_liter, target_day
            ),
        }
        output_rows.append(row)

    output = target_dir / "bootstrap_market.jsonl"
    output.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in output_rows
        ),
        encoding="utf-8",
    )

    complete = sum(
        1 for row in output_rows
        if row["brent_eur_per_barrel"].get("latest") is not None
        and row["distillate_eur_per_liter"].get("latest") is not None
        and row["eurusd_usd_per_eur"].get("latest") is not None
    )
    manifest = {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "alignment": "strictly previous available close/reference; no same-day look-ahead",
        "fuel_dates": len(target_dates),
        "complete_dates": complete,
        "first_date": target_dates[0],
        "last_date": target_dates[-1],
        "fetch_start": fetch_start.isoformat(),
        "fetch_end": fetch_end.isoformat(),
        "series": {
            "brent": {
                "symbol": brent_symbol,
                "source": "Yahoo Finance chart JSON",
                "points": len(brent),
                "first": brent[0][0] if brent else None,
                "last": brent[-1][0] if brent else None,
            },
            "distillate": {
                "symbol": distillate_symbol,
                "source": "Yahoo Finance Heating Oil futures proxy",
                "points": len(distillate),
                "first": distillate[0][0] if distillate else None,
                "last": distillate[-1][0] if distillate else None,
            },
            "eurusd": {
                "source": "ECB euro foreign exchange reference rates",
                "unit": "USD per EUR",
                "points": len(eurusd),
                "first": eurusd[0][0] if eurusd else None,
                "last": eurusd[-1][0] if eurusd else None,
            },
        },
        "derived": {
            "brent_eur_per_barrel": "Brent USD per barrel / USD per EUR",
            "distillate_eur_per_liter": (
                "Heating Oil USD per US gallon / USD per EUR / 3.785411784"
            ),
        },
        "output": str(output),
    }
    save_json(target_dir / "bootstrap_market_manifest.json", manifest)

    print("Market bootstrap finished.")
    print(f"Dates: {complete}/{len(target_dates)} complete "
          f"({target_dates[0]} .. {target_dates[-1]})")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
