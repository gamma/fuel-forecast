# Contributing

Contributions are welcome.

## Before opening a pull request

1. Keep `memory/` and all API keys out of commits.
2. Run the unit tests available in `tests/`.
3. Rebuild the skill package after changing `fuel-forecast-skill/`:

   ```sh
   ./build_skill_zip.sh
   ```

4. Keep forecasts and safety claims conservative. Never fabricate historical
   fuel observations or silently treat individual station values as regional
   ground truth.

## Scope

Useful contributions include regional configuration improvements, robust data
validation, transparent news-source handling, tests, documentation, and support
for additional public fuel-market proxies. Please open an issue first for large
model or data-source changes.
