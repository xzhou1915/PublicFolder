#!/usr/bin/env python3
"""Create one FX-option dashboard with four Greek charts and raw trade details."""

from __future__ import annotations

import argparse
import html
import math
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
        "--html-output",
        type=Path,
        default=None,
        help="Standalone HTML path (default: same name as --output with .html)",
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
    return (
        netted.groupby("Pair")["NetDelta"]
        .sum()
        .sort_values(ascending=True)
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
                fontsize=8.5,
                weight="bold",
                color="white",
                zorder=4,
            )
            count_text = f"\n{row.Positions} trades netted" if row.Positions > 1 else ""
            ax.annotate(
                f"{displayed_value:+d}m{count_text}",
                (row.ExpiryDate, y),
                xytext=(np.sqrt(bubble_size) / 2 + 8, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=9.2,
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
            fontsize=20.1,
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
        wspace=0.40,
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
        "Σ = total by currency pair  •  Yellow band = expires within 30 calendar days  •  "
        "Pairs ordered by total net Delta, smallest to largest",
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
    fig.subplots_adjust(top=0.94, bottom=0.025, left=0.055, right=0.90)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170, bbox_inches="tight")
    plt.close(fig)



def svg_panel_markup(
    netted: pd.DataFrame,
    greek: str,
    pair_order: list[str],
    as_of: pd.Timestamp,
) -> str:
    metric = f"Net{greek}"
    width, step = 980, 66
    left, right, top, bottom = 100, 220, 25, 48
    height = top + len(pair_order) * step + bottom
    x_min = min(as_of, netted["ExpiryDate"].min()) - pd.Timedelta(days=12)
    x_max = max(as_of + pd.Timedelta(days=30), netted["ExpiryDate"].max()) + pd.Timedelta(days=50)
    span_seconds = max((x_max - x_min).total_seconds(), 1)

    def x_position(value: pd.Timestamp) -> float:
        return left + (value - x_min).total_seconds() / span_seconds * (width - left - right)

    def y_position(pair: str) -> float:
        return top + pair_order.index(pair) * step + step / 2

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{greek} by currency pair and expiry">'
    ]
    band_x = x_position(as_of)
    band_width = x_position(as_of + pd.Timedelta(days=30)) - band_x
    parts.append(
        f'<rect x="{band_x:.2f}" y="{top}" width="{band_width:.2f}" '
        f'height="{height-top-bottom}" fill="#f3b65c" fill-opacity=".18"/>'
    )

    tick = pd.Timestamp(x_min.year, x_min.month, 1)
    tick_index = 0
    while tick <= x_max:
        if tick_index % 2 == 0:
            tick_x = x_position(tick)
            parts.append(
                f'<line x1="{tick_x:.2f}" y1="{top}" x2="{tick_x:.2f}" '
                f'y2="{height-bottom}" class="grid-line"/>'
            )
            parts.append(
                f'<text x="{tick_x:.2f}" y="{height-18}" text-anchor="middle" '
                f'class="axis-label">{tick:%b %y}</text>'
            )
        tick = tick + pd.DateOffset(months=1)
        tick_index += 1

    totals = netted.groupby("Pair")[metric].sum().reindex(pair_order)
    for pair in pair_order:
        pair_y = y_position(pair)
        total = float(totals.loc[pair])
        total_m = int(round(total / USD_MILLION))
        total_text = f"{total_m:+d}m"
        total_color = "#14866d" if total >= 0 else "#d84b5b"
        parts.append(
            f'<line x1="{left}" y1="{pair_y:.2f}" x2="{width-right}" '
            f'y2="{pair_y:.2f}" class="grid-line"/>'
        )
        parts.append(
            f'<text x="{left-9}" y="{pair_y+4:.2f}" text-anchor="end" '
            f'class="pair-label">{html.escape(pair)}</text>'
        )
        parts.append(
            f'<text x="{width-right+8}" y="{pair_y+4:.2f}" class="total-label" '
            f'font-size="36" font-weight="700" fill="{total_color}">Σ {total_text}</text>'
        )

    asof_x = x_position(as_of)
    parts.append(
        f'<line x1="{asof_x:.2f}" y1="{top}" x2="{asof_x:.2f}" '
        f'y2="{height-bottom}" class="asof-line"/>'
    )
    max_abs = max(float(netted[metric].abs().max()), 1)
    for row in netted.itertuples():
        raw_value = float(getattr(row, metric))
        point_x = x_position(pd.Timestamp(row.ExpiryDate))
        point_y = y_position(row.Pair) + (-8 if row.OptionType == "Call" else 8)
        radius = 7 + 17 * math.sqrt(abs(raw_value) / max_abs)
        color = "#2463eb" if row.OptionType == "Call" else "#8b58c7"
        letter = "C" if row.OptionType == "Call" else "P"
        value_m = int(round(raw_value / USD_MILLION))
        label = f"{value_m:+d}m"
        if row.Positions > 1:
            label += f" · {row.Positions} trades"
        tooltip = html.escape(
            f"{row.Pair} · {row.OptionType} · {row.ExpiryDate:%Y-%m-%d}\n"
            f"Net {greek}: {raw_value:,.0f} USD\nPositions netted: {row.Positions}"
        )
        parts.append(
            f'<line x1="{point_x+radius:.2f}" y1="{point_y:.2f}" '
            f'x2="{point_x+radius+7:.2f}" y2="{point_y:.2f}" '
            f'class="leader" stroke="{color}"/>'
        )
        parts.append(
            f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="{radius:.2f}" '
            f'fill="{color}" stroke="#fff" stroke-width="1.5"><title>{tooltip}</title></circle>'
        )
        parts.append(
            f'<text x="{point_x:.2f}" y="{point_y+3:.2f}" text-anchor="middle" '
            f'fill="#fff" font-size="11" font-weight="700">{letter}</text>'
        )
        parts.append(
            f'<text x="{point_x+radius+10:.2f}" y="{point_y+4:.2f}" '
            f'class="value-label">{html.escape(label)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def write_html_dashboard(
    trades: pd.DataFrame,
    netted: pd.DataFrame,
    output: Path,
    as_of: pd.Timestamp,
) -> None:
    pair_order = common_pair_order(netted)
    chart_svgs = {
        greek: svg_panel_markup(netted, greek, pair_order, as_of)
        for greek in GREEK_INPUT_COLUMNS
    }
    headers, rows = format_trade_table(trades)
    header_html = "".join(
        f'<th onclick="sortTable({index})">{html.escape(header)} <span>↕</span></th>'
        for index, header in enumerate(headers)
    )
    row_html = []
    for row in rows:
        cells = "".join(
            f'<td data-value="{html.escape(value.replace(",", ""))}">{html.escape(value)}</td>'
            for value in row
        )
        row_html.append(f"<tr>{cells}</tr>")

    template = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FX Options Greeks Dashboard</title>
