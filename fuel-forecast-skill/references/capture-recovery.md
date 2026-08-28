# Rejected 11:50 capture recovery

Read this reference only when `capture_recovery_request.json` has status `pending_verified_historical_lookup` or the user asks to repair a rejected/missing observation.

## Normal guard

The default acceptance window is 11:40 inclusive to 12:00 exclusive in the device's local timezone. A valid capture also requires at least five open stations and a regional reference between 0.50 and 5.00 EUR/l. Relative to the latest same-day stored observation or `morning_context.json`, an increase over 6 ct/l or decrease over 12 ct/l is rejected by default. These thresholds can be changed only in the single active `memory/config.json` under `capture`.

Never bypass the guard merely to fill a missing day. A missing observation is safer than a post-noon value presented as 11:50 ground truth.

If a known-bad value was already written and the user authorizes its removal, quarantine it before any recovery attempt:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/quarantine_observation.py \
  --date YYYY-MM-DD --reason "why this value is invalid"
```

This preserves the rejected row in `capture_rejections.jsonl`, removes it from training observations, and opens a recovery request. It does not invent a replacement.

## Acceptable recovery sources

Use this order:

1. An already stored local snapshot within the configured capture window.
2. Authorized Tankerkönig event-level historical CSV data. Reconstruct each station's last known price at or before the configured local target time, preserving timezone conversion.
3. No observation. Report that the day remains missing.

When an authorized historical repository is mounted, a missing date can be reconstructed with:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/import_tankerkoenig_history.py \
  --repo /path/to/tankerkoenig-data --since YYYY-MM-DD --until YYYY-MM-DD
```

Review the resulting timestamp and regional station count before considering the request resolved.

## Sources that are not 11:50 truth

Do not write any of these to `observations.jsonl` automatically:

- a current live price obtained after the capture window;
- tankzeit's daily noon value, because it can include changes reported from 12:00 to 12:15;
- an untimestamped fuel-price webpage or search snippet;
- interpolation between a morning and afternoon value;
- an LLM estimate.

A pre-noon `morning_context.json` snapshot can be shown to the user as a clearly labelled recovery candidate, but it is not promoted to the authoritative 11:50 series without explicit user approval.
