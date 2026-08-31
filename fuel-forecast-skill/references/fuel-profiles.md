# Fuel and news profiles

FuelForecast supports Tankerkönig fuels `diesel`, `e5`, and `e10`. The price target,
local learning data and recommendations are fuel-specific: use a separate `memory`
folder/configuration per fuel if you want to forecast more than one fuel.

## `news.profile`

Set one of these in the active `memory/config.json`:

- `diesel_europe`: German refinery/distribution, European diesel/gasoil imports,
  Gulf distillate cargoes, crude and shipping. Default for `diesel`.
- `gasoline_europe`: German refinery/distribution, European gasoline/blending
  component imports, refinery/petrochemical outages, crude and shipping. Default
  for `e5` and `e10`.
- `custom`: use only the user-defined `news.channels` categories and
  `news.research_topics`.

`news.channels` is an optional object with the model's three transmission paths:
`domestic_supply`, `european_imports`, and `global_crude_shipping`. Each value is
a list of schema-v2 event categories. `news.research_topics` is an optional list
of additional, plain-language subjects the daily news research must cover.

Example for E10:

```json
"news": {
  "profile": "gasoline_europe",
  "research_topics": ["EU gasoline stocks", "RBOB gasoline futures"],
  "channels": {
    "domestic_supply": ["domestic_refinery", "domestic_distribution", "refinery_outage"],
    "european_imports": ["european_gasoline_imports", "gasoline_blending_supply", "sanctions_export_policy"],
    "global_crude_shipping": ["opec_policy", "geopolitics_shipping", "inventory_demand", "macro_fx", "market_commentary", "other"]
  }
}
```

Use a category once only. The news processor still discounts source confidence,
age, repeats and effects already visible in futures. A configuration changes
classification, not those safeguards.
