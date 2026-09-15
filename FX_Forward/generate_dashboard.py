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
