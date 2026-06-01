"""
Convert WVS cross-national CSV to single calibrator JSON.

All countries in one file. Load once, filter by country at runtime.

Usage:
    # Create benchmark data (auto-detects B_COUNTRY_ALPHA for 3-letter codes)
    python scripts/convert_wvs_to_benchmark.py --input WVS_Cross-National_Wave_7_csv_v6_0.csv --output data/benchmarks/wvs_data.json

    # List available countries
    python scripts/convert_wvs_to_benchmark.py --input WVS_Cross-National_Wave_7_csv_v6_0.csv --list-countries
"""

import json
import argparse
import os
from collections import Counter

VARIABLES = {
    "Q260": {"text": "Age", "type": "single_choice"},
    "Q261": {"text": "Gender", "type": "single_choice"},
    "Q262": {"text": "Education level", "type": "single_choice"},
    "Q270": {"text": "Employment status", "type": "single_choice"},
    "Q288": {"text": "Income level", "type": "single_choice"},
    "Q49": {"text": "Most people can be trusted", "type": "single_choice"},
    "Q50": {"text": "Satisfaction with life", "type": "scale"},
    "Q221": {"text": "Confidence: Government", "type": "single_choice"},
    "Q222": {"text": "Confidence: Universities", "type": "single_choice"},
    "Q223": {"text": "Confidence: Press", "type": "single_choice"},
    "Q224": {"text": "Confidence: Courts", "type": "single_choice"},
}

