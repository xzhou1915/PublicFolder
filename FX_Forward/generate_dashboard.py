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
