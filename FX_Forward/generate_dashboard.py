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
cnH52f8HdCm39lLYAAA="""


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
