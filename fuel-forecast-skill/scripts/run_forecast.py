#!/usr/bin/env python3
from __future__ import annotations
from common import (data_dir, load_json, save_json, read_jsonl, append_jsonl,
                    add_days, clamp, median, write_jsonl)
from market import converted_pct
from model import (MODEL_VERSION, FEATURE_NAMES, feature_vector, is_compatible,
                   new_model, predict, update, confidence)
from news import process_news_files
from noon_reset import evaluate_noon_shadows, evaluation_summary

def observations_by_date(rows):
    out = {}
    for r in rows:
        if r.get("date") and r.get("metrics",{}).get("cheap_reference") is not None:
            out[r["date"]] = r
    return out

def _series_trends(source, dates):
    if not dates:
        return 0.0, 0.0
    vals = [(d, source[d]["metrics"]["cheap_reference"]*100.0) for d in dates[-8:]]
    one = vals[-1][1] - vals[-2][1] if len(vals) >= 2 else 0.0
    if len(vals) >= 4:
        three = (vals[-1][1] - vals[-4][1]) / 3.0
    elif len(vals) >= 2:
        three = (vals[-1][1] - vals[0][1]) / max(1, len(vals)-1)
    else:
        three = 0.0
    return one, three


def local_trend_selection(obs, today, bootstrap=None, noon_resets=None):
    """Select the freshest homogeneous local series for movement features.

    Absolute noon-reset levels never become 11:50 targets. Their day-to-day
    movement is a fallback when the authoritative pre-noon series has gaps.
    """
    candidates = []
    for priority, name, source in (
        (3, "pre_noon_observations", obs),
        (2, "noon_resets", noon_resets or {}),
        (1, "tankzeit_bootstrap_noon", bootstrap or {}),
    ):
        dates = sorted(day for day in source if day < today)
        if len(dates) >= 2:
            candidates.append((dates[-1], priority, name, source, dates))
    if not candidates:
        return 0.0, 0.0, "none"
    _, _, name, source, dates = max(candidates, key=lambda item: (item[0], item[1]))
    one, three = _series_trends(source, dates)
    return one, three, name


def local_trends(obs, today, bootstrap=None, noon_resets=None):
    one, three, _ = local_trend_selection(
        obs, today, bootstrap=bootstrap, noon_resets=noon_resets
    )
    return one, three

def getnum(dct, *path, default=0.0):
    cur = dct
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    try:
        return float(cur) if cur is not None else default
    except Exception:
        return default

def news_channel_scores(news, cfg=None):
    """Split residual news by configurable fuel transmission paths."""
    news_cfg = (cfg or {}).get("news", {}) or {}
    profile = news_cfg.get("profile") or (
        "diesel_europe" if (cfg or {}).get("fuel", "diesel") == "diesel"
        else "gasoline_europe"
    )
    defaults = {
        "diesel_europe": {
            "domestic_supply": {"domestic_refinery", "domestic_distribution", "refinery_outage"},
            "european_imports": {"european_diesel_imports", "gulf_distillate_shipping", "distillate_supply", "sanctions_export_policy"},
            "global_crude_shipping": {"opec_policy", "geopolitics_shipping", "inventory_demand", "macro_fx", "market_commentary", "other"},
        },
        "gasoline_europe": {
            "domestic_supply": {"domestic_refinery", "domestic_distribution", "refinery_outage"},
            "european_imports": {"european_gasoline_imports", "gasoline_blending_supply", "sanctions_export_policy"},
            "global_crude_shipping": {"opec_policy", "geopolitics_shipping", "inventory_demand", "macro_fx", "market_commentary", "other"},
        },
    }
    user_channels = ((cfg or {}).get("news", {}) or {}).get("channels")
    selected = user_channels if isinstance(user_channels, dict) else defaults.get(profile, defaults["diesel_europe"])
    categories = {
        channel: {str(value) for value in selected.get(channel, [])}
        for channel in ("domestic_supply", "european_imports", "global_crude_shipping")
    }
    channels = {name: 0.0 for name in categories}
    for event in news.get("events", []) if isinstance(news, dict) else []:
        category = str(event.get("category") or "other")
        score = float(event.get("effective_impact", 0.0) or 0.0)
        for channel, values in categories.items():
            if category in values:
                channels[channel] += score
                break
    # Compatibility with legacy v1 signals lacking event-level detail.
    if not any(channels.values()):
        channels["global_crude_shipping"] = float(
            news.get("effective_score", news.get("net_score", 0.0)) or 0.0
        )
    return {name: clamp(value, -3.0, 3.0) for name, value in channels.items()}


