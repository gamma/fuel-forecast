# Walk-forward backtesting

Run after historical calibration:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/backtest_model.py \
  --checkpoints 50,100,120,130,140 \
  --evaluation-days 10
```

For each checkpoint, the model is calibrated only with targets available by
that cutoff. Its weights are then frozen and tested on the next ten fuel issue
dates. Local trend features may use observations from preceding evaluation days,
because the real Scriptable workflow would know those prior-day captures.

The report compares the model with an unchanged-price baseline and records:

- MAE and RMSE in ct/l;
- signed bias;
- direction accuracy for movements of at least 0.5 ct/l;
- per-horizon and combined results;
- sample counts and exact evaluation dates.

Output: `memory/backtest_report.json`.

## Limitations

This validates tankzeit noon movement, not the absolute 11:50 target. It does
not retrospectively invent GPT news scores or test the live-morning intraday
offset. Late checkpoints have few future rows, so their metrics are less stable.
