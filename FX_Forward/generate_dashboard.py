#!/usr/bin/env python3
"""Generate a self-contained FX exposure dashboard from exposure and rate CSVs."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


SAMPLE_PATTERN = re.compile(r"const SAMPLE_CSV = `[\s\S]*?`;")
REGIONAL_PATTERN = re.compile(r"const REGIONAL_CSV = .*?;")
LOCATION_MAP_PATTERN = re.compile(r"const LOCATION_BY_STRATEGY = .*?;")
PNL_DATA_PATTERN = re.compile(r"const PNL_DATA = .*?;")
LOAD_LABEL_PATTERN = re.compile(
    r'\s*<label class="button" for="fileInput">[\s\S]*?</label>'
)
FETCH_BLOCK = """    fetch('synthetic_fx_exposure.csv')
      .then(response => response.ok ? response.text() : Promise.reject(new Error('sample fetch failed')))
      .then(text => setData(text, 'synthetic_fx_exposure.csv'))
      .catch(() => setData(SAMPLE_CSV, 'Embedded synthetic sample'));"""

# The complete dashboard template is embedded so this script is portable.
# It is gzip-compressed and base64-encoded to keep the source compact.
EMBEDDED_TEMPLATE_B64 = """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
hvybPKQBAA=="""


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


def validate_rate_csv(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    populated_rows = 0
    seen: set[tuple[str, str]] = set()

    for line_number, row in enumerate(csv.reader(text.splitlines()), start=1):
        if not row or all(not field.strip() for field in row):
            continue
        populated_rows += 1
        if len(row) != 3:
            raise ValueError(
                f"Rate row {line_number} has {len(row)} columns; expected exactly 3."
            )

        date, ccy, value = (field.strip() for field in row)
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(
                f"Rate row {line_number} has an invalid Date: {date!r}."
            ) from error
        if not ccy:
            raise ValueError(f"Rate row {line_number} has an empty CCY3.")
        try:
            numeric_value = float(value)
        except ValueError as error:
            raise ValueError(
                f"Rate row {line_number} has an invalid Value: {value!r}."
            ) from error
        if not math.isfinite(numeric_value) or numeric_value <= 0:
            raise ValueError(
                f"Rate row {line_number} must have a positive finite Value."
            )

        key = (date, ccy.upper())
        if key in seen:
            raise ValueError(
                f"Rate row {line_number} duplicates {date} / {ccy.upper()}."
            )
        seen.add(key)

    if populated_rows == 0:
        raise ValueError("The rate CSV contains no data rows.")
    return text


def parse_exposure_rows(text: str) -> list[dict[str, str | float]]:
    rows = []
    for row in csv.reader(text.splitlines()):
        if not row or all(not field.strip() for field in row):
            continue
        cob_date, bu, ccy, delta, _var = (field.strip() for field in row)
        rows.append(
            {
                "date": cob_date,
                "bu": bu,
                "ccy": ccy.upper(),
                "delta": float(delta),
            }
        )
    return rows


def parse_rate_rows(text: str) -> dict[tuple[str, str], float]:
    rates = {}
    for row in csv.reader(text.splitlines()):
        if not row or all(not field.strip() for field in row):
            continue
        date, ccy, value = (field.strip() for field in row)
        rates[(date, ccy.upper())] = float(value)
    return rates


def pnl_exposure_snapshot(
    rows: list[dict[str, str | float]],
    date: str,
    business_unit: str,
) -> dict[str, float]:
    exposures: defaultdict[str, float] = defaultdict(float)
    krw_net = 0.0
    krw_seen = False

    for row in rows:
        if row["date"] != date:
            continue
        if business_unit != "ALL" and row["bu"] != business_unit:
            continue
        ccy = str(row["ccy"])
        delta = float(row["delta"])
        if ccy == "CNH/CNY":
            exposures["CNH"] += delta
        elif ccy == "BRL/BRF":
            exposures["BRL"] += delta
        elif ccy in {"CNH", "CNY", "BRL", "BRF"}:
            continue
        elif ccy in {"KRW", "KRO"}:
            krw_net += delta
            krw_seen = True
        else:
            exposures[ccy] += delta

    if krw_seen:
        exposures["KRW"] += krw_net
    return dict(exposures)


def build_pnl_payload(exposure_text: str, rate_text: str) -> dict:
    rows = parse_exposure_rows(exposure_text)
    rates = parse_rate_rows(rate_text)
    dates = sorted({str(row["date"]) for row in rows})
    business_units = sorted({str(row["bu"]) for row in rows})
    result = {
        "latestDate": dates[-1],
        "formula": "Prior exposure × (prior USDXXX rate / current USDXXX rate − 1)",
        "byBusinessUnit": {},
    }

    for business_unit in ["ALL", *business_units]:
        snapshots = {
            date: pnl_exposure_snapshot(rows, date, business_unit) for date in dates
        }
        currencies = sorted(
            {ccy for snapshot in snapshots.values() for ccy in snapshot}
        )
        currency_cumulative = {ccy: 0.0 for ccy in currencies}
        currency_incomplete = {ccy: False for ccy in currencies}
        book_cumulative = 0.0
        book_incomplete = False
        warnings: list[str] = []
        points = [
            {
                "date": dates[0],
                "bookDaily": 0.0,
                "bookCumulative": 0.0,
                "currencies": {
                    ccy: {"daily": 0.0, "cumulative": 0.0}
                    for ccy in currencies
                },
            }
        ]

        for previous_date, current_date in zip(dates, dates[1:]):
            previous_exposures = snapshots[previous_date]
            currency_values = {}
            book_daily = 0.0
            book_complete = True

            for ccy in currencies:
                exposure = previous_exposures.get(ccy, 0.0)
                if abs(exposure) < 1e-12:
                    daily_pnl = 0.0
                else:
                    previous_rate = rates.get((previous_date, ccy))
                    current_rate = rates.get((current_date, ccy))
                    if previous_rate is None or current_rate is None:
                        daily_pnl = None
                        missing_dates = []
                        if previous_rate is None:
                            missing_dates.append(previous_date)
                        if current_rate is None:
                            missing_dates.append(current_date)
                        warnings.append(
                            f"{ccy}: missing USD{ccy} rate for "
                            + " and ".join(missing_dates)
                        )
                    else:
                        daily_pnl = exposure * (previous_rate / current_rate - 1.0)

                if daily_pnl is None:
                    currency_incomplete[ccy] = True
                    cumulative = None
                    book_complete = False
                else:
                    if not currency_incomplete[ccy]:
                        currency_cumulative[ccy] += daily_pnl
                        cumulative = currency_cumulative[ccy]
                    else:
                        cumulative = None
                    book_daily += daily_pnl
                currency_values[ccy] = {
                    "daily": daily_pnl,
                    "cumulative": cumulative,
                }

            if book_complete:
                if not book_incomplete:
                    book_cumulative += book_daily
                    displayed_book_cumulative = book_cumulative
                else:
                    displayed_book_cumulative = None
            else:
                book_incomplete = True
                book_daily = None
                displayed_book_cumulative = None

            points.append(
                {
                    "date": current_date,
                    "bookDaily": book_daily,
                    "bookCumulative": displayed_book_cumulative,
                    "currencies": currency_values,
                }
            )

        result["byBusinessUnit"][business_unit] = {
            "currencies": currencies,
            "points": points,
            "warnings": sorted(set(warnings)),
        }

    return result


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
    rate_path: Path,
    output_path: Path,
    regional_path: Path | None = None,
    location_map_path: Path | None = None,
) -> None:
    input_path = input_path.resolve()
    rate_path = rate_path.resolve()
    output_path = output_path.resolve()
    regional_path = regional_path.resolve() if regional_path is not None else None
    location_map_path = (
        location_map_path.resolve() if location_map_path is not None else None
    )

    if (regional_path is None) != (location_map_path is None):
        raise ValueError(
            "--regional-csv and --location-map must be supplied together."
        )
    if output_path in {input_path, rate_path, regional_path, location_map_path}:
        raise ValueError("The output HTML path cannot overwrite an input file.")

    csv_text = validate_csv(input_path)
    rate_text = validate_rate_csv(rate_path)
    pnl_payload = build_pnl_payload(csv_text, rate_text)
    pnl_payload["rateSource"] = rate_path.name
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
    embedded_pnl_data = (
        "const PNL_DATA = "
        + json.dumps(pnl_payload, separators=(",", ":"), sort_keys=True)
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
    html, pnl_count = PNL_DATA_PATTERN.subn(
        lambda _match: embedded_pnl_data, html, count=1
    )
    if pnl_count != 1:
        raise RuntimeError(
            "Could not locate the P&L data hook in the embedded template."
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
        "rate_csv",
        type=Path,
        help="Headerless rate CSV: Date, CCY3, USDXXX Value",
    )
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
    if not args.rate_csv.is_file():
        parser.error(f"Rate CSV file not found: {args.rate_csv}")
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
            args.rate_csv,
            output_path,
            args.regional_csv,
            args.location_map,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"Created static dashboard: {output_path.resolve()}")


if __name__ == "__main__":
    main()