def build_features(ctx, news, obs, bootstrap=None, noon_resets=None, cfg=None):
    today = ctx["date"]
    local1, local3 = local_trends(
        obs, today, bootstrap, noon_resets=noon_resets
    )
    market = ctx.get("market", {})
    # Market override values supplied by GPT take precedence if present.
    ov = news.get("market_override", {}) if isinstance(news, dict) else {}
    def mv(name, field):
        if name in ov and ov[name].get(field) is not None:
            return float(ov[name][field])
        return getnum(market, name, field, default=0.0)
    score = float(news.get("effective_score", news.get("net_score", 0.0)) or 0.0)
    brent_eur_d1 = converted_pct(mv("brent", "d1_pct"),
                                 mv("eurusd", "d1_pct"))
    brent_eur_d5 = converted_pct(mv("brent", "d5_pct"),
                                 mv("eurusd", "d5_pct"))
    distillate_eur_d1 = converted_pct(mv("distillate", "d1_pct"),
                                      mv("eurusd", "d1_pct"))
    distillate_eur_d5 = converted_pct(mv("distillate", "d5_pct"),
                                      mv("eurusd", "d5_pct"))
    channels = news_channel_scores(news, cfg)
    return feature_vector(
        today,
        local1_ct=local1,
        local3_ct=local3,
        brent_eur_d1=brent_eur_d1,
        brent_eur_d5=brent_eur_d5,
        distillate_eur_d1=distillate_eur_d1,
        distillate_eur_d5=distillate_eur_d5,
        eurusd_d5=mv("eurusd", "d5_pct"),
        news_domestic_supply=channels["domestic_supply"],
        news_european_imports=channels["european_imports"],
        news_global_crude_shipping=channels["global_crude_shipping"],
    )

def manual_zone_offset(manual_rows, obs, zone):
    """Return a local station offset only for date-matched regional targets.

    A user-confirmed single-station price never becomes a regional training
    target. It can calibrate its own place only when the same date has a true
    11:50 regional reference.
    """
    values = []
    usable = []
    for row in manual_rows:
        station = row.get("station", {}) if isinstance(row, dict) else {}
        if str(station.get("place", "")).casefold() != str(zone).casefold():
            continue
        if row.get("training_status") != "excluded_single_station_not_regional_reference":
            continue
        day = row.get("date")
        target = obs.get(day, {}).get("metrics", {}).get("cheap_reference")
        price = row.get("price_eur_l")
        try:
            if target is None or price is None:
                continue
            values.append((float(price) - float(target)) * 100.0)
            usable.append(day)
        except (TypeError, ValueError):
            continue
    return (median(values) if values else None), sorted(usable)


def manual_zone_latest(manual_rows, zone):
    rows = [
        row for row in manual_rows
        if isinstance(row, dict)
        and str(row.get("station", {}).get("place", "")).casefold() == str(zone).casefold()
    ]
    return max(rows, key=lambda row: (row.get("date", ""), row.get("captured_at_local", "")), default=None)


def zone_offset(obs_rows, zone):
    diffs = []
    for r in obs_rows[-30:]:
        m = r.get("metrics", {})
        reg = m.get("cheap_reference")
        z = m.get("places",{}).get(zone,{}).get("best")
        if reg is not None and z is not None:
            diffs.append((z-reg)*100.0)
    return median(diffs) if diffs else None


def previous_forecasts_by_target(history_rows, before_date):
    """Return the latest older forecast for each target calendar date."""
    previous = {}
    for run in history_rows:
        issue_date = run.get("date")
        if not issue_date or issue_date >= before_date:
            continue
        for item in run.get("forecast", []):
            target_date = item.get("date")
            price = item.get("price")
            if not target_date or price is None:
                continue
            existing = previous.get(target_date)
            if existing is None or issue_date >= existing["issue_date"]:
                previous[target_date] = {
                    "issue_date": issue_date,
                    "price": float(price),
                }
    return previous


