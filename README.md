# FuelForecast

A self-hosted, local diesel-price forecast for Germany. It combines a single daily [Tankerkönig/MTS-K](https://creativecommons.tankerkoenig.de/) regional price snapshot, EUR-adjusted energy-market inputs and an auditable, residual news signal. It runs inside [Open Minis](https://openminis.app/); iOS users can optionally use the included Scriptable widget.

> **Experimental personal decision aid — not financial advice.** A forecast is uncertain, especially before enough local 11:50 observations have accumulated.

## What you configure

No code changes are required for a new area:

- location or exact coordinates;
- search radius and a friendly region name;
- fuel type (`diesel`, `e5`, or `e10`, subject to Tankerkönig support);
- a diesel, gasoline, or fully custom news profile;
- your own Tankerkönig API key;
- optional local place labels and forecast thresholds.

The active configuration and all generated data remain in `memory/` and are ignored by Git. Never commit or publish `memory/config.json` because it contains your API key.

## Quick start

### 1. Install Open Minis and import the skill

Download or clone this repository, then import `fuel-forecast-skill.zip` in Open Minis. If you cloned the repository and want to rebuild the package:

```sh
./build_skill_zip.sh
```

### 2. Create your private local configuration

**Recommended — interactive helper:**

```sh
python3 /var/minis/skills/fuel-forecast/scripts/configure.py
```

It asks for a German town/address, lets you choose an OpenStreetMap result, and securely prompts for your Tankerkönig key. It writes exactly one active file:

```text
/var/minis/memory/fuel-forecast/config.json
```

If you use a mounted folder called `FuelForecast`, it writes to:

```text
/var/minis/mounts/FuelForecast/memory/config.json
```

You can also copy `fuel-forecast-skill/references/config.example.json` to the appropriate `memory/config.json` and edit it manually. The `region.center` coordinates, `region.radius_km`, `region.preferred_places`, `fuel`, and forecast thresholds are intentionally simple JSON settings.

### 3. Run one morning forecast

In Open Minis, ask:

> Run the fuel-forecast setup check and then execute one morning forecast.

The workflow writes `memory/forecast.json` and reports **TANKEN HEUTE**, **WARTEN** or **NEUTRAL** with uncertainty. It makes one regional Tankerkönig request per invocation; do not use it for high-frequency polling.

## Daily learning (optional, recommended)

The model learns from one genuine local snapshot around 11:50. Add a daily Open Minis task that runs:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode pre_noon
```

Run it only in the configured 11:40–12:00 local window. A separate 12:20 reset capture is available:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/capture_observation.py --mode noon_reset
```

The 12:20 data stays separate from the 11:50 learning target. Read the in-skill instructions for iOS Scriptable/Shortcuts and Android scheduling details.

## Model inputs and safeguards

- **Local ground truth:** Tankerkönig/MTS-K; target is the median of the five cheapest open stations in the configured area.
- **Markets:** Brent, a heating-oil/middle-distillate proxy and ECB EUR/USD rates.
- **News:** time-stamped, auditable events are discounted for age, repetition and effects already present in futures. Choose `news.profile` as `diesel_europe`, `gasoline_europe`, or `custom`; optional `news.research_topics` and `news.channels` make the research scope and the three model channels explicitly configurable. Diesel defaults distinguish domestic supply, European diesel imports (including Gulf-origin cargoes) and broad crude/shipping news. See `fuel-forecast-skill/references/fuel-profiles.md`.
- **No fabricated data:** an individual manually reported station price can improve only that local place after matching a true regional observation; it is never silently promoted to the regional training target.

## Project layout

```text
fuel-forecast-skill/      Open Minis skill and Python workflow
scriptable/               optional iOS capture and widget scripts
tests/                    regression tests
memory/                   local configuration and generated data (ignored)
```

## Privacy and API key safety

- Get a personal Tankerkönig API key from [Tankerkönig](https://creativecommons.tankerkoenig.de/).
- `memory/` is ignored by `.gitignore`; confirm this before every commit.
- Keep the repository private if your own operational notes matter. The source itself can be public only when no local `memory/` data or API keys are included.

## License

Released under the [MIT License](LICENSE).
