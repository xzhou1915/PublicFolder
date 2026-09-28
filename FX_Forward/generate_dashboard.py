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
            current_exposures = snapshots[current_date]
            currency_values = {}
            book_daily = 0.0
            book_complete = True

            for ccy in currencies:
                exposure = previous_exposures.get(ccy, 0.0)
                current_exposure = current_exposures.get(ccy, 0.0)
                if abs(exposure) < 1e-12 or abs(current_exposure) < 1e-12:
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
