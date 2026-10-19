# Demographic Data Files

Each region is one JSON file, named `{region_id}.json`.

## Built-in Regions

| File | Region | Age/Gender Source | Education Source | Income Source | City Tier Source |
|------|--------|-------------------|-----------------|---------------|------------------|
| `china.json` | China | UN WPP 2024 | World Bank + 7th Census | World Bank PIP | GaWC 2024 |
| `usa.json` | United States | UN WPP 2024 | World Bank Gender Stats | World Bank PIP | — |
| `gbr.json` | United Kingdom | UN WPP 2024 | World Bank Gender Stats | World Bank PIP | — |
| `deu.json` | Germany | UN WPP 2024 | World Bank Gender Stats | World Bank PIP | — |
| `jpn.json` | Japan | UN WPP 2024 | World Bank Gender Stats | World Bank PIP | — |
| `fra.json` | France | UN WPP 2024 | World Bank Gender Stats | World Bank PIP | — |

## Adding a New Region

1. Create `{region_id}.json`
2. Include `meta` with `source_url` pointing to verifiable data
3. Include `age` and `gender` distributions
4. `education`, `income`, `city_tier`, `urbanization` are optional

## Data Quality

- Each distribution must sum to 1.0 (±5%)
- `source_url` is required in `meta`
- Estimates must be flagged in `data_notes`
- Run validation: `from survey.engine.data import validate_region_data`

## Source Key

| Data Type | Primary Source | URL |
|-----------|---------------|-----|
| Age/Gender | UN World Population Prospects 2024 | https://population.un.org/wpp/ |
| Education | World Bank Gender Statistics | https://databank.worldbank.org/source/gender-statistics/ |
| Income | World Bank PIP | https://pip.worldbank.org/ |
| City Classification | GaWC 2024 | https://gawc.lboro.ac.uk/ |
| Urbanization | UN World Urbanization Prospects | https://population.un.org/wup/ |
