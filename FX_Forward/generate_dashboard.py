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
Lj/7/+G3hDB+2QAA"""


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