def attach_forecast_revisions(forecasts, history_rows, issue_date):
    previous = previous_forecasts_by_target(history_rows, issue_date)
    for item in forecasts:
        prior = previous.get(item["date"])
        if prior is None:
            item["revision_ct"] = None
            item["revision_from_date"] = None
            continue
        item["revision_ct"] = round((item["price"] - prior["price"]) * 100.0, 1)
        item["revision_from_date"] = prior["issue_date"]
    return forecasts

def main():
    d = data_dir()
    cfg = load_json(d/"config.json")
    ctx = load_json(d/"morning_context.json")
    if not cfg or not ctx:
        raise SystemExit("Run prepare_morning.py first and ensure config.json exists.")
    # Process a new v2 draft exactly once; retain compatibility with a legacy
    # news_signal.json when no current draft exists.
    news = process_news_files(d, ctx) or {}

    obs_rows = read_jsonl(d/"observations.jsonl")
    manual_station_rows = read_jsonl(d/"manual_station_observations.jsonl")
    obs = observations_by_date(obs_rows)
    bootstrap_rows = read_jsonl(d/"bootstrap_noon.jsonl")
    bootstrap = observations_by_date(bootstrap_rows)
    noon_rows = read_jsonl(d/"noon_resets.jsonl")
    noon_resets = observations_by_date(noon_rows)
    shadow_rows = read_jsonl(d/"noon_shadow_history.jsonl")
    shadow_evaluations = evaluate_noon_shadows(shadow_rows, obs_rows)
    write_jsonl(d/"noon_shadow_evaluations.jsonl", shadow_evaluations)
    shadow_report = evaluation_summary(shadow_evaluations)
    save_json(d/"noon_shadow_report.json", shadow_report)
    models = load_json(d/"model.json", {}) or {}
    migrated = []
    models.setdefault("intraday_offset_ct", -0.5)
    models.setdefault("trained_intraday_dates", [])
    for h in range(1, cfg.get("forecast",{}).get("days",5)):
        if not is_compatible(models.get(str(h))):
            migrated.append(h)
            models[str(h)] = new_model(h)
    models["version"] = MODEL_VERSION
    models["feature_names"] = FEATURE_NAMES
    if migrated:
        models["last_schema_migration"] = {
            "to_version": MODEL_VERSION,
            "reset_horizons": migrated,
        }

    # Reconcile same-day morning -> 11:50 offset.
    mornings = read_jsonl(d/"morning_runs.jsonl")
    trained_intraday = set(models.get("trained_intraday_dates", []))
    for r in mornings:
        dt = r.get("date")
        if dt in trained_intraday or dt not in obs:
            continue
        morning_ref = r.get("morning_cheap_reference")
        actual = obs[dt]["metrics"].get("cheap_reference")
        if morning_ref is not None and actual is not None:
            delta_ct = (actual-morning_ref)*100.0
            # Before noon the current regulatory regime should make positive deltas unusual.
            delta_ct = clamp(delta_ct, -6.0, 1.0)
            models["intraday_offset_ct"] = 0.82*models["intraday_offset_ct"] + 0.18*delta_ct
            trained_intraday.add(dt)
    models["trained_intraday_dates"] = sorted(trained_intraday)[-120:]

    # Reconcile pending multi-horizon forecasts.
    pending_all = load_json(d/"pending_training.json", []) or []
    pending = [p for p in pending_all
               if len(p.get("x", [])) == len(FEATURE_NAMES)]
    if len(pending) != len(pending_all):
        models["discarded_incompatible_pending"] = len(pending_all) - len(pending)
    still_pending = []
    for p in pending:
        issue, target = p["issue_date"], p["target_date"]
        if issue in obs and target in obs:
            actual_delta = (obs[target]["metrics"]["cheap_reference"] -
                            obs[issue]["metrics"]["cheap_reference"]) * 100.0
            m = models[str(p["horizon"])]
            update(m, p["x"], actual_delta, p.get("predicted_delta_ct"))
        else:
            still_pending.append(p)

    x = build_features(
        ctx, news, obs, bootstrap, noon_resets=noon_resets, cfg=cfg
    )
    _, _, local_trend_source = local_trend_selection(
        obs, ctx["date"], bootstrap=bootstrap, noon_resets=noon_resets
    )
    live_ref = ctx.get("local",{}).get("cheap_reference")
    if live_ref is None:
        # fallback to last observed 11:50 reference
        past = sorted(obs)
        if not past:
            raise SystemExit("No live Tankerkönig price and no observations available.")
        live_ref = obs[past[-1]]["metrics"]["cheap_reference"]
    today_est = live_ref + models["intraday_offset_ct"]/100.0
    # Do not predict a higher 11:50 level than the live pre-noon reference.
    today_est = min(today_est, live_ref)

    forecasts = [{
        "date": ctx["date"],
        "horizon": 0,
        "price": round(today_est, 3),
        "delta_ct": 0.0,
        "low": round(today_est - 0.012, 3),
        "high": round(today_est + 0.008, 3),
        "confidence": 0.68 if ctx.get("local",{}).get("cheap_reference") is not None else 0.40,
    }]

    for h in range(1, cfg["forecast"].get("days",5)):
        m = models[str(h)]
        delta = predict(m, x)
        p = today_est + delta/100.0
        mae = max(1.2, m.get("mae_ema_ct", 3.0))
        band = 1.35*mae/100.0
        forecasts.append({
            "date": add_days(ctx["date"], h),
            "horizon": h,
            "price": round(p,3),
            "delta_ct": round(delta,1),
            "low": round(p-band,3),
            "high": round(p+band,3),
            "confidence": round(confidence(m),2),
        })
        still_pending.append({
            "id": f'{ctx["date"]}:{h}',
            "issue_date": ctx["date"],
            "target_date": add_days(ctx["date"], h),
            "horizon": h,
            "x": x,
            "predicted_delta_ct": delta,
        })

    forecast_history = read_jsonl(d/"forecast_history.jsonl")
    attach_forecast_revisions(forecasts, forecast_history, ctx["date"])

    # Deduplicate pending by id.
    pd = {p["id"]: p for p in still_pending}
    save_json(d/"pending_training.json", list(pd.values())[-500:])

    future = forecasts[1:]
    best = min(future, key=lambda r:r["price"]) if future else forecasts[0]
    advantage_ct = (best["price"] - forecasts[0]["price"])*100.0
    fcfg = cfg["forecast"]
    if advantage_ct <= -float(fcfg.get("wait_threshold_ct",2.0)) and best["confidence"] >= float(fcfg.get("min_confidence",0.5)):
        action = "WAIT"
        action_de = "WARTEN"
    elif advantage_ct >= -float(fcfg.get("tank_threshold_ct",0.8)):
        action = "TANK_TODAY"
        action_de = "TANKEN HEUTE"
    else:
        action = "NEUTRAL"
        action_de = "NEUTRAL"

    places = {}
    manual_place_history = {}
    for z in cfg["region"].get("preferred_places",[]):
        off = zone_offset(obs_rows, z)
        manual_off, matched_dates = manual_zone_offset(manual_station_rows, obs, z)
        latest_manual = manual_zone_latest(manual_station_rows, z)
        # Direct matched 11:50 regional truth takes precedence; otherwise keep
        # the model's regional/local offset untouched and expose the manual row.
        if manual_off is not None:
            off = manual_off
        if off is None:
            live_zone = ctx.get("local",{}).get("places",{}).get(z,{}).get("best")
            if live_zone is not None:
                off = (live_zone - ctx["local"]["cheap_reference"])*100.0
        manual_place_history[z] = {
            "count": sum(
                1 for row in manual_station_rows
                if str(row.get("station", {}).get("place", "")).casefold() == str(z).casefold()
            ),
            "matched_regional_dates": matched_dates,
            "latest": latest_manual,
            "used_for_offset": manual_off is not None,
            "note": (
                "Single-station entries are never regional model targets; they "
                "adjust this place only when matched to a true regional 11:50 reference."
            ),
        }
        places[z] = {
            "offset_ct": round(off,1) if off is not None else None,
            "forecast": [
                {"date": r["date"], "price": round(r["price"] + (off or 0)/100.0,3)}
                for r in forecasts
            ] if off is not None else []
        }

    result = {
        "version": 1,
        "generated_at": ctx["generated_at"],
        "date": ctx["date"],
        "fuel": cfg.get("fuel","diesel"),
        "region": cfg["region"]["name"],
        "recommendation": action,
        "recommendation_de": action_de,
        "best_day": best["date"],
        "best_advantage_ct": round(advantage_ct,1),
        "forecast": forecasts,
        "local_live": ctx.get("local",{}),
        "places": places,
        "manual_station_history": manual_place_history,
        "news": {
            "version": news.get("version", 1),
            "channels": news_channel_scores(news, cfg),
            "profile": ((cfg.get("news", {}) or {}).get("profile") or (
                "diesel_europe" if cfg.get("fuel", "diesel") == "diesel" else "gasoline_europe"
            )),
            "net_score": news.get("net_score",0),
            "effective_score": news.get("effective_score", news.get("net_score",0)),
            "confidence": news.get("confidence"),
            "summary": news.get("summary"),
            "drivers": news.get("drivers",[])[:5],
            "sources": news.get("sources",[])[:8],
            "event_ids": [event.get("event_id") for event in news.get("events",[])[:8]],
        },
        "model": {
            "version": MODEL_VERSION,
            "intraday_offset_ct": round(models["intraday_offset_ct"],2),
            "samples": {str(h): models[str(h)].get("samples",0) for h in range(1,fcfg.get("days",5))},
            "bootstrap_samples": {str(h): models[str(h)].get("bootstrap_samples",0) for h in range(1,fcfg.get("days",5))},
            "mae_ct": {str(h): round(models[str(h)].get("mae_ema_ct",0),2) for h in range(1,fcfg.get("days",5))},
            "market_features": "EUR-converted split rises/falls (rockets-and-feathers)",
            "local_trend_source": local_trend_source,
        },
        "noon_reset": {
            "days": len(noon_resets),
            "latest_date": max(noon_resets) if noon_resets else None,
            "used_as": "separate local-movement fallback; never 11:50 truth",
            "shadow_evaluation": shadow_report,
        },
        "bootstrap": {"tankzeit_noon_days": len(bootstrap), "used_for": "daily movement only; 11:50 level remains Tankerkönig ground truth"},
        "attribution": "Live/11:50: Tankerkönig.de / MTS-K; historical movement bootstrap: tankzeit.de"
    }
    save_json(d/"forecast.json", result)
    save_json(d/"model.json", models)
    append_jsonl(d/"morning_runs.jsonl", {
        "date": ctx["date"],
        "generated_at": ctx["generated_at"],
        "morning_cheap_reference": ctx.get("local",{}).get("cheap_reference"),
        "x": x,
        "news_effective_score": news.get("effective_score", news.get("net_score",0)),
        "news_version": news.get("version", 1),
        "news_event_ids": [event.get("event_id") for event in news.get("events",[])],
        "news_draft_fingerprint": news.get("draft_fingerprint"),
    })
    append_jsonl(d/"forecast_history.jsonl", result)
    print(json_summary(result))

def json_summary(r):
    lines = [
        f'{r["recommendation_de"]} — {str(r.get("fuel", "Kraftstoff")).upper()} {r["region"]}',
        f'Heute ~ {r["forecast"][0]["price"]:.3f} €/l; bester Tag {r["best_day"]} ({r["best_advantage_ct"]:+.1f} ct).'
    ]
    for x in r["forecast"]:
        revision = x.get("revision_ct") if x.get("horizon") == 0 else None
        revision_text = f', Revision {revision:+.1f} ct' if revision is not None else ''
        lines.append(f'{x["date"]}: {x["price"]:.3f} €/l ({x["delta_ct"]:+.1f} ct{revision_text}, conf {x["confidence"]:.0%})')
    if r["news"].get("summary"):
        lines.append("News: " + str(r["news"]["summary"]))
    return "\n".join(lines)

if __name__ == "__main__":
    main()
