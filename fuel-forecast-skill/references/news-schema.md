# Daily GPT news draft — schema v2

After `prepare_morning.py`, read `morning_context.json`. Research material
developments that were published during the previous 48 hours and can plausibly
affect German diesel prices over the next 1–5 days.
Also carry forward a previously recorded event only when it remains materially
unresolved; keep its original `published_at` and mark it `ongoing`.

Prioritize Reuters/major wires and primary OPEC, IEA, EIA, government, sanctions,
inventory, refinery, pipeline, shipping, export-policy, European import-flow and
Middle-East diesel/gasoil cargo sources. News is a
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

Suggested categories: `domestic_refinery`, `domestic_distribution`,
`european_diesel_imports`, `gulf_distillate_shipping`, `opec_policy`,
`sanctions_export_policy`, `geopolitics_shipping`, `refinery_outage`,
`distillate_supply`, `inventory_demand`, `macro_fx`, `market_commentary`,
`other`.

## Transmission-path classification

Assign every event to the most direct German-diesel transmission path:

- `domestic_refinery` / `domestic_distribution`: German refinery availability,
  Rhine/rail/terminal disruptions, strikes, or regional logistics. Use only for
  an identifiable domestic effect.
- `european_diesel_imports`: cargo availability, European diesel/gasoil import
  flows, EU/UK/Northwest-European stocks, exports from the Middle East, India,
  Turkey, the US or Russia, and sanctions that directly redirect diesel supply.
- `gulf_distillate_shipping`: Strait of Hormuz, Gulf port/loadings or tanker
  disruptions **when they impede diesel/gasoil cargoes** destined for Europe.
  Do not use this merely for an oil headline.
- `geopolitics_shipping` / `opec_policy`: broad crude or shipping news without
  a demonstrated distillate-import connection.

The model keeps these three channels separate: domestic supply, European
imports (the highest initial diesel-specific weight), and global crude/shipping.
Always estimate the residual effect after checking the EUR-adjusted distillate
futures; do not count the same shock twice.

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
