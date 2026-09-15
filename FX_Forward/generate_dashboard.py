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
F2eLdLW8/OL/A8N9j4OF1gAA"""


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
