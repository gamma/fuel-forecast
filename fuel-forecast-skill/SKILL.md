---
name: fuel-forecast
description: >
  Predict whether to refuel diesel today or wait 1–4 days around Oberkrämer/Oberhavel.
  Use for Dieselpreis, Tanken, Tankerkönig, Spritpreis-Prognose, Germendorf, Hohen Neuendorf,
  oil-price/news effects, daily fuel forecast, a scheduled morning task, or the 11:50/12:20 learning captures.
metadata:
  version: 1.8.0
  compatibility: OpenMinis on iOS or Android with Python 3, network access, and browser/search; Scriptable is optional and iOS-only.
---

# Fuel Forecast — Oberkrämer/Oberhavel Diesel

Operate this as a deterministic local forecasting workflow with GPT used for fresh-news interpretation.

## Data paths

Prefer `/var/minis/mounts/FuelForecast/memory/`. If not mounted, scripts fall back to `/var/minis/memory/fuel-forecast/`.
The `memory` subfolder is the persistent data store. On iOS, Scriptable can write the true 11:50 target and the separate 12:20 noon-reset signal into the mounted shared folder. On Android or without Scriptable, `capture_observation.py` writes the same two data types directly. `memory/config.json` is the single active configuration; `references/config.example.json` is only a template and must not be maintained as a second live config.

## Daily learning captures — one script, two times

Use the same executable for both scheduled invocations. To record the authoritative daily learning target, run once near 11:50 local time:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode pre_noon
```

To record the separate post-12 reset proxy, run the same script once near 12:20 local time:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode noon_reset
```

Each invocation makes one Tankerkönig request and idempotently replaces today's row in its own series. `pre_noon` writes `observations.jsonl`; `noon_reset` writes `noon_resets.jsonl`, `noon_shadow_forecast.json`, and `noon_shadow_history.jsonl`. With no `--mode`, the script detects the active window automatically. Report the capture type, regional reference, and any error briefly. On iOS, schedule the single `FuelForecastCapture.js` implementation twice; do not add the Python capture on top of Scriptable.

Both capture implementations enforce local 11:40–12:00 and 12:15–12:31 acceptance windows by default. They reject before making a live request when invoked outside the requested window. Both types reject too few stations, implausible values, and attempts that would replace an existing capture closer to its target. Only the pre-noon target rejects large same-day jumps; a regulatory 12:00 increase is valid for `noon_reset`. Rejections never modify either learning series and are audited in `capture_rejections.jsonl`. Only a failed pre-noon capture creates `capture_recovery_request.json`.

Never merge or substitute the two series. The noon reset may provide local day-to-day movement when pre-noon data has a gap, but its absolute level is not 11:50 ground truth. Its D+1 revision remains shadow-only until `noon_shadow_report.json` has enough out-of-sample evaluations to justify production use. A missing capture of either type does not invalidate the other.

When a pre-noon capture is rejected, do not rerun the current live API and do not invent or interpolate an 11:50 price. Read [references/capture-recovery.md](references/capture-recovery.md) and research only verified timestamped historical data. Leave the day missing if no qualifying source exists. A rejected noon reset is simply left missing; it never triggers 11:50 recovery.

## Morning workflow

1. If `capture_recovery_request.json` exists with a status beginning with `pending`, read [references/capture-recovery.md](references/capture-recovery.md) and attempt only a verified timestamped recovery. Do not delay the morning forecast and do not fill the observation when no qualifying source is available.
2. Run:
   ```sh
   python3 /var/minis/skills/fuel-forecast/scripts/prepare_morning.py
   ```
3. Read `morning_context.json`.
4. Read `references/news-schema.md`.
5. Read the previous `news_signal.json` when present and reuse stable `event_id` values for the same underlying events. Give a new `update_id` only to a genuinely new development. Carry forward an older event only when it remains materially unresolved; mark it `ongoing` and preserve its original publication timestamp.
6. Use Minis web/browser search to research the last 48 hours of oil, middle-distillate/diesel, refinery, sanctions, shipping, OPEC+, inventory, and EUR/USD-relevant developments. Capture exact publication timestamps with timezone.
7. Treat news as a **residual shock**, not a second copy of price moves already visible in futures. Prioritize Reuters and primary sources.
8. Write strict valid schema-v2 JSON to `/var/minis/mounts/FuelForecast/memory/news_signal_draft.json`.
9. Run:
   ```sh
   python3 /var/minis/skills/fuel-forecast/scripts/process_news_signal.py
   ```
10. Run:
   ```sh
   python3 /var/minis/skills/fuel-forecast/scripts/run_forecast.py
   ```
11. Read `forecast.json` and report briefly in German:
   - TANKEN HEUTE / WARTEN / NEUTRAL
   - today + next four dates with expected pre-12:00 diesel price
   - best day and expected advantage in ct/l
   - Germendorf / Hohen Neuendorf when available
   - top 2–4 market/news drivers
   - confidence/model sample count
   - append today's forecast revision in ct inline when `revision_ct` is available; omit future-day revisions and do not add a separate revision section
