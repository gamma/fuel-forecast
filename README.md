# FuelForecast for Open Minis — iOS and Android

Serverless diesel-price forecast for Oberkrämer/Oberhavel.

Current skill package: **v1.8.0**

## Platform support

| Function | iOS | Android |
| --- | --- | --- |
| Open Minis forecast skill | Yes | Yes |
| 07:00 forecast automation | Apple Shortcuts | Built-in Scheduled Tasks |
| 11:50 target + 12:20 reset capture | One Scriptable source, two Apple automations | One Python source, two Scheduled Tasks |
| Result | Minis notification/chat, `forecast.json`, optional Scriptable widget | Minis notification/chat and `forecast.json` |
| Persistent data | Mounted iCloud folder | Minis-local memory, or a mounted `FuelForecast` folder |

Open Minis officially supports both platforms. Android Scheduled Tasks, available since Android `0.11-preview`, can run prompts once, daily, on weekdays, or on selected days; see the [Open Minis website](https://openminis.app/) and [Android release notes](https://github.com/OpenMinis/OpenMinis/releases).

## Architecture

- **Tankerkönig/MTS-K**: live local diesel truth
- **One dual-mode capture**: records the 11:50 daily target and the separately stored 12:20 reset signal, using Scriptable on iOS or the skill's Python capture on Android
- **Minis at 07:00**: fetches market data, GPT researches the last 48h of oil/diesel news, updates the online model, writes `forecast.json`
- **Optional iOS Scriptable widget**: shows the live cheapest station plus the 5-day forecast
- **One `memory` folder**: contains the single active configuration, observations, model, news signals and forecasts

## Installation

### A. Install the skill — both platforms

1. Install [Open Minis](https://openminis.app/) on iOS or Android.
2. Import `fuel-forecast-skill.zip` using Minis' Skills import UI.
3. Open a Minis chat using a GPT model with web/browser access.
4. Start a fresh chat after importing an updated ZIP so the new skill version is loaded.

If the import UI does not accept the ZIP and the file is available in Minis' sandbox, install it with:

```sh
mkdir -p /var/minis/skills/fuel-forecast
unzip -o /path/to/fuel-forecast-skill.zip -d /var/minis/skills/fuel-forecast
```

After every change under `fuel-forecast-skill/`, rebuild the package before refreshing Minis:

```sh
./build_skill_zip.sh
```

### B. Configure the single data folder

Only one live `config.json` is maintained per installation. The file under `references/` is a template, not a second configuration.

#### iOS with Scriptable/iCloud

1. In Files, create `iCloud Drive/Scriptable/FuelForecast`.
2. Copy `fuel-forecast-skill/references/config.example.json` once to `iCloud Drive/Scriptable/FuelForecast/memory/config.json`.
3. Edit only `memory/config.json` and replace `PASTE_YOUR_TANKERKOENIG_API_KEY_HERE` with your existing key. This is the single active configuration.
4. In Minis, mount the iCloud folder `Scriptable/FuelForecast` as external folder **FuelForecast**.
   The expected path inside Minis is `/var/minis/mounts/FuelForecast/`.
5. Say:
   `Run the fuel-forecast setup check and then execute one morning forecast.`
6. Confirm that `memory/forecast.json` appears in the shared folder.

#### Android or Minis without an external mount

Use Minis' local persistent data directory:

```sh
mkdir -p /var/minis/memory/fuel-forecast
cp /var/minis/skills/fuel-forecast/references/config.example.json \
  /var/minis/memory/fuel-forecast/config.json
```

Edit only `/var/minis/memory/fuel-forecast/config.json` and replace the API-key placeholder. Then ask Minis:

`Run the fuel-forecast setup check and then execute one morning forecast.`

Confirm that `/var/minis/memory/fuel-forecast/forecast.json` exists. If Android has an external folder mounted with the exact name **FuelForecast**, the skill uses `/var/minis/mounts/FuelForecast/memory/` instead; do not keep active configurations in both locations.

### C. iOS: Scriptable

Scriptable accepts sources only from the top-level `Documents` folder. Use the two wrappers created there:

- `FuelForecastCapture.js`
- `FuelForecastWidget.js`

They load the maintained implementations from `FuelForecast/scriptable/`; edit the files in the project, not the wrappers.

Run each once manually and grant Location/iCloud permissions when requested.

### D. iOS: one capture script at 11:50 and 12:20

Create two iOS Personal Automations that both run the existing `FuelForecastCapture` script:

1. First automation: Time of Day → **11:50**, Daily → Scriptable → **Run Script** → `FuelForecastCapture` → Run Immediately.
2. Set its optional Shortcut parameter to `pre_noon`. If the installed Scriptable action does not expose a parameter field, leave it empty; the script detects the time window automatically.
3. Duplicate the automation and change only the time to **12:20**.
4. Set the duplicate's optional parameter to `noon_reset`, or leave it empty for automatic detection.

There is still only one Scriptable source/wrapper. The 11:50 run writes the authoritative target to `memory/observations.jsonl`; the 12:20 run writes the independent reset signal to `memory/noon_resets.jsonl`. If one automation fails, the other series remains valid and usable.

The pre-noon capture accepts writes from **11:40 inclusive until 12:00 exclusive**. The reset capture accepts writes from **12:15 inclusive until 12:31 exclusive** and targets 12:20, allowing a large regulatory upward jump. Both reject before a Tankerkönig request when outside the requested window and preserve an existing capture closer to its target. Defaults and optional overrides live only under `capture` in the single active `memory/config.json`.

Rejected attempts leave both series unchanged and append an audit record to `memory/capture_rejections.jsonl`. Only a failed pre-noon capture creates `memory/capture_recovery_request.json`. Recovery uses timestamped event-level historical data only; noon-reset, tankzeit noon, and current post-noon prices are never promoted automatically to 11:50 truth.

The reset run also writes a D+1 candidate to `memory/noon_shadow_forecast.json`. It learns only from historical pairs `12:20 on D → 11:50 on D+1`, is evaluated automatically, and does not yet change `forecast.json`, the recommendation, or the widget.

The next Minis morning workflow checks a pending recovery request before model reconciliation. If no verified event-level source is available, the observation remains missing and the normal forecast continues safely.

### E. iOS: 07:00 forecast automation

On iOS, Minis does not expose an in-app Scheduled Tasks screen. Create a Personal Automation in Apple's **Shortcuts** app instead:

1. Shortcuts → Automation → `+`
2. Time of Day → **07:00**, Daily
3. Choose **Run Immediately**
4. Add Action → search for **Minis** or **Open Minis**
5. If the installed Minis version exposes **Send Prompt**, select it and paste this prompt:

`Run the fuel-forecast skill morning workflow now. Use GPT/web research for the last 48 hours of oil, diesel/distillate, refinery, OPEC+, sanctions and shipping news; create the schema-v2 news draft with exact publication timestamps and stable event IDs, process it, update the self-learning model, write forecast.json and send me a Diesel-Prognose OHV notification.`

Run the automation manually once and approve any requested notification, file and network permissions. Android builds can provide their own Scheduled Tasks screen; these instructions are specifically for iOS. If **Send Prompt** is missing, opening Minis alone will not run the workflow automatically—the available Minis Shortcut actions or a supported prompt deep link must be checked for that installed build.

### F. Android: built-in Scheduled Tasks

Android Open Minis has a native scheduler backed by Android's AlarmManager. Open it through the **clock icon on the Minis home screen** or through **Settings → Scheduled Tasks**. You can also ask the agent to manage tasks through `minis-scheduled`.

Create these three daily tasks in the device's local timezone. Both price-capture tasks call the same Python source:

#### 07:00 forecast

- Schedule: **Daily at 07:00**
- Mode: preferably **new chat**
- Model: a GPT model with web/browser access
- Prompt:

> Run the fuel-forecast skill morning workflow now. Use GPT/web research for the last 48 hours of oil, diesel/distillate, refinery, OPEC+, sanctions and shipping news; create the schema-v2 news draft with exact publication timestamps and stable event IDs, process it, update the self-learning model, write forecast.json and send me a Diesel-Prognose OHV notification.

#### 11:50 learning capture

- Schedule: **Daily at 11:50**
- Prompt:

> Run `python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode pre_noon` for the fuel-forecast 11:50 learning target. Report the captured regional reference.

#### 12:20 noon-reset capture

- Schedule: **Daily at 12:20**
- Prompt:

> Run `python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode noon_reset` for the fuel-forecast noon-reset signal. Keep it separate from observations.jsonl and report the reset and shadow D+1 correction.

Each capture invocation calls Tankerkönig once and replaces only today's row in its corresponding series. Do not add a second capture mechanism for either time on the same installation.

Run all three tasks manually once, grant notification/network permissions, and inspect **Run records**. For more reliable background execution, enable **Settings → Background Audio Keep-Alive** in Open Minis. Android users receive the result through the Minis notification/chat and can inspect `forecast.json`; the Scriptable home-screen widget remains iOS-only.

## Historical bootstrap

The realtime Tankerkönig API is intentionally not used for mass historical collection. Build the public tankzeit noon history first, then align historical market and exchange-rate data:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/download_tankzeit_history.py
python3 /var/minis/skills/fuel-forecast/scripts/download_market_history.py
python3 /var/minis/skills/fuel-forecast/scripts/calibrate_bootstrap_model.py
```

The second command pairs every fuel date with only the previously available Brent, Heating Oil, and ECB EUR/USD values. It also derives Brent in EUR/barrel and the distillate proxy in EUR/liter. The third command calibrates separate cost-rise and cost-fall features for each forecast horizon, encoding a conservative rockets-and-feathers prior without treating tankzeit noon prices as absolute 11:50 truth.

Test historical model snapshots against unseen future windows:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/backtest_model.py \
  --checkpoints 50,100,120,130,140 --evaluation-days 10
```

The generated `memory/backtest_report.json` compares the model against an unchanged-price baseline for each checkpoint and forecast horizon.

Compare the incremental value of local dynamics, USD markets, EUR conversion, and rockets-and-feathers:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/ablation_backtest.py \
  --checkpoints 50,100,120,130,140 --evaluation-days 10
```

This writes `memory/ablation_report.json`. Historical news is intentionally excluded because a retrospective GPT score would risk using later information; live news remains a residual shock after accounting for visible futures moves.

If you separately obtain verified access to Tankerkönig's historical CSV repository, it can be imported as authoritative observations:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/import_tankerkoenig_history.py \
  --repo /path/to/tankerkoenig-data \
  --since 2026-04-01
```

The model can run without this. It starts with conservative priors and learns every day from the 11:50 captures.

## Files created over time

All generated and configuration files are kept under `memory/`:

- `memory/observations.jsonl` — real 11:50 regional targets
- `memory/capture_status.json` — latest accepted/rejected capture status
- `memory/capture_rejections.jsonl` — rejected attempts with reasons and attempted data
- `memory/capture_recovery_request.json` — pending or resolved request for verified historical recovery
- `memory/noon_resets.jsonl` — separate post-12 reset proxies; never 11:50 truth
- `memory/noon_reset_status.json` — latest accepted/rejected reset-capture status
- `memory/noon_shadow_forecast.json` — current shadow-only D+1 revision
- `memory/noon_shadow_history.jsonl` — all issued reset-based shadow revisions
- `memory/noon_shadow_evaluations.jsonl` / `noon_shadow_report.json` — matured comparisons against later 11:50 targets
- `memory/market_history.jsonl` — morning market snapshots
- `memory/bootstrap_noon.jsonl` — public tankzeit noon history, kept separate from 11:50 truth
- `memory/bootstrap_market.jsonl` — prior-day Brent, distillate, EUR/USD, and EUR-converted historical inputs
- `memory/news_signal_draft.json` — today's point-in-time GPT event draft
- `memory/news_signal.json` — deterministically weighted residual-news score
- `memory/news_history.jsonl` — deduplicated event/update audit trail for future learning
- `memory/forecast.json` — current 5-day output
- `memory/forecast_history.jsonl` — all old forecasts
- `memory/pending_training.json` — forecasts waiting for future outcome
- `memory/model.json` — learned online coefficients, error, sample counts
- `memory/manual_station_observations.jsonl` — user-confirmed individual station prices; used only to calibrate that place when a matching regional 11:50 target also exists, never as a regional model target

Each forecast day also contains `revision_ct`: the change from the latest older forecast for the same target date. To keep the Scriptable widget compact, only today's otherwise useless `+0.0ct` line is replaced by this revision. Future days continue to show their expected difference from today; no additional row is added. A dash means that no older forecast exists for today yet.

## What is predicted?

The regional target is the **median of the five cheapest open stations** in the 25 km Oberkrämer-centered market. This is more stable than a single accidental minimum.

Germendorf, Hohen Neuendorf and Oberkrämer receive separate learned offsets from the regional cheap reference.


## Tankerkönig API usage note

Tankerkönig explicitly asks clients to avoid high-frequency/background polling and to use `list.php`/`prices.php` efficiently. This package makes only one regional request per workflow invocation and never loops over stations. The two captures are single daily snapshots rather than polling; the widget's separate live request remains on demand.
