#!/usr/bin/env python3
"""Generate an HTML FXO dashboard from the 18-column headerless position file."""

from __future__ import annotations

import argparse
import html
from collections import defaultdict
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
NUMERIC_COLUMNS = [
    "Strike",
    *GREEK_INPUT_COLUMNS.values(),
    "Notional",
    "PnL",
]
PAIR_COLORS = [
    "#2463eb",
    "#8b58c7",
    "#14866d",
    "#d84b5b",
    "#d88917",
    "#0e7490",
    "#be4b9b",
    "#56752f",
    "#6b7280",
    "#7c3aed",
    "#0891b2",
    "#c2410c",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an HTML FXO dashboard from a headerless 18-column CSV."
    )
    parser.add_argument("input_csv", type=Path, help="Headerless FXO position CSV")
    parser.add_argument(
        "--output",
        type=Path,
        help="Standalone HTML path (default: <input>_dashboard.html)",
    )
    return parser.parse_args()


def load_position_history(
    path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    trades = pd.read_csv(path, header=None)
    if trades.shape[1] != len(INPUT_COLUMNS):
        raise ValueError(
            f"Expected {len(INPUT_COLUMNS)} columns, found {trades.shape[1]}"
        )

    trades.columns = INPUT_COLUMNS
    trades = trades.copy()

    for column in ("CobDate", "ExpiryDate", "TradeDate"):
        trades[column] = pd.to_datetime(trades[column], errors="raise")
        if trades[column].isna().any():
            raise ValueError(f"{column} contains blank values")

    trades["OptionType"] = trades["OptionType"].astype(str).str.strip().str.title()
    invalid_types = sorted(set(trades["OptionType"]) - {"Call", "Put"})
    if invalid_types:
        raise ValueError(f"OptionType must be Call or Put; found: {invalid_types}")

    for column in NUMERIC_COLUMNS:
        trades[column] = pd.to_numeric(trades[column], errors="raise")
        if trades[column].isna().any():
            raise ValueError(f"{column} contains blank values")

    trades["UniqueID"] = trades["UniqueID"].astype("string").str.strip()
    if trades["UniqueID"].isna().any() or trades["UniqueID"].eq("").any():
        raise ValueError("UniqueID contains blank values")

    trades["Pair"] = (
        trades["Underlying"]
        .astype(str)
        .str.strip()
        .str.replace(" Curncy", "", regex=False)
    )
    if trades["Pair"].eq("").any():
        raise ValueError("Underlying contains blank values")

    duplicate = trades.duplicated(["CobDate", "UniqueID"], keep=False)
    if duplicate.any():
        example = trades.loc[duplicate, ["CobDate", "UniqueID"]].iloc[0]
        raise ValueError(
            "UniqueID must occur once per CobDate; duplicate found for "
            f"{example['UniqueID']} on {example['CobDate']:%Y-%m-%d}"
        )

    pair_counts = trades.groupby("UniqueID")["Pair"].nunique()
    if pair_counts.gt(1).any():
        unique_id = pair_counts[pair_counts.gt(1)].index[0]
        raise ValueError(f"UniqueID {unique_id} appears under multiple currency pairs")

    latest_cob = trades["CobDate"].max()
    current = trades.loc[trades["CobDate"].eq(latest_cob)].copy()
    return trades, current, latest_cob


def build_ytd_pnl_streams(
    trades: pd.DataFrame,
    latest_cob: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = trades.loc[trades["CobDate"].dt.year.eq(latest_cob.year)].copy()
    history = history.sort_values(["CobDate", "UniqueID"])

    state: dict[str, tuple[str, float]] = {}
    snapshots: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for cob_date, day in history.groupby("CobDate", sort=True):
        for row in day.itertuples():
            state[str(row.UniqueID)] = (str(row.Pair), float(row.PnL))

        totals: defaultdict[str, float] = defaultdict(float)
        for pair, pnl in state.values():
            totals[pair] += pnl
        snapshots.append((pd.Timestamp(cob_date), dict(totals)))

    if not snapshots:
        raise ValueError(f"No positions found for {latest_cob.year}")

    pairs = sorted({pair for _, totals in snapshots for pair in totals})
    first_totals = snapshots[0][1]
    opening_book = sum(first_totals.values())

    book_rows = []
    pair_rows = []
    for cob_date, totals in snapshots:
        book_rows.append(
            {
                "CobDate": cob_date,
                "YtdPnL": sum(totals.values()) - opening_book,
            }
        )
        for pair in pairs:
            pair_rows.append(
                {
                    "CobDate": cob_date,
                    "Pair": pair,
                    "YtdPnL": totals.get(pair, 0.0) - first_totals.get(pair, 0.0),
                }
            )

    return pd.DataFrame(book_rows), pd.DataFrame(pair_rows)


def format_money(value: float, signed: bool = True) -> str:
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    amount = abs(value)
    if amount >= 1_000_000:
        scaled = amount / 1_000_000
        digits = 0 if scaled >= 100 else 1
        return f"{sign}${scaled:,.{digits}f}m"
    if amount >= 1_000:
        scaled = amount / 1_000
        digits = 0 if scaled >= 100 else 1
        return f"{sign}${scaled:,.{digits}f}k"
    return f"{sign}${amount:,.0f}"


def choose_date_ticks(dates: list[pd.Timestamp], maximum: int = 6) -> list[pd.Timestamp]:
    if len(dates) <= maximum:
        return dates
    indexes = {
        round(index * (len(dates) - 1) / (maximum - 1))
        for index in range(maximum)
    }
    return [dates[index] for index in sorted(indexes)]


def line_chart_svg(
    series: list[tuple[str, str, list[tuple[pd.Timestamp, float]]]],
    chart_id: str,
    aria_label: str,
) -> str:
    width, height = 980, 355
    left, right, top, bottom = 92, 26, 24, 54
    plot_width = width - left - right
    plot_height = height - top - bottom

    all_points = [point for _, _, points in series for point in points]
    dates = sorted({date for date, _ in all_points})
    values = [value for _, value in all_points] + [0.0]
    min_date, max_date = dates[0], dates[-1]
    date_span = max((max_date - min_date).total_seconds(), 1.0)

    low, high = min(values), max(values)
    if low == high:
        padding = max(abs(low) * 0.2, 1.0)
    else:
        padding = (high - low) * 0.1
    low -= padding
    high += padding

    def x_position(date: pd.Timestamp) -> float:
        if min_date == max_date:
            return left + plot_width / 2
        elapsed = (date - min_date).total_seconds()
        return left + elapsed / date_span * plot_width

    def y_position(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(aria_label)}">',
        f'<defs><clipPath id="{chart_id}-clip"><rect x="{left}" y="{top}" '
        f'width="{plot_width}" height="{plot_height}"/></clipPath></defs>',
    ]

    for index in range(5):
        value = low + (high - low) * index / 4
        y = y_position(value)
        parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" '
            'class="pnl-grid-line"/>'
        )
        parts.append(
            f'<text x="{left-12}" y="{y+4:.2f}" text-anchor="end" '
            f'class="pnl-axis-label">{html.escape(format_money(value, signed=False))}</text>'
        )

    zero_y = y_position(0)
    parts.append(
        f'<line x1="{left}" y1="{zero_y:.2f}" x2="{width-right}" '
        f'y2="{zero_y:.2f}" class="pnl-zero-line"/>'
    )

    for date in choose_date_ticks(dates):
        x = x_position(date)
        parts.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{height-bottom}" '
            'class="pnl-grid-line"/>'
        )
        parts.append(
            f'<text x="{x:.2f}" y="{height-bottom+25}" text-anchor="middle" '
            f'class="pnl-axis-label">{date:%d %b}</text>'
        )

    parts.append(f'<g clip-path="url(#{chart_id}-clip)">')
    for name, color, points in series:
        coordinates = [
            (x_position(date), y_position(value), date, value)
            for date, value in points
        ]
        path = " ".join(
            f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}"
            for index, (x, y, _, _) in enumerate(coordinates)
        )
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" '
            'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        for x, y, date, value in coordinates:
            tooltip = html.escape(
                f"{date:%Y-%m-%d} · {name} · {format_money(value)}"
            )
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="{color}" '
                f'class="pnl-point"><title>{tooltip}</title></circle>'
            )
    parts.append("</g></svg>")
    return "\n".join(parts)


