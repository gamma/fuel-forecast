# Daily GPT news draft — schema v2

After `prepare_morning.py`, read `morning_context.json`. Research material
developments that were published during the previous 48 hours and can plausibly
affect German diesel prices over the next 1–5 days.
Also carry forward a previously recorded event only when it remains materially
unresolved; keep its original `published_at` and mark it `ongoing`.

Prioritize Reuters/major wires and primary OPEC, IEA, EIA, government, sanctions,
inventory, refinery, pipeline, shipping, and export-policy sources. News is a
residual shock: estimate how much is not already visible in Brent/distillate
futures. Do not score ordinary market commentary as a new causal event.

Write valid JSON only to the exact `instructions_for_gpt.write_file` path,
normally `memory/news_signal_draft.json`:

```json
{
  "version": 2,
  "date": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "summary": "One short German sentence.",
  "events": [
    {
      "event_id": "stable-topic-id-across-days",
      "update_id": "stable-id-for-this-specific-development",
      "category": "refinery_outage",
      "status": "new",
      "published_at": "YYYY-MM-DDTHH:MM:SSZ",
      "impact": 1.5,
      "confidence": 0.8,
      "novelty": 1.0,
      "already_priced": 0.6,
      "persistence_hours": 72,
      "reason": "Why this is a residual German-diesel driver.",
      "sources": [
        {
          "title": "...",
          "url": "https://...",
          "published_at": "YYYY-MM-DDTHH:MM:SSZ"
        }
      ]
    }
  ],
  "market_override": {
    "brent": {"latest": null, "d1_pct": null, "d5_pct": null},
    "distillate": {"latest": null, "d1_pct": null, "d5_pct": null},
    "eurusd": {"latest": null, "d1_pct": null, "d5_pct": null}
  }
}
```

## Event fields

- `event_id`: stable across repeated coverage of the same underlying event.
- `update_id`: stable only for the same specific development; change it when a
  genuinely new decision, outage update, escalation, or resolution occurs.
- `status`: `new`, `updated`, `ongoing`, or `resolved`.
- `published_at`: exact timestamp with timezone. Never substitute today's time.
- `impact`: residual direction/magnitude from -2 to +2.
- `confidence`, `novelty`, `already_priced`: values from 0 to 1.
- `persistence_hours`: expected event half-life, normally 12–168 hours.

Suggested categories: `opec_policy`, `sanctions_export_policy`,
`geopolitics_shipping`, `refinery_outage`, `distillate_supply`,
`inventory_demand`, `macro_fx`, `market_commentary`, `other`.

The deterministic processor applies full age weight at 0–24 hours, decays it to
55 percent during 24–48 hours, retains older events only when `ongoing` or
`updated`, discounts repeated event/update IDs, and applies the already-priced
factor. Do not calculate `effective_score` yourself.

After writing the draft, run:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/process_news_signal.py
```

This writes `memory/news_signal.json` and appends point-in-time event records to
`memory/news_history.jsonl`.
