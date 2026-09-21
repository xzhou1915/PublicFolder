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
EMBEDDED_TEMPLATE_B64 = """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
qrPY7ZYCsimXY0rhorwJSCfdz8xPZLIBEYfuhaXA3z36kc8OwHb6pbBoLwSp7V45KEiJ4EHYLgUleyHHVk4BioogNijnAk5qVzCB
a0EJMNiLjpTWdhVqbi9aVfOGUhP5Gh/8EmCwF+2UE1EFNBOejoGGnL2QRiA/bRl7EUoZD1sloGQvBL86QQkkSoI+DQWAZC8K1oIo
Zy/kXPklkDhJ7bDIAEY5iyHY1InKIWn2O34558liRJql9AtBn6bWt18OyWa9LRC/O/lCcSge//Dih1fn4EzcOUoideC4vErA9ZiD
hE/YiVrwhJKOBEOncLnO/kRB+cOrb5+8AoxvjxSMR55zRIjwF2p/dKE2enz26tXP0GiZfHDOk23t7RGIAcLCJOM/MIVHF3W1xaOz
8+fnv57/8ObV4ydaQ2A19fbqRabF+Zsff/zh1etfXzz5LtPgGWvwNNPgx7PnjDfc7zviM3k0UM+N4+0xaBs4EhuCXTh7cQ3mEZ+H
TFMkMm3K/mKEiIPa+GzNITBfxx/QP0fWct7hU745d057tPDuKLtDe8RRTHdL5n1C57MtuJAvIPao0eclypW0OO51stnNt0o/rCeW
74QejtSn/7RbYWg6dKbxfJOkNzWtnRq+pq+K4K1/wn99QCdpNVn8Kh7eHzpBSoWgA0NxaIrwbwlOkuM4s6lTY++HQJF7pLZmbzlh
33yjIHDuO8GF0oSP6T79rRKTHqqH/0tgZOlAv2S/pbTsGYBOkneEXXNYnTrG3+b1bnNVIwKa2/VsUcPz0PI8luglqdiHeCuoLEYp
Aba79ZLDafdfSLm4xnuSQS5quAealQk6822jyQQXFiaS2KYJwRLe6lg7/vMvu6dPnj49Bmk+qjdJ4GrHv6wf/rI8rjchNiexc4an
TBY4qU121lPt0Wo1T+IlAyRIj81MHVtkhWQ6S+YTpCAv1rq0MEAueM6XMEcRSgAbGOPcO7xX8as7KSr7Aaa8wIbBvEf8CMXNO5gm
zs3lbj5XJYVR9Baz+p4z2nnOeHz7Kv7gsRCefoNwFP69QH0hek6yMg9B7pC3a25Xb/CDpcfxJqnVs5As0TR0vqe62JroIgcHPf7E
pYp1zuTzyPn0yTn+Mw7hq+NZE9MpNfa+7jykkTkDgZs/1/n5Jczy5K69b8DPkP/86pghQg7UsYMvRzv6B4eF/zKEzdnmKV6onTCq
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"""


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
