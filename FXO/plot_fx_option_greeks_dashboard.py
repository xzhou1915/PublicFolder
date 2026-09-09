#!/usr/bin/env python3
"""Create one FX-option dashboard with four Greek charts and raw trade details."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


GREEK_INPUT_COLUMNS = {
    "Delta": "Delta",
    "Gamma": "Gamma",
    "Theta": "ThetaPortCCY",
    "Vega": "VegaPortCCY",
}
REQUIRED_COLUMNS = {
    "Underlying",
    "OptionType",
    "ExpiryDate",
    *GREEK_INPUT_COLUMNS.values(),
}
USD_MILLION = 1_000_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot Delta, Gamma, Theta and Vega with the raw trades below."
    )
    parser.add_argument("input_csv", type=Path, help="CSV containing FX-option trades")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fx_options_greeks_dashboard.png"),
        help="Combined dashboard PNG (default: fx_options_greeks_dashboard.png)",
    )
    parser.add_argument(
        "--as-of",
        default=pd.Timestamp.today().strftime("%Y-%m-%d"),
        help="Report date in YYYY-MM-DD format (default: today)",
    )
    return parser.parse_args()


def load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(trades.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    trades = trades.copy()
    trades["ExpiryDate"] = pd.to_datetime(trades["ExpiryDate"], errors="raise")
    trades["OptionType"] = trades["OptionType"].astype(str).str.strip().str.title()
    invalid_types = sorted(set(trades["OptionType"]) - {"Call", "Put"})
    if invalid_types:
        raise ValueError(f"OptionType must be Call or Put; found: {invalid_types}")

    for column in GREEK_INPUT_COLUMNS.values():
        trades[column] = pd.to_numeric(trades[column], errors="raise")
        if trades[column].isna().any():
            raise ValueError(f"{column} contains blank values")

    trades["Pair"] = (
        trades["Underlying"].astype(str).str.strip().str.replace(" Curncy", "", regex=False)
    )
    return trades


def net_trades(trades: pd.DataFrame) -> pd.DataFrame:
    aggregation = {
        f"Net{display_name}": (input_column, "sum")
        for display_name, input_column in GREEK_INPUT_COLUMNS.items()
    }
    aggregation["Positions"] = ("Underlying", "size")
    return (
        trades.groupby(["Pair", "ExpiryDate", "OptionType"], as_index=False)
        .agg(**aggregation)
    )


def common_pair_order(netted: pd.DataFrame) -> list[str]:
    score = pd.Series(0.0, index=netted.index)
    for greek in GREEK_INPUT_COLUMNS:
        values = netted[f"Net{greek}"].abs()
        denominator = max(values.max(), 1)
        score = score + values / denominator
    return (
        netted.assign(ExposureScore=score)
        .groupby("Pair")["ExposureScore"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )


def draw_panel(
    ax: plt.Axes,
    netted: pd.DataFrame,
    greek: str,
    pair_order: list[str],
    as_of: pd.Timestamp,
    x_min: pd.Timestamp,
    x_max: pd.Timestamp,
) -> None:
    metric = f"Net{greek}"
    y_lookup = {pair: i for i, pair in enumerate(pair_order)}
    data = netted.assign(Y=netted["Pair"].map(y_lookup))
    max_abs = max(data[metric].abs().max(), 1)
    styles = {
        "Call": ("#2463eb", "C", 0.14),
        "Put": ("#8b58c7", "P", -0.14),
    }

    ax.axvline(as_of, color="#657588", linewidth=0.9, linestyle="--")
    ax.axvspan(
        as_of,
        as_of + pd.Timedelta(days=30),
        color="#f3b65c",
        alpha=0.12,
    )

    for option_type, (color, letter, offset) in styles.items():
        subset = data[data["OptionType"].eq(option_type)]
        for row in subset.itertuples():
            raw_value = getattr(row, metric)
            bubble_size = 100 + 430 * abs(raw_value) / max_abs
            displayed_value = int(round(raw_value / USD_MILLION))
            y = row.Y + offset
            ax.scatter(
                row.ExpiryDate,
                y,
                s=bubble_size,
                marker="o",
                color=color,
                alpha=0.9,
                edgecolor="white",
                linewidth=1.2,
                zorder=3,
            )
            ax.annotate(
                letter,
                (row.ExpiryDate, y),
                ha="center",
                va="center",
                fontsize=6.5,
                weight="bold",
                color="white",
                zorder=4,
            )
            count_text = f" · n={row.Positions}" if row.Positions > 1 else ""
            ax.annotate(
                f"{displayed_value:+d}m{count_text}",
                (row.ExpiryDate, y),
                xytext=(np.sqrt(bubble_size) / 2 + 8, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=6.4,
                weight="bold",
                color="#26384a",
                bbox={
                    "boxstyle": "round,pad=0.15",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.88,
                },
                arrowprops={
                    "arrowstyle": "-",
                    "color": color,
                    "linewidth": 0.65,
                    "shrinkA": 1,
                    "shrinkB": 4,
                },
                zorder=5,
            )

    totals = data.groupby("Pair")[metric].sum().reindex(pair_order) / USD_MILLION
    for y, total in enumerate(totals):
        rounded_total = int(round(total))
        ax.text(
            1.008,
            y,
            f"Σ {rounded_total:+d}m",
            transform=ax.get_yaxis_transform(),
            ha="left",
            va="center",
            fontsize=6.7,
            weight="bold",
            color="#14866d" if total >= 0 else "#d84b5b",
            clip_on=False,
        )

    ax.set_title(greek, loc="left", fontsize=13, weight="bold", pad=9)
    ax.set_xlim(x_min, x_max)
    ax.set_yticks(range(len(pair_order)), pair_order)
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.grid(axis="x", alpha=0.15)
    ax.grid(axis="y", alpha=0.09)
    ax.tick_params(axis="y", labelsize=7.5, length=0, pad=5)
    ax.tick_params(axis="x", labelsize=7, length=0, pad=5)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)


def format_trade_table(trades: pd.DataFrame) -> tuple[list[str], list[list[str]]]:
    preferred = [
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
    ]
    columns = [column for column in preferred if column in trades.columns]
    display_names = {
        "ThetaPortCCY": "Theta",
        "VegaPortCCY": "Vega",
    }
    headers = [display_names.get(column, column) for column in columns]
    rows: list[list[str]] = []
    for _, trade in trades[columns].iterrows():
        row: list[str] = []
        for column in columns:
            value = trade[column]
            if column == "ExpiryDate":
                row.append(pd.Timestamp(value).strftime("%Y-%m-%d"))
            elif column in GREEK_INPUT_COLUMNS.values() or column in {"Notional", "PnL"}:
                row.append(f"{float(value):,.0f}")
            elif column == "Strike":
                row.append(f"{float(value):,.4f}".rstrip("0").rstrip("."))
            else:
                row.append(str(value))
        rows.append(row)
    return headers, rows


def draw_dashboard(
    trades: pd.DataFrame,
    netted: pd.DataFrame,
    output: Path,
    as_of: pd.Timestamp,
) -> None:
    pair_order = common_pair_order(netted)
    x_min = min(as_of, netted["ExpiryDate"].min()) - pd.Timedelta(days=12)
    x_max = max(as_of + pd.Timedelta(days=30), netted["ExpiryDate"].max()) + pd.Timedelta(days=50)
    table_height = max(3.8, min(20, 0.32 * len(trades) + 1.4))
    figure_height = 11.2 + table_height

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "figure.facecolor": "#f4f7fb",
            "axes.facecolor": "white",
            "text.color": "#172433",
            "xtick.color": "#526273",
            "ytick.color": "#526273",
        }
    )
    fig = plt.figure(figsize=(22, figure_height))
    grid = fig.add_gridspec(
        3,
        2,
        height_ratios=[5, 5, table_height],
        hspace=0.34,
        wspace=0.22,
    )
    axes = [
        fig.add_subplot(grid[0, 0]),
        fig.add_subplot(grid[0, 1]),
        fig.add_subplot(grid[1, 0]),
        fig.add_subplot(grid[1, 1]),
    ]
    for ax, greek in zip(axes, GREEK_INPUT_COLUMNS):
        draw_panel(ax, netted, greek, pair_order, as_of, x_min, x_max)

    table_ax = fig.add_subplot(grid[2, :])
    table_ax.axis("off")
    table_ax.set_title(
        f"Original trades — {len(trades)} rows (unnetted, raw input amounts)",
        loc="left",
        fontsize=12,
        weight="bold",
        pad=10,
    )
    headers, rows = format_trade_table(trades)
    column_widths = {
        "Underlying": 0.105,
        "Shore": 0.075,
        "OptionType": 0.065,
        "Strike": 0.06,
        "ExpiryDate": 0.085,
        "Delta": 0.09,
        "Gamma": 0.09,
        "Theta": 0.09,
        "Vega": 0.09,
        "Notional": 0.105,
        "NotionalCCY": 0.075,
        "PnL": 0.085,
    }
    widths = [column_widths.get(header, 1 / len(headers)) for header in headers]
    width_total = sum(widths)
    widths = [width / width_total for width in widths]
    table = table_ax.table(
        cellText=rows,
        colLabels=headers,
        cellLoc="left",
        colLoc="left",
        colWidths=widths,
        bbox=[0, 0, 1, 0.96],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(max(5.2, 7.2 - max(0, len(trades) - 20) * 0.035))
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#e1e7ee")
        cell.set_linewidth(0.45)
        if row == 0:
            cell.set_facecolor("#173151")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("white" if row % 2 else "#f7f9fc")

    fig.suptitle(
        "FX Options — Netted Greeks by Expiry and Type",
        x=0.045,
        y=0.992,
        ha="left",
        fontsize=23,
        weight="bold",
    )
    fig.text(
        0.045,
        0.974,
        "Bubble label = net Greek in whole USD m  •  Bubble size = absolute net Greek  •  "
        "Σ = total by currency pair  •  Yellow band = expires within 30 calendar days",
        fontsize=9.5,
        color="#687789",
    )
    legend = [
        Line2D([0], [0], marker="o", color="white", label="Call (C)", markerfacecolor="#2463eb", markersize=9),
        Line2D([0], [0], marker="o", color="white", label="Put (P)", markerfacecolor="#8b58c7", markersize=9),
        Line2D([0], [0], color="#657588", linestyle="--", label=f"As of {as_of:%d %b %Y}"),
    ]
    fig.legend(
        handles=legend,
        frameon=False,
        ncol=3,
        loc="upper right",
        bbox_to_anchor=(0.96, 0.989),
    )
    fig.subplots_adjust(top=0.94, bottom=0.025, left=0.055, right=0.945)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    as_of = pd.to_datetime(args.as_of, format="%Y-%m-%d", errors="raise")
    trades = load_trades(args.input_csv)
    netted = net_trades(trades)
    if netted.empty:
        raise ValueError("The input contains no trades to plot")

    draw_dashboard(trades, netted, args.output, as_of)
    netted_output = args.output.with_name(f"{args.output.stem}_netted.csv")
    netted.to_csv(netted_output, index=False, date_format="%Y-%m-%d")
    print(f"Dashboard: {args.output.resolve()}")
    print(f"Netted data: {netted_output.resolve()}")
    print(f"{len(trades)} original trades -> {len(netted)} bubbles per Greek panel")


if __name__ == "__main__":
    main()
