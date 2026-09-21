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
    expected_locations = {"Beijing", "Shanghai", "Hong Kong"}
    if not isinstance(data, dict) or set(data) != expected_locations:
        raise ValueError(
            "Location map must contain Beijing, Shanghai, and Hong Kong lists."
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
        help="JSON mapping of Beijing, Shanghai, and Hong Kong to strategy names",
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
