#!/usr/bin/env python3
"""Create a netted FX-option Delta-by-expiry bubble chart from a CSV file."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


REQUIRED_COLUMNS = {"Underlying", "OptionType", "ExpiryDate", "Delta"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot netted FX-option Delta by currency pair, expiry, and call/put."
    )
    parser.add_argument("input_csv", type=Path, help="CSV containing FX-option positions")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("netted_delta_expiry_map.png"),
        help="Output PNG path (default: netted_delta_expiry_map.png)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=pd.Timestamp.today().strftime("%Y-%m-%d"),
        help="Report date in YYYY-MM-DD format (default: today)",
    )
    return parser.parse_args()


def load_positions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    df = df.copy()
    df["ExpiryDate"] = pd.to_datetime(df["ExpiryDate"], errors="raise")
    df["Delta"] = pd.to_numeric(df["Delta"], errors="raise")
    df["OptionType"] = df["OptionType"].str.strip().str.title()
    invalid_types = sorted(set(df["OptionType"]) - {"Call", "Put"})
    if invalid_types:
        raise ValueError(f"OptionType must be Call or Put; found: {invalid_types}")

    df["Pair"] = (
        df["Underlying"].astype(str).str.strip().str.replace(" Curncy", "", regex=False)
    )
    return df


def net_positions(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["Pair", "ExpiryDate", "OptionType"], as_index=False)
        .agg(NetDelta=("Delta", "sum"), Positions=("Delta", "size"))
    )


def draw_chart(net: pd.DataFrame, output: Path, as_of: pd.Timestamp) -> None:
    if net.empty:
        raise ValueError("The input contains no positions to plot")

    pair_order = (
        net.assign(AbsDelta=net["NetDelta"].abs())
        .groupby("Pair")["AbsDelta"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )
    y_lookup = {pair: i for i, pair in enumerate(pair_order)}
    net = net.assign(Y=net["Pair"].map(y_lookup))
    totals = net.groupby("Pair")["NetDelta"].sum().reindex(pair_order) / 1_000_000

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
    fig = plt.figure(figsize=(16, 8.5))
    grid = fig.add_gridspec(1, 5, width_ratios=[1, 1, 1, 1, 1.05], wspace=0.08)
    timeline = fig.add_subplot(grid[0, :4])
    total_ax = fig.add_subplot(grid[0, 4], sharey=timeline)

    max_abs_delta = max(net["NetDelta"].abs().max(), 1)
    styles = {
        "Call": ("#2463eb", "C", 0.14),
        "Put": ("#8b58c7", "P", -0.14),
    }
    for option_type, (color, letter, offset) in styles.items():
        positions = net[net["OptionType"].eq(option_type)]
        for row in positions.itertuples():
            bubble_size = 250 + 900 * abs(row.NetDelta) / max_abs_delta
            delta_millions = int(round(row.NetDelta / 1_000_000))
            y = row.Y + offset
            timeline.scatter(
                row.ExpiryDate, y, s=bubble_size, marker="o", color=color,
                alpha=0.9, edgecolor="white", linewidth=1.6, zorder=3,
            )
            timeline.annotate(
                letter, (row.ExpiryDate, y), ha="center", va="center",
                fontsize=8.2, weight="bold", color="white", zorder=4,
            )
            timeline.annotate(
                f"{delta_millions:+d}m"
                + (f"\n{row.Positions} netted" if row.Positions > 1 else ""),
                (row.ExpiryDate, y),
                xytext=(np.sqrt(bubble_size) / 2 + 12, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=8.2,
                weight="bold",
                color="#26384a",
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
                arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.8, "shrinkA": 1, "shrinkB": 6},
                zorder=5,
            )

    timeline.axvline(as_of, color="#657588", linewidth=1.1, linestyle="--")
    timeline.axvspan(as_of, as_of + pd.Timedelta(days=30), color="#f3b65c", alpha=0.12)
    timeline.text(
        as_of + pd.Timedelta(days=15),
        1.012,
        "EXPIRES WITHIN 30 DAYS",
        transform=timeline.get_xaxis_transform(),
        ha="center",
        va="bottom",
        fontsize=7.5,
        weight="bold",
        color="#a76614",
    )
    timeline.set_yticks(range(len(pair_order)), pair_order)
    timeline.invert_yaxis()
    timeline.set_xlim(
        min(as_of, net["ExpiryDate"].min()) - pd.Timedelta(days=12),
        net["ExpiryDate"].max() + pd.Timedelta(days=28),
    )
    timeline.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    timeline.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    timeline.grid(axis="x", alpha=0.16)
    timeline.grid(axis="y", alpha=0.10)
    timeline.tick_params(axis="y", labelsize=10, length=0, pad=8)
    timeline.tick_params(axis="x", length=0, pad=8)
    timeline.spines[["top", "right", "left", "bottom"]].set_visible(False)
    timeline.set_title("Expiry timeline", loc="left", fontsize=12, weight="bold", pad=14)

    total_colors = np.where(totals >= 0, "#14866d", "#d84b5b")
    total_ax.barh(range(len(pair_order)), totals, color=total_colors, height=0.46)
    total_ax.axvline(0, color="#778594", linewidth=0.8)
    bound = max(abs(totals.min()), abs(totals.max()), 1) * 1.48
    total_ax.set_xlim(-bound, bound)
    total_ax.set_yticks(range(len(pair_order)))
    total_ax.tick_params(axis="y", left=False, labelleft=False)
    total_ax.tick_params(axis="x", length=0, pad=8)
    total_ax.grid(axis="x", alpha=0.14)
    total_ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    total_ax.set_title("Total net Delta", loc="left", fontsize=12, weight="bold", pad=14)
    total_ax.set_xlabel("USD m", fontsize=8.5, color="#687789")
    for i, value in enumerate(totals):
        rounded_value = int(round(value))
        total_ax.text(
            value + (bound * 0.025 if value >= 0 else -bound * 0.025), i,
            f"{rounded_value:+d}m", ha="left" if value >= 0 else "right",
            va="center", fontsize=8.5, weight="bold",
        )

    fig.suptitle(
        "FX Options — Netted Delta by Expiry and Type", x=0.055, y=0.985,
        ha="left", fontsize=21, weight="bold",
    )
    fig.text(
        0.055, 0.943,
        "Each bubble nets positions with the same pair, expiry and type  •  "
        "Label = net Delta in USD m, rounded to an integer  •  Size = |net Delta|",
        fontsize=9.5, color="#687789",
    )
    legend = [
        Line2D([0], [0], marker="o", color="white", label="Call (C)", markerfacecolor="#2463eb", markersize=10),
        Line2D([0], [0], marker="o", color="white", label="Put (P)", markerfacecolor="#8b58c7", markersize=10),
        Line2D([0], [0], color="#14866d", linewidth=7, label="Positive total Delta"),
        Line2D([0], [0], color="#d84b5b", linewidth=7, label="Negative total Delta"),
    ]
    fig.legend(handles=legend, frameon=False, ncol=4, loc="upper right", bbox_to_anchor=(0.97, 0.975))
    fig.text(
        0.055, 0.018,
        f"As of {as_of:%d %b %Y}. Input Delta is assumed to be an unscaled USD amount; "
        "cross-pair totals are intentionally omitted.",
        fontsize=8.3, color="#718094",
    )
    fig.subplots_adjust(top=0.88, bottom=0.11, left=0.08, right=0.97)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    as_of = pd.to_datetime(args.as_of, format="%Y-%m-%d", errors="raise")
    positions = load_positions(args.input_csv)
    netted = net_positions(positions)
    draw_chart(netted, args.output, as_of)

    netted_path = args.output.with_name(f"{args.output.stem}_netted.csv")
    netted.to_csv(netted_path, index=False, date_format="%Y-%m-%d")
    print(f"Chart: {args.output.resolve()}")
    print(f"Netted data: {netted_path.resolve()}")
    print(f"{len(positions)} input positions -> {len(netted)} plotted bubbles")


if __name__ == "__main__":
    main()