def inject_ytd_pnl(
    output: Path,
    book_history: pd.DataFrame,
    pair_history: pd.DataFrame,
) -> None:
    book_points = [
        (pd.Timestamp(row.CobDate), float(row.YtdPnL))
        for row in book_history.itertuples()
    ]
    latest_book = book_points[-1][1]
    book_svg = line_chart_svg(
        [("Whole book", "#14866d", book_points)],
        "book-pnl",
        "Whole-book YTD P&L history",
    )

    latest_by_pair = (
        pair_history.sort_values("CobDate")
        .groupby("Pair", as_index=True)["YtdPnL"]
        .last()
    )
    pair_order = (
        latest_by_pair.abs().sort_values(ascending=False).index.tolist()
    )
    pair_series = []
    legend_items = []
    for index, pair in enumerate(pair_order):
        color = PAIR_COLORS[index % len(PAIR_COLORS)]
        subset = pair_history.loc[pair_history["Pair"].eq(pair)]
        points = [
            (pd.Timestamp(row.CobDate), float(row.YtdPnL))
            for row in subset.itertuples()
        ]
        pair_series.append((str(pair), color, points))
        legend_items.append(
            '<span class="pnl-legend-item">'
            f'<i style="background:{color}"></i>{html.escape(str(pair))} '
            f'<strong>{html.escape(format_money(float(latest_by_pair.loc[pair])))}</strong>'
            "</span>"
        )

    pair_svg = line_chart_svg(
        pair_series,
        "pair-pnl",
        "YTD P&L history by currency pair",
    )

    css = """
.pnl-section{margin:0 0 24px}.pnl-section-head{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin:0 0 12px}
.pnl-section-head h2{margin:0;font-size:21px}.pnl-section-head p{margin:4px 0 0;color:var(--muted);font-size:12px}
.pnl-card-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 10px 2px}
.pnl-card-head h2{margin:0}.pnl-latest{font-size:19px;font-weight:700;color:var(--pos);white-space:nowrap}
.pnl-card svg{display:block;width:100%;height:auto}.pnl-grid-line{stroke:#e7ecf2;stroke-width:1}
.pnl-zero-line{stroke:#9ba8b6;stroke-width:1.25;stroke-dasharray:5 4}.pnl-axis-label{font-size:11px;fill:#687789}
.pnl-point{stroke:#fff;stroke-width:1;cursor:crosshair}.pnl-point:hover{r:5}
.pnl-legend{display:flex;flex-wrap:wrap;gap:8px 15px;padding:0 13px 12px;color:var(--muted);font-size:11px}
.pnl-legend-item{display:inline-flex;align-items:center;gap:5px}.pnl-legend-item i{display:inline-block;width:9px;height:9px;border-radius:50%}
.pnl-legend-item strong{color:var(--ink);font-weight:600}
@media(max-width:1100px){.pnl-section-head{align-items:flex-start;flex-direction:column}}
"""
    markup = f"""
<section class="pnl-section">
  <div class="pnl-section-head">
    <div><h2>YTD P&amp;L</h2><p>Rebased to the first available CobDate · Last observed trade P&amp;L is carried forward by UniqueID after disappearance</p></div>
  </div>
  <div class="chart-grid">
    <article class="chart-card pnl-card">
      <div class="pnl-card-head"><h2>Whole book</h2><div class="pnl-latest">{html.escape(format_money(latest_book))}</div></div>
      {book_svg}
    </article>
    <article class="chart-card pnl-card">
      <div class="pnl-card-head"><h2>Individual currency pairs</h2></div>
      {pair_svg}
      <div class="pnl-legend">{''.join(legend_items)}</div>
    </article>
  </div>
</section>
"""

    document = output.read_text(encoding="utf-8")
    if "</style>" not in document:
        raise RuntimeError("Could not locate dashboard style hook")
    document = document.replace("</style>", css + "\n</style>", 1)

    chart_hook = '<section class="chart-grid"><article class="chart-card"><h2>Delta</h2>'
    if chart_hook not in document:
        raise RuntimeError("Could not locate dashboard chart hook")
    document = document.replace(chart_hook, markup + "\n" + chart_hook, 1)
    output.write_text(document, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not args.input_csv.is_file():
        raise FileNotFoundError(f"CSV file not found: {args.input_csv}")

    history, trades, as_of = load_position_history(args.input_csv)
    netted = net_trades(trades)
    if netted.empty:
        raise ValueError("The latest CobDate contains no trades to plot")

    output = args.output or args.input_csv.with_name(
        f"{args.input_csv.stem}_dashboard.html"
    )
    if output.suffix.lower() != ".html":
        raise ValueError("Output path must use the .html extension")

    book_history, pair_history = build_ytd_pnl_streams(history, as_of)
    write_html_dashboard(trades, netted, output, as_of)
    inject_ytd_pnl(output, book_history, pair_history)

    print(f"Latest CobDate: {as_of:%Y-%m-%d}")
    print(
        f"YTD P&L range: {book_history['CobDate'].min():%Y-%m-%d} "
        f"to {book_history['CobDate'].max():%Y-%m-%d}"
    )
    print(f"Dashboard HTML: {output.resolve()}")
    print(
        f"{len(trades)} latest-snapshot trades -> "
        f"{len(netted)} bubbles per Greek panel"
    )


if __name__ == "__main__":
    main()
