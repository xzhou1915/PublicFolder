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
T+S/7Mb1KXuD48XpIlstL7/4/3SRlUad2AAA"""


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


def generate(input_path: Path, output_path: Path) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()

    if input_path == output_path:
        raise ValueError("The output HTML path cannot overwrite the input CSV.")

    csv_text = validate_csv(input_path)
    html = load_template()
    embedded_data = "const SAMPLE_CSV = " + json.dumps(csv_text) + ";"

    # A callback keeps JSON escape sequences literal in JavaScript.
    html, sample_count = SAMPLE_PATTERN.subn(
        lambda _match: embedded_data, html, count=1
    )
    if sample_count != 1:
        raise RuntimeError("Could not locate the embedded-data hook in the embedded template.")

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
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path")
    args = parser.parse_args()

    input_path = args.csv_file
    if not input_path.is_file():
        parser.error(f"CSV file not found: {input_path}")
    output_path = args.output or input_path.with_name(
        f"{input_path.stem}_dashboard.html"
    )

    try:
        generate(input_path, output_path)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"Created static dashboard: {output_path.resolve()}")


if __name__ == "__main__":
    main()