# ISO 3166-1 numeric (0-padded) -> (alpha-3, country_name)
# Covers all 66 countries in WVS Wave 7 CSV (v6.0)
_ISO_NUMERIC_TO_ALPHA = {
    "004": ("AFG", "Afghanistan"),
    "008": ("ALB", "Albania"),
    "012": ("DZA", "Algeria"),
    "020": ("AND", "Andorra"),
    "024": ("AGO", "Angola"),
    "032": ("ARG", "Argentina"),
    "036": ("AUS", "Australia"),
    "040": ("AUT", "Austria"),
    "050": ("BGD", "Bangladesh"),
    "051": ("ARM", "Armenia"),
    "068": ("BOL", "Bolivia"),
    "076": ("BRA", "Brazil"),
    "100": ("BGR", "Bulgaria"),
    "104": ("MMR", "Myanmar"),
    "112": ("BLR", "Belarus"),
    "124": ("CAN", "Canada"),
    "144": ("LKA", "Sri Lanka"),
    "148": ("TCD", "Chad"),
    "152": ("CHL", "Chile"),
    "156": ("CHN", "China"),
    "158": ("TWN", "Taiwan"),
    "170": ("COL", "Colombia"),
    "180": ("COD", "Democratic Republic of the Congo"),
    "196": ("CYP", "Cyprus"),
    "203": ("CZE", "Czechia"),
    "204": ("BEN", "Benin"),
    "208": ("DNK", "Denmark"),
    "218": ("ECU", "Ecuador"),
    "231": ("ETH", "Ethiopia"),
    "233": ("EST", "Estonia"),
    "246": ("FIN", "Finland"),
    "250": ("FRA", "France"),
    "268": ("GEO", "Georgia"),
    "276": ("DEU", "Germany"),
    "288": ("GHA", "Ghana"),
    "300": ("GRC", "Greece"),
    "320": ("GTM", "Guatemala"),
    "324": ("GIN", "Guinea"),
    "344": ("HKG", "Hong Kong SAR"),
    "348": ("HUN", "Hungary"),
    "352": ("ISL", "Iceland"),
    "356": ("IND", "India"),
    "360": ("IDN", "Indonesia"),
    "364": ("IRN", "Iran"),
    "368": ("IRQ", "Iraq"),
    "372": ("IRL", "Ireland"),
    "376": ("ISR", "Israel"),
    "380": ("ITA", "Italy"),
    "392": ("JPN", "Japan"),
    "398": ("KAZ", "Kazakhstan"),
    "400": ("JOR", "Jordan"),
    "404": ("KEN", "Kenya"),
    "408": ("PRK", "North Korea"),
    "410": ("KOR", "South Korea"),
    "414": ("KWT", "Kuwait"),
    "417": ("KGZ", "Kyrgyzstan"),
    "422": ("LBN", "Lebanon"),
    "426": ("LSO", "Lesotho"),
    "428": ("LVA", "Latvia"),
    "434": ("LBY", "Libya"),
    "440": ("LTU", "Lithuania"),
    "442": ("LUX", "Luxembourg"),
    "446": ("MAC", "Macao SAR"),
    "450": ("MDG", "Madagascar"),
    "454": ("MWI", "Malawi"),
    "458": ("MYS", "Malaysia"),
    "462": ("MDV", "Maldives"),
    "466": ("MLI", "Mali"),
    "470": ("MLT", "Malta"),
    "478": ("MRT", "Mauritania"),
    "484": ("MEX", "Mexico"),
    "496": ("MNG", "Mongolia"),
    "504": ("MAR", "Morocco"),
    "508": ("MOZ", "Mozambique"),
    "512": ("OMN", "Oman"),
    "516": ("NAM", "Namibia"),
    "524": ("NPL", "Nepal"),
    "528": ("NLD", "Netherlands"),
    "540": ("NCL", "New Caledonia"),
    "548": ("VUT", "Vanuatu"),
    "554": ("NZL", "New Zealand"),
    "558": ("NIC", "Nicaragua"),
    "562": ("NER", "Niger"),
    "566": ("NGA", "Nigeria"),
    "578": ("NOR", "Norway"),
    "586": ("PAK", "Pakistan"),
    "591": ("PAN", "Panama"),
    "598": ("PNG", "Papua New Guinea"),
    "600": ("PRY", "Paraguay"),
    "604": ("PER", "Peru"),
    "608": ("PHL", "Philippines"),
    "616": ("POL", "Poland"),
    "620": ("PRT", "Portugal"),
    "624": ("GNB", "Guinea-Bissau"),
    "630": ("PRI", "Puerto Rico"),
    "634": ("QAT", "Qatar"),
    "642": ("ROU", "Romania"),
    "643": ("RUS", "Russia"),
    "646": ("RWA", "Rwanda"),
    "682": ("SAU", "Saudi Arabia"),
    "686": ("SEN", "Senegal"),
    "688": ("SRB", "Serbia"),
    "694": ("SLE", "Sierra Leone"),
    "702": ("SGP", "Singapore"),
    "703": ("SVK", "Slovakia"),
    "704": ("VNM", "Vietnam"),
    "705": ("SVN", "Slovenia"),
    "710": ("ZAF", "South Africa"),
    "716": ("ZWE", "Zimbabwe"),
    "724": ("ESP", "Spain"),
    "728": ("SSD", "South Sudan"),
    "729": ("SDN", "Sudan"),
    "732": ("ESH", "Western Sahara"),
    "740": ("SUR", "Suriname"),
    "748": ("SWZ", "Eswatini"),
    "752": ("SWE", "Sweden"),
    "756": ("CHE", "Switzerland"),
    "760": ("SYR", "Syria"),
    "762": ("TJK", "Tajikistan"),
    "764": ("THA", "Thailand"),
    "768": ("TGO", "Togo"),
    "780": ("TTO", "Trinidad and Tobago"),
    "784": ("ARE", "United Arab Emirates"),
    "788": ("TUN", "Tunisia"),
    "792": ("TUR", "Turkey"),
    "800": ("UGA", "Uganda"),
    "804": ("UKR", "Ukraine"),
    "807": ("MKD", "North Macedonia"),
    "818": ("EGY", "Egypt"),
    "826": ("GBR", "United Kingdom"),
    "834": ("TZA", "Tanzania"),
    "840": ("USA", "United States"),
    "854": ("BFA", "Burkina Faso"),
    "858": ("URY", "Uruguay"),
    "860": ("UZB", "Uzbekistan"),
    "862": ("VEN", "Venezuela"),
    "887": ("YEM", "Yemen"),
    "894": ("ZMB", "Zambia"),
    # Non-standard / UN-administered territories
    "909": ("XKX", "Kosovo"),
}

# Fallback: known alpha-3 codes not in ISO 3166-1 (e.g., sub-national entities)
_ALPHA3_NAME_FALLBACK = {
    "NIR": ("NIR", "Northern Ireland"),
}

