#!/usr/bin/env python3
"""Calibrate asymmetric model priors from paired fuel/market bootstraps."""
from __future__ import annotations

import argparse
import hashlib
from datetime import date

from common import data_dir, load_json, read_jsonl, save_json, add_days
from model import (MODEL_VERSION, FEATURE_NAMES, calibration_metrics,
                   constrain_bootstrap_asymmetry, feature_vector,
                   initial_weights, new_model, ridge_weights)

FEATURE_MODES = (
    "local_only",
    "usd_market_symmetric",
    "eur_market_symmetric",
    "eur_market_asymmetric",
)


def rows_by_date(rows, value_path=None):
    out = {}
    for row in rows:
        day = row.get("date")
        if not day:
            continue
        if value_path:
            value = row
            for key in value_path:
                value = value.get(key, {}) if isinstance(value, dict) else None
            if value is None:
                continue
        out[day] = row
    return out


def historical_local_trends(fuel, today):
    dates = sorted(day for day in fuel if day < today)
    if not dates:
        return 0.0, 0.0
    values = [(day, fuel[day]["metrics"]["cheap_reference"] * 100.0)
              for day in dates[-8:]]
    one = values[-1][1] - values[-2][1] if len(values) >= 2 else 0.0
    if len(values) >= 4:
        three = (values[-1][1] - values[-4][1]) / 3.0
    elif len(values) >= 2:
        three = (values[-1][1] - values[0][1]) / (len(values) - 1)
    else:
        three = 0.0
    return one, three


def market_value(row, section, field):
    value = row.get(section, {}).get(field)
    return float(value) if value is not None else 0.0


def _collapse_market_asymmetry(features):
    positions = {name: i for i, name in enumerate(FEATURE_NAMES)}
    for prefix in ("brent_eur_1d", "brent_eur_5d",
                   "distillate_eur_1d", "distillate_eur_5d"):
        up = positions[prefix + "_up"]
        down = positions[prefix + "_down"]
        # Up/down values are mutually exclusive and the down value is signed.
        features[up] += features[down]
        features[down] = 0.0
    return features


def historical_features(day, fuel, market, mode="eur_market_asymmetric"):
    if mode not in FEATURE_MODES:
        raise ValueError(f"Unknown feature mode: {mode}")
    local1, local3 = historical_local_trends(fuel, day)
    row = market[day]
    if mode == "local_only":
        return feature_vector(day, local1_ct=local1, local3_ct=local3)
    if mode == "usd_market_symmetric":
        brent_section = "brent_usd_per_barrel"
        distillate_section = "distillate_usd_per_gallon"
    else:
        brent_section = "brent_eur_per_barrel"
        distillate_section = "distillate_eur_per_liter"
    features = feature_vector(
        day,
        local1_ct=local1,
        local3_ct=local3,
        brent_eur_d1=market_value(row, brent_section, "d1_pct"),
        brent_eur_d5=market_value(row, brent_section, "d5_pct"),
        distillate_eur_d1=market_value(
            row, distillate_section, "d1_pct"
        ),
        distillate_eur_d5=market_value(
            row, distillate_section, "d5_pct"
        ),
        eurusd_d5=(
            market_value(row, "eurusd_usd_per_eur", "d5_pct")
            if mode == "eur_market_asymmetric" else 0.0
        ),
        news_domestic_supply=0.0,
        news_european_imports=0.0,
        news_global_crude_shipping=0.0,
    )
    if mode.endswith("_symmetric"):
        return _collapse_market_asymmetry(features)
    return features


def build_examples(fuel, market, horizon, mode="eur_market_asymmetric"):
    examples = []
    for issue_day in sorted(set(fuel) & set(market)):
        target_day = add_days(issue_day, horizon)
        if target_day not in fuel:
            continue
        x = historical_features(issue_day, fuel, market, mode=mode)
        target = ((fuel[target_day]["metrics"]["cheap_reference"] -
                   fuel[issue_day]["metrics"]["cheap_reference"]) * 100.0)
        examples.append({
            "issue_date": issue_day,
            "target_date": target_day,
            "x": x,
            "target": target,
        })
    return examples


