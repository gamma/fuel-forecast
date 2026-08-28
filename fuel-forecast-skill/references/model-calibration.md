# Historical model calibration

After both bootstrap files exist, run once before real 11:50 learning begins:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/calibrate_bootstrap_model.py
```

The calibration:

- learns daily movements, never the absolute tankzeit noon level;
- uses only market values available before each historical fuel target;
- converts Brent and the middle-distillate proxy to EUR;
- separates rising and falling cost features;
- calibrates one model for each 1–4 day horizon;
- validates chronologically on the newest 20 percent of rows;
- keeps economic sign constraints on bootstrap start weights;
- caps confidence until real 11:50 observations accumulate.

The separate rise/fall features and horizon models encode the
rockets-and-feathers prior: cost increases may pass through quickly while cost
decreases can take several days. Actual Scriptable observations continue to
update the weights online.

For safety, the script refuses to replace weights after real observations have
trained the model. `--force` exists for an intentional, reviewed recalibration.
