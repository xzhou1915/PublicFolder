#!/usr/bin/env python3
"""Generate a self-contained FX exposure dashboard from a headerless CSV."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import re
from datetime import datetime
from pathlib import Path


SAMPLE_PATTERN = re.compile(r"const SAMPLE_CSV = `[\s\S]*?`;")
REGIONAL_PATTERN = re.compile(r"const REGIONAL_CSV = .*?;")
LOCATION_MAP_PATTERN = re.compile(r"const LOCATION_BY_STRATEGY = .*?;")
LOAD_LABEL_PATTERN = re.compile(
    r'\s*<label class="button" for="fileInput">[\s\S]*?</label>'
)
FETCH_BLOCK = """    fetch('synthetic_fx_exposure.csv')
      .then(response => response.ok ? response.text() : Promise.reject(new Error('sample fetch failed')))
      .then(text => setData(text, 'synthetic_fx_exposure.csv'))
      .catch(() => setData(SAMPLE_CSV, 'Embedded synthetic sample'));"""

# The complete dashboard template is embedded so this script is portable.
# It is gzip-compressed and base64-encoded to keep the source compact.
EMBEDDED_TEMPLATE_B64 = """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"""


def load_template() -> str:
    encoded = "".join(EMBEDDED_TEMPLATE_B64.split())
    return gzip.decompress(base64.b64decode(encoded)).decode("utf-8")


def validate_csv(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    populated_rows = 0

    for line_number, row in enumerate(csv.reader(text.splitlines()), start=1):
        if not row or all(not field.strip() for field in row):
            continue
        populated_rows += 1
        if len(row) != 5:
            raise ValueError(
                f"Row {line_number} has {len(row)} columns; expected exactly 5."
            )

        cob_date, bu, ccy, delta, var = (field.strip() for field in row)
        try:
            datetime.strptime(cob_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(
                f"Row {line_number} has an invalid CobDate: {cob_date!r}."
            ) from error

        if not bu or not ccy:
            raise ValueError(f"Row {line_number} has an empty BU or CCY.")
        try:
            float(delta)
        except ValueError as error:
            raise ValueError(
                f"Row {line_number} has an invalid Delta value: {delta!r}."
            ) from error

        if var and var.lower() != "null":
            try:
                float(var)
            except ValueError as error:
                raise ValueError(
                    f"Row {line_number} has an invalid VaR value: {var!r}."
                ) from error

    if populated_rows == 0:
        raise ValueError("The CSV contains no data rows.")
    return text


def validate_regional_csv(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    populated_rows = 0

    for line_number, row in enumerate(csv.reader(text.splitlines()), start=1):
        if not row or all(not field.strip() for field in row):
            continue
        populated_rows += 1
        if len(row) != 5:
            raise ValueError(
                f"Regional row {line_number} has {len(row)} columns; "
                "expected exactly 5."
            )

        cob_date, business_unit, strategy, ccy, delta = (
            field.strip() for field in row
        )
        try:
            datetime.strptime(cob_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(
                f"Regional row {line_number} has an invalid CobDate: "
                f"{cob_date!r}."
            ) from error

        if not business_unit or not strategy or not ccy:
            raise ValueError(
                f"Regional row {line_number} has an empty label."
            )
        try:
            float(delta)
        except ValueError as error:
            raise ValueError(
                f"Regional row {line_number} has an invalid Delta value: "
                f"{delta!r}."
            ) from error

    if populated_rows == 0:
        raise ValueError("The regional CSV contains no data rows.")
    return text


def load_location_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    expected_locations = {"SG", "CH", "LATAM"}
    if not isinstance(data, dict) or set(data) != expected_locations:
        raise ValueError(
            "Location map must contain SG, CH, and LATAM lists."
        )

    result: dict[str, str] = {}
    for location, names in data.items():
        if not isinstance(names, list) or not all(
            isinstance(name, str) and name.strip() for name in names
        ):
            raise ValueError(f"{location} mapping must be a list of names.")
        for name in names:
            normalized = name.strip().upper()
            if normalized in result:
                raise ValueError(
                    f"StrategyLevelOne {name!r} appears in multiple locations."
                )
            result[normalized] = location
    return result


def generate(
    input_path: Path,
    output_path: Path,
    regional_path: Path | None = None,
    location_map_path: Path | None = None,
) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    regional_path = regional_path.resolve() if regional_path is not None else None
    location_map_path = (
        location_map_path.resolve() if location_map_path is not None else None
    )

    if (regional_path is None) != (location_map_path is None):
        raise ValueError(
            "--regional-csv and --location-map must be supplied together."
        )
    if output_path in {input_path, regional_path, location_map_path}:
        raise ValueError("The output HTML path cannot overwrite an input file.")

    csv_text = validate_csv(input_path)
    regional_text = (
        validate_regional_csv(regional_path) if regional_path is not None else ""
    )
    location_map = (
        load_location_map(location_map_path)
        if location_map_path is not None
        else {}
    )
    html = load_template()
    embedded_data = "const SAMPLE_CSV = " + json.dumps(csv_text) + ";"
    embedded_regional = (
        "const REGIONAL_CSV = " + json.dumps(regional_text) + ";"
    )
    embedded_location_map = (
        "const LOCATION_BY_STRATEGY = "
        + json.dumps(location_map, sort_keys=True)
        + ";"
    )

    # A callback keeps JSON escape sequences literal in JavaScript.
    html, sample_count = SAMPLE_PATTERN.subn(
        lambda _match: embedded_data, html, count=1
    )
    if sample_count != 1:
        raise RuntimeError("Could not locate the embedded-data hook in the embedded template.")

    html, regional_count = REGIONAL_PATTERN.subn(
        lambda _match: embedded_regional, html, count=1
    )
    if regional_count != 1:
        raise RuntimeError(
            "Could not locate the regional-data hook in the embedded template."
        )
    html, map_count = LOCATION_MAP_PATTERN.subn(
        lambda _match: embedded_location_map, html, count=1
    )
    if map_count != 1:
        raise RuntimeError(
            "Could not locate the location-map hook in the embedded template."
        )

    if FETCH_BLOCK not in html:
        raise RuntimeError("Could not locate the sample-loading hook in the embedded template.")
    html = html.replace(FETCH_BLOCK, "    setData(SAMPLE_CSV, 'Static report');", 1)
    html, label_count = LOAD_LABEL_PATTERN.subn("", html, count=1)
    if label_count != 1:
        raise RuntimeError("Could not locate the CSV loader control in the embedded template.")

    html = html.replace(
        "<!doctype html>",
        "<!doctype html>\n<!-- Self-contained report generated by generate_dashboard.py -->",
        1,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a standalone FX exposure HTML dashboard."
    )
    parser.add_argument("csv_file", type=Path, help="Headerless five-column FX CSV")
    parser.add_argument(
        "--regional-csv",
        type=Path,
        help=(
            "Headerless regional CSV: CobDate, BusinessUnit, "
            "StrategyLevelOne, CCY, Delta"
        ),
    )
    parser.add_argument(
        "--location-map",
        type=Path,
        help="JSON mapping of SG, CH, and LATAM to strategy names",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path")
    args = parser.parse_args()

    input_path = args.csv_file
    if not input_path.is_file():
        parser.error(f"CSV file not found: {input_path}")
    if args.regional_csv is not None and not args.regional_csv.is_file():
        parser.error(f"Regional CSV file not found: {args.regional_csv}")
    if args.location_map is not None and not args.location_map.is_file():
        parser.error(f"Location map file not found: {args.location_map}")
    output_path = args.output or input_path.with_name(
        f"{input_path.stem}_dashboard.html"
    )

    try:
        generate(
            input_path,
            output_path,
            args.regional_csv,
            args.location_map,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"Created static dashboard: {output_path.resolve()}")


if __name__ == "__main__":
    main()
