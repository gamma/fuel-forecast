# Historical market bootstrap

Run after `download_tankzeit_history.py`:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/download_market_history.py
```

The script reads the dates in `memory/bootstrap_noon.jsonl` and writes:

- `memory/bootstrap_market.jsonl`
- `memory/bootstrap_market_manifest.json`

Each fuel date contains:

- Brent futures in USD per barrel;
- Heating Oil futures in USD per US gallon as a middle-distillate proxy;
- the ECB EUR/USD reference rate in USD per EUR;
- derived Brent in EUR per barrel;
- derived distillate cost in EUR per liter.

## No look-ahead

A fuel target around noon must not be paired with a same-day futures close or
ECB reference rate published later that day. Every row therefore uses the
latest value strictly before the fuel target date. `source_date` records the
actual market/reference date used.

The file is a derived historical input for later model calibration. Creating it
does not modify `observations.jsonl`, `bootstrap_noon.jsonl`, or learned model
weights.