<style>
:root{--ink:#172433;--muted:#687789;--line:#dfe6ee;--navy:#173151;--bg:#f4f7fb;--call:#2463eb;--put:#8b58c7;--pos:#14866d;--neg:#d84b5b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif}
main{max-width:1900px;margin:0 auto;padding:28px}header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:17px}
h1{margin:0 0 7px;font-size:28px}.subtitle,.asof{color:var(--muted);font-size:13px}.asof{white-space:nowrap}
.legend{display:flex;gap:17px;align-items:center;margin:0 0 15px;font-size:12px;color:var(--muted)}.key{display:flex;align-items:center;gap:6px}.dot{width:14px;height:14px;border-radius:50%;display:inline-grid;place-items:center;color:#fff;font-size:8px;font-weight:bold}.band{width:22px;height:12px;background:rgba(243,182,92,.28);border:1px solid rgba(167,102,20,.25)}
.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.chart-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 12px 8px;box-shadow:0 4px 14px rgba(23,49,81,.05);overflow:visible}
.chart-card h2{margin:0 0 4px 10px;font-size:18px}.chart-card svg{display:block;width:100%;height:auto;overflow:visible}.trades{margin-top:24px;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(23,49,81,.05)}
.toolbar{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:16px 18px;border-bottom:1px solid var(--line)}.toolbar h2{margin:0;font-size:18px}input{min-width:300px;padding:9px 12px;border:1px solid #bdc9d6;border-radius:7px;font-size:13px}
.table-wrap{overflow:auto;max-height:620px}table{width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap}th{position:sticky;top:0;z-index:1;padding:10px;background:var(--navy);color:#fff;text-align:left;cursor:pointer;user-select:none}th span{opacity:.55;font-size:10px}
td{padding:9px 10px;border-bottom:1px solid #e8edf2}tbody tr:nth-child(even){background:#f7f9fc}tbody tr:hover{background:#edf4ff}.footer{padding:12px 18px;color:var(--muted);font-size:12px;border-top:1px solid var(--line)}
.axis-label{font-size:10px;fill:#526273}.pair-label{font-size:12px;fill:#26384a;font-weight:600}.value-label{font-size:13px;fill:#26384a;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:6px;stroke-linejoin:round}.total-label{font-size:36px;font-weight:700}.grid-line{stroke:#e4eaf0;stroke-width:1}.asof-line{stroke:#657588;stroke-width:1.2;stroke-dasharray:5 4}.leader{stroke-width:1;opacity:.75}
@media(max-width:1100px){.chart-grid{grid-template-columns:1fr}header,.toolbar{align-items:flex-start;flex-direction:column}input{min-width:100%;width:100%}}
@media print{body{background:#fff}main{max-width:none;padding:0}.chart-card,.trades{box-shadow:none}.table-wrap{max-height:none;overflow:visible}input{display:none}}
</style>
</head>
<body><main>
<header><div><h1>FX Options — Netted Greeks by Expiry and Type</h1><div class="subtitle">Native SVG charts · Whole USD millions · Pair order follows total net Delta from smallest to largest · Hover for exact values</div></div><div class="asof">As of __AS_OF_LABEL__</div></header>
<div class="legend"><span class="key"><span class="dot" style="background:var(--call)">C</span>Call</span><span class="key"><span class="dot" style="background:var(--put)">P</span>Put</span><span class="key"><span class="band"></span>Expires within 30 calendar days</span><span>Σ = total by currency pair</span></div>
<section class="chart-grid"><article class="chart-card"><h2>Delta</h2>__DELTA_SVG__</article><article class="chart-card"><h2>Gamma</h2>__GAMMA_SVG__</article><article class="chart-card"><h2>Theta</h2>__THETA_SVG__</article><article class="chart-card"><h2>Vega</h2>__VEGA_SVG__</article></section>
<section class="trades"><div class="toolbar"><h2>Original trades — __COUNT__ rows</h2><input id="search" type="search" placeholder="Filter trades…" oninput="filterTrades()"></div><div class="table-wrap"><table id="tradeTable"><thead><tr>__HEADERS__</tr></thead><tbody>__ROWS__</tbody></table></div><div class="footer">Unnetted trades and raw input amounts. ThetaPortCCY and VegaPortCCY are displayed as Theta and Vega. Click a heading to sort.</div></section>
</main>
<script>

let direction=1;
function filterTrades(){const q=document.getElementById('search').value.toLowerCase();document.querySelectorAll('#tradeTable tbody tr').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(q)?'':'none')}
function sortTable(c){const b=document.querySelector('#tradeTable tbody'),r=Array.from(b.rows);direction*=-1;r.sort((x,y)=>{const a=x.cells[c].dataset.value,d=y.cells[c].dataset.value,an=Number(a),dn=Number(d);return(a!==''&&d!==''&&Number.isFinite(an)&&Number.isFinite(dn)?an-dn:a.localeCompare(d))*direction});r.forEach(x=>b.appendChild(x))}
</script></body></html>
'''
    document = (
        template.replace("__AS_OF_LABEL__", as_of.strftime("%d %b %Y"))
        .replace("__COUNT__", str(len(trades)))
        .replace("__HEADERS__", header_html)
        .replace("__ROWS__", "\n".join(row_html))
        .replace("__DELTA_SVG__", chart_svgs["Delta"])
        .replace("__GAMMA_SVG__", chart_svgs["Gamma"])
        .replace("__THETA_SVG__", chart_svgs["Theta"])
        .replace("__VEGA_SVG__", chart_svgs["Vega"])
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")

def main() -> None:
    args = parse_args()
    as_of = pd.to_datetime(args.as_of, format="%Y-%m-%d", errors="raise")
    trades = load_trades(args.input_csv)
    netted = net_trades(trades)
    if netted.empty:
        raise ValueError("The input contains no trades to plot")

    draw_dashboard(trades, netted, args.output, as_of)
    html_output = args.html_output or args.output.with_suffix(".html")
    write_html_dashboard(trades, netted, html_output, as_of)
    netted_output = args.output.with_name(f"{args.output.stem}_netted.csv")
    netted.to_csv(netted_output, index=False, date_format="%Y-%m-%d")
    print(f"Dashboard image: {args.output.resolve()}")
    print(f"Dashboard HTML: {html_output.resolve()}")
    print(f"Netted data: {netted_output.resolve()}")
    print(f"{len(trades)} original trades -> {len(netted)} bubbles per Greek panel")


if __name__ == "__main__":
    main()
