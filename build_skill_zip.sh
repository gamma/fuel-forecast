#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
rm -f fuel-forecast-skill.zip
(cd fuel-forecast-skill && zip -qr ../fuel-forecast-skill.zip . \
  -x '*/__pycache__/*' \
  -x '*.DS_Store')
unzip -tq fuel-forecast-skill.zip
VERSION=$(sed -n 's/^  version: *"\{0,1\}\([^" ]*\)"\{0,1\}$/\1/p' fuel-forecast-skill/SKILL.md | head -1)
test -n "$VERSION"
echo "Built FuelForecast skill v$VERSION: $ROOT/fuel-forecast-skill.zip"
