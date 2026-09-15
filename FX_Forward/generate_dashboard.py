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
