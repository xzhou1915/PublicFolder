#!/usr/bin/env python3
"""Generate the FXO dashboard from the 18-column headerless position file."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from plot_fx_option_greeks_dashboard import (
    GREEK_INPUT_COLUMNS,
    net_trades,
    write_html_dashboard,
)


INPUT_COLUMNS = [
    "CobDate",
    "Underlying",
    "Shore",
    "OptionType",
    "Strike",
    "ExpiryDate",
    "Delta",
    "Gamma",
    "ThetaPortCCY",
    "VegaPortCCY",
    "Notional",
    "NotionalCCY",
    "PnL",
    "PositionName",
    "Portfolio",
    "AssetType",
    "TradeDate",
    "UniqueID",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the FXO dashboard from a headerless 18-column CSV."
    )
    parser.add_argument("input_csv", type=Path, help="Headerless FXO position CSV")
    parser.add_argument(
        "--output",
        type=Path,
        help="Standalone HTML path (default: <input>_dashboard.html)",
    )
    return parser.parse_args()


def load_latest_snapshot(path: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    trades = pd.read_csv(path, header=None)
    if trades.shape[1] != len(INPUT_COLUMNS):
        raise ValueError(
            f"Expected {len(INPUT_COLUMNS)} columns, found {trades.shape[1]}"
        )

    trades.columns = INPUT_COLUMNS
    trades = trades.copy()
    for column in ("CobDate", "ExpiryDate", "TradeDate"):
        trades[column] = pd.to_datetime(trades[column], errors="raise")
    if trades["CobDate"].isna().any():
        raise ValueError("CobDate contains blank values")

    trades["OptionType"] = trades["OptionType"].astype(str).str.strip().str.title()
    invalid_types = sorted(set(trades["OptionType"]) - {"Call", "Put"})
    if invalid_types:
        raise ValueError(f"OptionType must be Call or Put; found: {invalid_types}")

    for column in GREEK_INPUT_COLUMNS.values():
        trades[column] = pd.to_numeric(trades[column], errors="raise")
        if trades[column].isna().any():
            raise ValueError(f"{column} contains blank values")

    latest_cob = trades["CobDate"].max()
    trades = trades.loc[trades["CobDate"].eq(latest_cob)].copy()
    trades["Pair"] = (
        trades["Underlying"]
        .astype(str)
        .str.strip()
        .str.replace(" Curncy", "", regex=False)
    )
    return trades, latest_cob


def main() -> None:
    args = parse_args()
    if not args.input_csv.is_file():
        raise FileNotFoundError(f"CSV file not found: {args.input_csv}")

    trades, as_of = load_latest_snapshot(args.input_csv)
    netted = net_trades(trades)
    if netted.empty:
        raise ValueError("The latest CobDate contains no trades to plot")

    output = args.output or args.input_csv.with_name(
        f"{args.input_csv.stem}_dashboard.html"
    )
    if output.suffix.lower() != ".html":
        raise ValueError("Output path must use the .html extension")

    write_html_dashboard(trades, netted, output, as_of)

    print(f"Latest CobDate: {as_of:%Y-%m-%d}")
    print(f"Dashboard HTML: {output.resolve()}")
    print(
        f"{len(trades)} latest-snapshot trades -> "
        f"{len(netted)} bubbles per Greek panel"
    )


if __name__ == "__main__":
    main()
