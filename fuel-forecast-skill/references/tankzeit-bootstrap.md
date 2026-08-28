# tankzeit.de bootstrap

tankzeit.de documents a daily historical noon series since 2026-04-01:

`data2/<station>/<fuel>/history.csv`

Columns:
- `date`
- `price`
- `last_update`

Important semantic difference from FuelForecast's target:
tankzeit's 12:00 reference can include a positive change reported between
12:00 and 12:15. FuelForecast targets the cheap pre-increase price around 11:50.

Therefore:
- `bootstrap_noon.jsonl` is kept separate.
- Absolute tankzeit noon prices are never treated as 11:50 ground truth.
- The model uses the historical series mainly for day-to-day movement and
  early regime/seasonality information.
- `observations.jsonl` from Scriptable/Tankerkönig at 11:50 remains authoritative.

The downloader first discovers currently relevant stations with one Tankerkönig
`list.php` call, then downloads per-station historical CSV files from public
tankzeit/GitHub or its documented Hugging Face dataset.
