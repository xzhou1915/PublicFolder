#!/usr/bin/env python3
"""Generate a self-contained FX exposure dashboard from exposure and rate CSVs."""

from __future__ import annotations

import argparse
import base64
from bisect import bisect_right
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


def build_rate_history(
    rates: dict[tuple[str, str], float],
) -> dict[str, tuple[list[str], list[float]]]:
    history: defaultdict[str, list[tuple[str, float]]] = defaultdict(list)
    for (date, ccy), value in rates.items():
        history[ccy].append((date, value))
    result = {}
    for ccy, observations in history.items():
        observations.sort()
        result[ccy] = (
            [date for date, _value in observations],
            [value for _date, value in observations],
        )
    return result


def rate_on_or_before(
    history: dict[str, tuple[list[str], list[float]]],
    ccy: str,
    target_date: str,
) -> tuple[str, float] | None:
    observations = history.get(ccy)
    if observations is None:
        return None
    dates, values = observations
    index = bisect_right(dates, target_date) - 1
    if index < 0:
        return None
    return dates[index], values[index]


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
    rate_history = build_rate_history(rates)
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
        carried_rates: list[str] = []
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
                    previous_observation = rate_on_or_before(
                        rate_history, ccy, previous_date
                    )
                    current_observation = rate_on_or_before(
                        rate_history, ccy, current_date
                    )
                    if previous_observation is None or current_observation is None:
                        daily_pnl = None
                        missing_dates = []
                        if previous_observation is None:
                            missing_dates.append(previous_date)
                        if current_observation is None:
                            missing_dates.append(current_date)
                        warnings.append(
                            f"{ccy}: no USD{ccy} rate on or before "
                            + " and ".join(missing_dates)
                        )
                    else:
                        previous_source, previous_rate = previous_observation
                        current_source, current_rate = current_observation
                        if previous_source != previous_date:
                            carried_rates.append(
                                f"{ccy}: {previous_date} uses {previous_source} rate"
                            )
                        if current_source != current_date:
                            carried_rates.append(
                                f"{ccy}: {current_date} uses {current_source} rate"
                            )
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
            "carriedRates": sorted(set(carried_rates)),
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
