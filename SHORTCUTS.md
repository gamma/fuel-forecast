# iOS Shortcuts setup

## One capture script, two daily automations

Both automations run the same `FuelForecastCapture` Scriptable source.

### 11:50 authoritative learning target

- Shortcuts → Automation → `+`
- Time of Day → 11:50 → Daily
- Add Action → Scriptable → Run Script
- Script: `FuelForecastCapture`
- Optional Parameter: `pre_noon` (otherwise the script detects the time)
- Set to Run Immediately
- Do not ask before running

### 12:20 separate noon reset

- Duplicate the 11:50 automation
- Change Time of Day to 12:20 → Daily
- Keep Script: `FuelForecastCapture`
- Optional Parameter: `noon_reset` (otherwise the script detects the time)
- Set to Run Immediately
- Do not ask before running

Run `FuelForecastCapture` manually once before enabling the automations so iCloud/network permissions are already granted. A manual run outside both windows is rejected before a network request, so use Scriptable's Run Script action at one of the scheduled times for the permission test.

Pre-noon observations are accepted only from 11:40 until just before 12:00 local time. Noon resets are accepted from 12:15 until just before 12:31. They are stored separately and the reset's D+1 correction remains shadow-only.

## Morning 07:00

On iOS, configure this in Apple's Shortcuts app; Minis' built-in Scheduled Tasks screen is Android-specific.

- Shortcuts → Automation → `+`
- Time of Day → 07:00 → Daily
- Choose Run Immediately
- Add Action → search for Minis or Open Minis
- If available, select Minis → Send Prompt
- paste this prompt:

> Run the fuel-forecast skill morning workflow now. Use GPT/web research for the last 48 hours of oil, diesel/distillate, refinery, OPEC+, sanctions and shipping news; create the schema-v2 news draft with exact publication timestamps and stable event IDs, process it, update the self-learning model, write forecast.json and send me a Diesel-Prognose OHV notification.

Run it manually once to grant permissions. If `Send Prompt` is not listed, an `Open App` action only launches Minis and does not execute the workflow; check which Minis actions the installed build exposes before relying on the automation.

A native `.shortcut` file is intentionally not included because third-party Shortcut files require Apple signing/import handling and are less portable than the five-step automation above.
