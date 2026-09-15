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
