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
naY7f32oZ60Pau9f3OaDxW8P67rN5x3mWH3FaDdTVr+mmvFO1+ppaUbOHmeeGFtgzAHbG1bCagFYnHqQMQ5P0tlSNcja7OYAYNVi
N0OawmTV8CyoYlXPbHlnCYIye1F01eZ0CdaDuzmdsTxhEszWRTBbHGyaaoaGx9j5qIZYu2wkbGThR97cqtQFuvlV8yaZfLhLmfDM
ucuZMMmXDuNIDhqwmOKBsMqHW2FH5AXWWMDSez7B1hhZN8zNnBlXJS81acd/8F6BCYiG0xmYC4+KInGzGlOF6jyQIb+uKY8adfaI
b9/BTPDMR1CNNstJkGyGpfDIXSC+F6MCNC25lUTE6auSGv9hy9cEpsMUqKlkpSM7AiOJY2BbBUbKOU14ThTaNKJQTkESP+rIDHvY
tbjymjNby/b1U3FWw4hnRJwjBqEFCEqEUQuzO9EQ9Q4LPDpp95N5jMYeqKrSnJZiE9LINyF36WzX77E2bDe1bvF70iSldT1gWfA0
rBYEmSNspkEsw9Lfm3FVMoCaHEAq+3unWQDcato7TADispueM+gSfQuwuWsXK9ROW6HW51ihdpEVauVZIWaAGvzH77NCjS9shVpF
VqhjWqFGthVqp6xQr8gKNQ6wQs0sK9QusEJ1RyuUZxNtZqjnYIYUK96njYOaoxlqupuhxhcwQ6LKO88MNQ8wQ81iM9QqMEONg8xQ
Qw6gwAzh9857x3XAbobOiUEen3jNFI2Wax7/oD1KZWMUTW7ZkjApm5MvXC13GckXp7Gpxkb1VetE53Nux0wYMqXO6rOaA7ex/Snx
YgrG3mMi6sXz1XW0mW6I15ljk0zkgm0aFsoDFEQ3lWpYi+d5HKxur9fx5noJQxqCRIyueWL7Xjdqdo08zWQyCcetE6UEhJ1y1aDk
27241YsaTTsTHv/TDsY/i29A/LFsbSRkMV5H69H17e9jRa2dzqeYrFhAYBepmVM9OLhi6zMvrNtu11NYLoU+rOk1Meg9DHth7Frm
7dI2jV1auWeoLCfM6TU7ecvSN5dmNMnh4o+gVWPSfn6iiDhQJFVGZmvUnyxHu03lZrqZIorlbksVtPUk5OOVsvxNZTmZYH1TU0WH
uRQlERZqnmvXlvoUFbrpUrd0jlPvJ2fAyo5fxiEptjNSMtGzwpE7o0ZvNBrGhjqEk9ZkmI3mMzlcNzlsxMd5m18tp5SI+gEc+/7N
1qE3zdu27uRtyGAeMFWFwjooG10xVdaLtBTVaOh500ba5El8EdWEMwNiLy1o6mpn+ojtrO1SLrSZPeVrqgoN7tkX2D/tppLJ1s5o
m1LVTjMxnCpwMk0opcVkq3g2m65g2cqTH7V/bqWx0iYU52NmTV5lPt3Moy0sP2qlTO24UjtRt1PSO/7JjknOipWfElTM43y1vU1T
UKhR+6/Y1yeKC8eKnu7SS8dhNT3aenXMTqx+gPEiO586mi7wRJfNZuBTCZbPDpB+wCqrTvkHHw/G0xsBRkXv/qk8djf1jj4a8E+f
/OnBMbzSAZO/4O+VaMY/L/BPf1qutxPQmKWHdhmk5SpejOIHxyut3XUNj8JOYP/2z/+WHIw9vPUuuPzAcGtK9yo1+h/KCJTqdXWM
9MW74FPyCYTvTcfiwTn+fXpxu9he4ycW3iaCGQLasWkGJhlz+6dnG285+W4x3KxO8CRv+hQfcc+oXP97+OmfwjhxLvHdqY5XGQ6b
Y5w69ueGe+W8S15b5nt4UjEz0wP/+2hzPVxipTUP9Te+jTfqtxmZzKHD8fzTB1P9CZYJw9Pj6SkDJ77Rm9dgIvzT58sIddSLxTwC
b6K//fP/4ePMHK6dQqqcU0lk65GQUkpj+N5kuWbnhz3D88R8Tcbw7DE8sf3R8uPApyqWJvzfx8OcgGFonn06MeF9PPDVgyDEU6bE
A79W7XJeM5MJNK53MJcPVtH22gMmvKjVvVr75+YcOnneqba8brWFz5qzJvwB/71oQXh304zqXp2f/ge/XddC9UGlflNp+sfIppsr
dRzIVu/84mdFC4gVCmvYmcc4HwkrPOVsNQ8LzVfbgV8dbW4CNOjH8IvKXP6FgsFdxKh8ECRw8tenr/CVVBL2VJUp9p0bx8nFkiEd
7p5Qrb4uw+wZqv9wtwFfY7PxdoupMavLFekCrSsD/+z5c1C82UxvsXlwzMBU08HIsaobV7AMfcOPoHRCE7vFg5RE16I1GA6IV8So
USMBAcoUGPCBz84X077UzTDE8igx//RHYDN+3EOlOBaTrDYhxjAuL+IthTLc7OQ2ww+6wPTt5mDDvMSxoVhNKPTGsL98rJ85dvz0
zmHsP9DJG58xejqy48Dxn/GN58SG8RJt5pZ/WQawrxEdWPC92JeG2PTn6JU7C8ZJw59hwXBmw7PFaLYbxxtPfGC+iqbrVNe/d/yO
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