12. Send a native notification with title `Diesel-Prognose OHV` and body containing the recommendation, best day, and expected advantage.

## Learning behavior

Do not invent training data. `FuelForecastCapture.js` on iOS or `capture_observation.py` in Minis records the actual Tankerkönig snapshot at 11:50 and the separately labelled reset proxy at 12:20.
`run_forecast.py` reconciles old predictions against later observations and updates one online model per horizon.
Model errors and sample counts are persisted in `model.json`.

The reset model learns only leakage-safe pairs `noon_reset(D) -> pre_noon_observation(D+1)`. It can therefore keep learning when the 11:50 capture on day D is missing, provided the next day's target exists. Conversely, the normal model continues when a noon reset is missing. The 07:00 workflow evaluates matured shadow forecasts and writes `noon_shadow_evaluations.jsonl` plus `noon_shadow_report.json`.

The system starts with conservative heuristic weights. It becomes genuinely personalized after accumulating daily observations.
If authorized historical Tankerkönig CSV access is available, bootstrap with `import_tankerkoenig_history.py`; realtime API calls must not be abused for historical mass collection.

Model version 2 converts market inputs to EUR and uses separate cost-rise and cost-fall features for each forecast horizon. This is the rockets-and-feathers prior: upward pass-through starts faster, while downward pass-through is allowed to unfold over more days. Historical tankzeit calibration is discounted and confidence remains capped until real 11:50 samples accumulate.

## Historical bootstrap

If `/var/minis/mounts/FuelForecast/memory/bootstrap_noon.jsonl` is missing or older than 7 days, run:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/download_tankzeit_history.py
```

This discovers currently relevant regional stations with one Tankerkönig request and downloads their public tankzeit historical noon CSVs. Read `references/tankzeit-bootstrap.md` for the target-time caveat. Never merge `bootstrap_noon.jsonl` into `observations.jsonl`.

After creating or refreshing `bootstrap_noon.jsonl`, build the matching historical market series:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/download_market_history.py
```

This writes `memory/bootstrap_market.jsonl` with leakage-safe prior-day Brent, middle-distillate, ECB EUR/USD, and EUR-converted cost series. Read `references/market-bootstrap.md` for alignment and unit details. The calibration command below consumes this history; the normal morning forecast then uses the calibrated version-2 weights.

Before real 11:50 learning begins, calibrate model version 2 once:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/calibrate_bootstrap_model.py
```

Read `references/model-calibration.md`. The command refuses to replace a model that already contains real online samples unless `--force` is deliberately supplied.

Validate historical performance with expanding-window checkpoints:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/backtest_model.py \
  --checkpoints 50,100,120,130,140 --evaluation-days 10
```

Read `references/backtesting.md` and report both model MAE and the unchanged-price baseline. Never present in-sample calibration error as forecast performance.

To measure the incremental value of market, FX, and asymmetric pass-through, run:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/ablation_backtest.py \
  --checkpoints 50,100,120,130,140 --evaluation-days 10
```

Read `references/ablation-testing.md`. Historical news remains zero because no leakage-safe point-in-time residual-news archive exists; do not describe that feature as historically validated.

## Current prices

Tankerkönig/MTS-K is the primary source for local live fuel prices. Do not replace it with scraped fuel-price websites when the API is available.

## Market values

The deterministic helper tries:
- Brent futures: Yahoo Finance JSON (`BZ=F`)
- Heating Oil futures as a liquid middle-distillate proxy: Yahoo Finance JSON (`HO=F`)
- EUR/USD: official ECB reference-rate XML

These numeric endpoints are only inputs. Cross-check direction and unusual moves during GPT web research. If a numeric source fails, use reliable web sources and fill `market_override` in `news_signal_draft.json`.

## News lifecycle

News schema v2 is processed deterministically. Events from 0–24 hours receive full age weight; events from 24–48 hours decay to 55 percent. Older events contribute only when explicitly `ongoing` or `updated`, then decay using their persistence half-life. Repeated `event_id`/`update_id` pairs receive reduced novelty. The processor writes the model input to `news_signal.json` and appends an auditable point-in-time record to `news_history.jsonl`.

News published between daily 07:00 runs is included at the next run while it is still in the full 0–24 hour window. Do not run the pre-noon forecast workflow after noon merely to refresh news; its same-day price anchor is designed for the morning cycle.

## Safety/quality

- Never claim precision below the model uncertainty.
- A 1 ct/l predicted advantage is not a strong wait signal.
- Prefer `NEUTRAL` when evidence conflicts.
- Mention stale/missing market or Tankerkönig data.
- Preserve Tankerkönig attribution in outputs.