def fit_horizon(horizon, examples, enforce_asymmetry=True):
    if len(examples) < 30:
        raise ValueError(f"Not enough bootstrap examples for horizon {horizon}")

    split_date = examples[int(len(examples) * 0.80)]["issue_date"]
    train = [e for e in examples if e["target_date"] < split_date]
    validation = [e for e in examples if e["issue_date"] >= split_date]
    train_pairs = [(e["x"], e["target"]) for e in train]
    validation_pairs = [(e["x"], e["target"]) for e in validation]

    candidates = []
    prior = initial_weights(horizon)
    if enforce_asymmetry:
        prior = constrain_bootstrap_asymmetry(prior, horizon)
    prior_metrics = calibration_metrics(prior, validation_pairs)
    candidates.append(("prior", None, prior, prior_metrics))
    for penalty in (10.0, 20.0, 40.0, 80.0):
        weights = ridge_weights(train_pairs, horizon, penalty)
        if enforce_asymmetry:
            weights = constrain_bootstrap_asymmetry(weights, horizon)
        metrics = calibration_metrics(weights, validation_pairs)
        candidates.append((f"ridge-{penalty:g}", penalty, weights, metrics))

    selected = min(candidates, key=lambda item: item[3]["mae_ct"])
    method, penalty, _, validation_metrics = selected
    full_pairs = [(e["x"], e["target"]) for e in examples]
    final_weights = (initial_weights(horizon) if penalty is None
                     else ridge_weights(full_pairs, horizon, penalty))
    if enforce_asymmetry:
        final_weights = constrain_bootstrap_asymmetry(final_weights, horizon)
    full_metrics = calibration_metrics(final_weights, full_pairs)

    model = new_model(horizon)
    model["weights"] = final_weights
    model["bootstrap_samples"] = len(examples)
    model["bootstrap_validation_samples"] = len(validation)
    model["bootstrap_mae_ct"] = validation_metrics["mae_ct"]
    model["bootstrap_full_mae_ct"] = full_metrics["mae_ct"]
    model["bootstrap_direction_hits"] = validation_metrics["direction_hits"]
    model["bootstrap_direction_total"] = validation_metrics["direction_total"]
    model["mae_ema_ct"] = max(1.2, validation_metrics["mae_ct"])
    model["calibration"] = {
        "method": method,
        "penalty": penalty,
        "split_date": split_date,
        "training_samples": len(train),
        "validation_samples": len(validation),
        "asymmetry": "separate EUR cost-rise and cost-fall features",
    }
    return model


def fingerprint(*paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true",
        help="replace calibrated weights even after real 11:50 learning began",
    )
    args = parser.parse_args()
    target_dir = data_dir()
    config = load_json(target_dir / "config.json")
    if not config:
        raise SystemExit(f"Missing {target_dir/'config.json'}")

    fuel_path = target_dir / "bootstrap_noon.jsonl"
    market_path = target_dir / "bootstrap_market.jsonl"
    fuel = rows_by_date(
        read_jsonl(fuel_path), ("metrics", "cheap_reference")
    )
    market = rows_by_date(read_jsonl(market_path))
    if not fuel or not market:
        raise SystemExit("Run both historical bootstrap downloaders first.")

    old = load_json(target_dir / "model.json", {}) or {}
    live_samples = sum(
        int(old.get(str(h), {}).get("samples", 0))
        for h in range(1, config.get("forecast", {}).get("days", 5))
    )
    source_fingerprint = fingerprint(fuel_path, market_path)
    if (old.get("bootstrap_fingerprint") == source_fingerprint
            and old.get("version") == MODEL_VERSION and not args.force):
        print("Bootstrap model calibration is already current.")
        return
    if live_samples and not args.force:
        raise SystemExit(
            "Refusing to replace weights after real 11:50 learning began; "
            "review first or rerun with --force."
        )

    models = {
        "version": MODEL_VERSION,
        "feature_names": FEATURE_NAMES,
        "intraday_offset_ct": old.get("intraday_offset_ct", -0.5),
        "trained_intraday_dates": old.get("trained_intraday_dates", []),
        "bootstrap_fingerprint": source_fingerprint,
        "bootstrap_fuel_dates": len(fuel),
        "bootstrap_market_dates": len(market),
        "bootstrap_calibrated_at": date.today().isoformat(),
        "bootstrap_target": "tankzeit noon movement only; not absolute 11:50 level",
    }
    days = config.get("forecast", {}).get("days", 5)
    for horizon in range(1, days):
        examples = build_examples(fuel, market, horizon)
        models[str(horizon)] = fit_horizon(horizon, examples)
        calibrated = models[str(horizon)]
        print(
            f"h{horizon}: {calibrated['bootstrap_samples']} rows, "
            f"validation MAE {calibrated['bootstrap_mae_ct']:.2f} ct, "
            f"{calibrated['calibration']['method']}"
        )

    save_json(target_dir / "model.json", models)
    pending = load_json(target_dir / "pending_training.json", []) or []
    compatible_pending = [
        row for row in pending if len(row.get("x", [])) == len(FEATURE_NAMES)
    ]
    save_json(target_dir / "pending_training.json", compatible_pending)
    print(f"Saved model version {MODEL_VERSION} to {target_dir/'model.json'}")


if __name__ == "__main__":
    main()
