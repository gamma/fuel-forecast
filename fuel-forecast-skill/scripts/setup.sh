#!/bin/sh
set -eu
DATA="${FUEL_FORECAST_DATA_DIR:-/var/minis/mounts/FuelForecast/memory}"
if [ ! -d "$DATA" ]; then
  DATA="/var/minis/memory/fuel-forecast"
  mkdir -p "$DATA"
fi
echo "FuelForecast data directory: $DATA"
if [ ! -f "$DATA/config.json" ]; then
  echo "config.json missing. Copy references/config.example.json to $DATA/config.json and set your Tankerkönig API key."
  exit 2
fi
python3 -V
echo "Setup OK."
