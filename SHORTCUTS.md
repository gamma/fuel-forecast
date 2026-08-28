# iOS Shortcuts setup

## Required: 11:50 learning capture

This is the important Shortcut because it records the actual target used for model learning.

- Shortcuts → Automation → `+`
- Time of Day → 11:50 → Daily
- Add Action → Scriptable → Run Script
- Script: `FuelForecastCapture`
- Set to Run Immediately
- Do not ask before running

Run `FuelForecastCapture` manually once before enabling the automation so iCloud/network permissions are already granted.

Normal observations are accepted only from 11:40 until just before 12:00 local time. A manual test outside that window intentionally records only a rejection/recovery status and does not call Tankerkönig or change `observations.jsonl`.

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