# Prefer alpha-3 column; fallback detection order
_COUNTRY_COLUMNS_PREFERRED = ["B_COUNTRY_ALPHA", "B_COUNTRY", "COUNTRY_ALPHA", "country", "COUNTRY", "S003"]


def _lookup_country(raw: str) -> tuple:
    """Map a raw country code from CSV to (alpha3, country_name).
    Returns (raw, raw) if unmapped, so the caller can still use the raw value.
    """
    u = raw.strip().upper()
    # Already a valid 3-letter code?
    if len(u) == 3 and u.isalpha():
        # Check fallback map first (non-ISO codes like NIR)
        fallback = _ALPHA3_NAME_FALLBACK.get(u)
        if fallback:
            return fallback
        # Find if this exists as alpha-3 in our map
        for _k, (a3, name) in _ISO_NUMERIC_TO_ALPHA.items():
            if a3 == u:
                return (a3, name)
        # Unknown 3-letter code — use as-is
        return (u, u)

    # Try numeric -> alpha-3
    # Zero-pad to 3 digits
    try:
        numeric = int(u)
    except ValueError:
        return (u, u)

    key = f"{numeric:03d}"
    mapped = _ISO_NUMERIC_TO_ALPHA.get(key)
    if mapped:
        return mapped

    # Not in map — use raw
    return (u, u)


def list_countries(path):
    import csv
    seen = Counter()
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        col = next((c for c in _COUNTRY_COLUMNS_PREFERRED if c in r.fieldnames), None)
        if not col:
            print("Country column not found")
            return
        for row in r:
            v = str(row.get(col, "")).strip().upper()
            if v:
                seen[v] += 1
    header = f"--- Countries ({len(seen)}) ---"
    print(header)
    for k, v in seen.most_common():
        a3, name = _lookup_country(k)
        print(f"  {k:>6s}  ->  {a3:3s}  {name:30s}  (n={v})")


def convert(in_path, out_path):
    import csv
    with open(in_path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        col = next((c for c in _COUNTRY_COLUMNS_PREFERRED if c in r.fieldnames), None)
        assert col, f"Country column not found in {r.fieldnames[:15]}"
        print(f"Country column: {col}")

        pools = {}
        total = 0
        for row in r:
            total += 1
            raw_cc = str(row.get(col, "")).strip().upper()
            if not raw_cc:
                continue
            # Resolve to alpha-3 key
            a3, country_name = _lookup_country(raw_cc)
            if a3 not in pools:
                pools[a3] = {"country_name": country_name, "questions": {v: Counter() for v in VARIABLES}}
            for v in VARIABLES:
                val = row.get(v, "").strip()
                if val and val not in {"", ".", "NA", "-1", "-2", "-3", "-4", "-5"}:
                    pools[a3]["questions"][v][val] += 1
            if total % 100000 == 0:
                print(f"  {total} rows...")

    result = {
        "source": "WVS Wave 7 (2017-2022)",
        "source_url": "https://www.worldvaluessurvey.org",
        "countries": {},
    }
    for cc in sorted(pools):
        entry = pools[cc]
        questions = {}
        for v, counter in entry["questions"].items():
            n = sum(counter.values())
            if n == 0:
                continue
            questions[v] = {
                "text": VARIABLES[v]["text"],
                "type": VARIABLES[v]["type"],
                "n": n,
                "distribution": {k: round(v / n, 4) for k, v in counter.most_common()},
            }
        samples = [q["n"] for q in questions.values()]
        result["countries"][cc] = {
            "country_name": entry["country_name"],
            "sample_size": max(samples) if samples else 0,
            "questions": questions,
        }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    unmapped = [cc for cc in pools if cc == pools[cc].get("country_name", "")]
    note = f" ({len(unmapped)} unmapped codes)" if unmapped else ""
    print(f"\n{total} rows, {len(result['countries'])} countries{note} -> {out_path}")
    if unmapped:
        print(f"  Unmapped codes: {unmapped}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="data/benchmarks/wvs_data.json")
    p.add_argument("--list-countries", action="store_true")
    args = p.parse_args()
    if args.list_countries:
        list_countries(args.input)
    else:
        convert(args.input, args.output)
