#!/usr/bin/env python3
"""Generate an HTML FXO dashboard from the 18-column headerless position file."""

from __future__ import annotations

import argparse
import html
import itertools
import json
from collections import defaultdict
from functools import lru_cache
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
    trades["Notional"] = pd.to_numeric(trades["Notional"], errors="raise")

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


def build_wow_summary(
    book_history: pd.DataFrame,
    pair_history: pd.DataFrame,
) -> tuple[pd.Timestamp | None, float, float | None, list[tuple[str, float, float]]]:
    latest_date = pd.Timestamp(book_history["CobDate"].max())
    current_pnl = float(
        book_history.loc[book_history["CobDate"].eq(latest_date), "YtdPnL"].iloc[0]
    )
    comparison_dates = book_history.loc[
        book_history["CobDate"].le(latest_date - pd.Timedelta(days=7)), "CobDate"
    ]
    if comparison_dates.empty:
        return None, current_pnl, None, []

    comparison_date = pd.Timestamp(comparison_dates.max())
    previous_pnl = float(
        book_history.loc[
            book_history["CobDate"].eq(comparison_date), "YtdPnL"
        ].iloc[0]
    )
    wow_change = current_pnl - previous_pnl

    latest_pairs = pair_history.loc[
        pair_history["CobDate"].eq(latest_date)
    ].set_index("Pair")["YtdPnL"]
    previous_pairs = pair_history.loc[
        pair_history["CobDate"].eq(comparison_date)
    ].set_index("Pair")["YtdPnL"]

    contributors = []
    for pair in latest_pairs.index:
        current = float(latest_pairs.loc[pair])
        change = current - float(previous_pairs.loc[pair])
        if change != 0:
            contributors.append((str(pair), current, change))
    contributors.sort(key=lambda item: abs(item[2]), reverse=True)

    contribution_total = sum(item[2] for item in contributors)
    tolerance = max(1e-6, abs(wow_change) * 1e-12)
    if abs(contribution_total - wow_change) > tolerance:
        raise RuntimeError("Currency WoW contributions do not match whole-book WoW")

    return comparison_date, current_pnl, wow_change, contributors


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


def infer_leg_side(row: pd.Series) -> tuple[int, str]:
    """Infer long/short from signed risks without using PositionName."""
    gamma = float(row["Gamma"])
    vega = float(row["VegaPortCCY"])
    delta = float(row["Delta"])
    option_type = str(row["OptionType"])

    if gamma != 0:
        side = 1 if gamma > 0 else -1
        source = "Gamma"
    elif vega != 0:
        side = 1 if vega > 0 else -1
        source = "Vega"
    elif delta != 0:
        side = (1 if delta > 0 else -1) * (1 if option_type == "Call" else -1)
        source = "Delta"
    else:
        return 1, "Low"

    expected_delta = side if option_type == "Call" else -side
    delta_consistent = delta == 0 or (1 if delta > 0 else -1) == expected_delta
    vega_consistent = vega == 0 or (1 if vega > 0 else -1) == side
    confidence = (
        "High"
        if source == "Gamma" and delta_consistent and vega_consistent
        else "Medium"
    )
    return side, confidence


def notional_ratio_label(legs: list[dict]) -> str:
    ordered = sorted(legs, key=lambda leg: (leg["strike"], leg["optionType"]))
    notionals = [leg["notional"] for leg in ordered]
    if any(value is None or value <= 0 for value in notionals):
        return "—"
    minimum = min(notionals)
    ratios = [value / minimum for value in notionals]

    def format_ratio(value: float) -> str:
        rounded = round(value)
        if abs(value - rounded) <= 0.05:
            return str(int(rounded))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    return " : ".join(format_ratio(value) for value in ratios)


def notionals_are_equal(legs: list[dict]) -> bool | None:
    values = [leg["notional"] for leg in legs]
    if any(value is None or value <= 0 for value in values):
        return None
    return max(values) / min(values) <= 1.10


def candidate_confidence(legs: list[dict]) -> str:
    sides_are_clear = all(leg["sideConfidence"] == "High" for leg in legs)
    ratios_are_clear = all(
        leg["notional"] is not None and leg["notional"] > 0 for leg in legs
    )
    if sides_are_clear and ratios_are_clear:
        return "High"
    return "Medium"


def classify_leg_combination(indices: tuple[int, ...], legs: list[dict]) -> dict | None:
    selected = [legs[index] for index in indices]
    ordered = sorted(selected, key=lambda leg: leg["strike"])
    option_types = [leg["optionType"] for leg in ordered]
    sides = [leg["side"] for leg in ordered]

    if len(selected) == 2:
        first, second = ordered
        if first["strike"] == second["strike"]:
            return None
        if first["optionType"] == second["optionType"] and first["side"] != second["side"]:
            equal = notionals_are_equal(selected)
            ratio = equal is False
            option_type = first["optionType"]
            if option_type == "Call":
                direction = "Long" if first["side"] == 1 else "Short"
            else:
                direction = "Long" if second["side"] == 1 else "Short"
            kind = f"{'Ratio ' if ratio else ''}{option_type} Spread"
            return {
                "indices": indices,
                "type": kind,
                "direction": direction,
                "score": 44 if not ratio else 42,
                "confidence": candidate_confidence(selected),
            }

        if set(option_types) == {"Call", "Put"} and first["side"] != second["side"]:
            call = next(leg for leg in selected if leg["optionType"] == "Call")
            put = next(leg for leg in selected if leg["optionType"] == "Put")
            direction = "Long" if call["side"] == 1 and put["side"] == -1 else "Short"
            return {
                "indices": indices,
                "type": "Risk Reversal",
                "direction": direction,
                "score": 43,
                "confidence": candidate_confidence(selected),
            }
        return None

    if len(selected) == 3:
        if len(set(leg["strike"] for leg in selected)) < 2:
            return None
        if len(set(option_types)) == 1:
            option_type = option_types[0]
            equal = notionals_are_equal(selected)
            if sides in ([1, -1, 1], [-1, 1, -1]):
                values = [leg["notional"] for leg in ordered]
                butterfly_ratio = (
                    all(value is not None and value > 0 for value in values)
                    and abs(values[0] - values[2]) / min(values[0], values[2]) <= 0.10
                    and abs(values[1] / values[0] - 2) <= 0.20
                )
                if butterfly_ratio:
                    return {
                        "indices": indices,
                        "type": f"{option_type} Butterfly",
                        "direction": "Long" if sides[0] == 1 else "Short",
                        "score": 64,
                        "confidence": candidate_confidence(selected),
                    }
            if sides.count(1) in {1, 2} and sides[0] != sides[-1]:
                if option_type == "Call":
                    direction = "Long" if ordered[0]["side"] == 1 else "Short"
                else:
                    direction = "Long" if ordered[-1]["side"] == 1 else "Short"
                return {
                    "indices": indices,
                    "type": f"{option_type} Ladder",
                    "direction": direction,
                    "score": 60 if equal is not None else 57,
                    "confidence": candidate_confidence(selected),
                }
            return None

        counts = {kind: option_types.count(kind) for kind in set(option_types)}
        if sorted(counts.values()) == [1, 2]:
            repeated_type = next(kind for kind, count in counts.items() if count == 2)
            repeated = [leg for leg in selected if leg["optionType"] == repeated_type]
            if repeated[0]["side"] != repeated[1]["side"]:
                singleton = next(
                    leg for leg in selected if leg["optionType"] != repeated_type
                )
                if singleton["optionType"] == "Call":
                    direction = "Long" if singleton["side"] == 1 else "Short"
                else:
                    direction = "Long" if singleton["side"] == -1 else "Short"
                return {
                    "indices": indices,
                    "type": "Seagull",
                    "direction": direction,
                    "score": 62,
                    "confidence": candidate_confidence(selected),
                }

    if len(selected) == 4:
        calls = sorted(
            (leg for leg in selected if leg["optionType"] == "Call"),
            key=lambda leg: leg["strike"],
        )
        puts = sorted(
            (leg for leg in selected if leg["optionType"] == "Put"),
            key=lambda leg: leg["strike"],
        )
        if (
            len(calls) == 2
            and len(puts) == 2
            and calls[0]["strike"] != calls[1]["strike"]
            and puts[0]["strike"] != puts[1]["strike"]
            and calls[0]["side"] != calls[1]["side"]
            and puts[0]["side"] != puts[1]["side"]
        ):
            call_direction = "Long" if calls[0]["side"] == 1 else "Short"
            put_direction = "Long" if puts[1]["side"] == 1 else "Short"
            if call_direction != put_direction:
                return {
                    "indices": indices,
                    "type": "Risk Reversal",
                    "direction": call_direction,
                    "score": 96,
                    "confidence": candidate_confidence(selected),
                }
    return None


def build_structure_candidates(legs: list[dict]) -> list[dict]:
    candidates = []
    for size in (2, 3, 4):
        for indices in itertools.combinations(range(len(legs)), size):
            candidate = classify_leg_combination(indices, legs)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def best_bucket_partition(legs: list[dict]) -> tuple[list[dict | None], bool]:
    if len(legs) > 14:
        return [None for _ in legs], True

    candidates = build_structure_candidates(legs)

    @lru_cache(maxsize=None)
    def solve(mask: int) -> tuple[int, tuple[tuple[tuple[int, tuple[int, ...]], ...], ...]]:
        if mask == 0:
            return 0, ((),)
        first = next(index for index in range(len(legs)) if mask & (1 << index))
        remainder_score, remainder_solutions = solve(mask & ~(1 << first))
        options = [
            (
                remainder_score,
                ((-1, (first,)),) + solution,
            )
            for solution in remainder_solutions
        ]
        for candidate_index, candidate in enumerate(candidates):
            indices = candidate["indices"]
            candidate_mask = sum(1 << index for index in indices)
            if first not in indices or mask & candidate_mask != candidate_mask:
                continue
            score, solutions = solve(mask & ~candidate_mask)
            options.extend(
                (
                    score + int(candidate["score"]),
                    ((candidate_index, indices),) + solution,
                )
                for solution in solutions
            )
        best_score = max(score for score, _ in options)
        unique = []
        seen = set()
        for score, solution in options:
            if score != best_score or solution in seen:
                continue
            seen.add(solution)
            unique.append(solution)
            if len(unique) == 2:
                break
        return best_score, tuple(unique)

    best_score, solutions = solve((1 << len(legs)) - 1)
    if len(solutions) != 1:
        return [None for _ in legs], True
    if best_score == 0 and len(legs) > 1:
        return [None for _ in legs], True

    result = []
    for candidate_index, indices in solutions[0]:
        if candidate_index == -1:
            result.append(
                {
                    "indices": indices,
                    "type": f"Vanilla {legs[indices[0]]['optionType']}",
                    "direction": "Long" if legs[indices[0]]["side"] == 1 else "Short",
                    "score": 0,
                    "confidence": (
                        legs[indices[0]]["sideConfidence"]
                        if len(legs) == 1
                        and legs[indices[0]]["notional"] is not None
                        else "Medium"
                    ),
                }
            )
        else:
            result.append(candidates[candidate_index])
    return result, False


def payoff_configuration(legs: list[dict], pair: str) -> tuple[str, str, list[float]]:
    letters = "".join(character for character in pair.upper() if character.isalpha())
    base = letters[:3] if len(letters) == 6 else ""
    quote = letters[3:] if len(letters) == 6 else ""
    actual = bool(base and quote)
    weights = []
    for leg in legs:
        notional = leg["notional"]
        currency = leg["notionalCcy"].upper()
        if notional is None or notional <= 0 or currency not in {base, quote}:
            actual = False
            break
        weights.append(
            notional if currency == base else notional / max(leg["strike"], 1e-12)
        )
    if actual:
        return "Actual", quote, weights

    available = [
        leg["notional"]
        for leg in legs
        if leg["notional"] is not None and leg["notional"] > 0
    ]
    scale = min(available) if available else 1.0
    weights = [
        (leg["notional"] / scale)
        if leg["notional"] is not None and leg["notional"] > 0
        else 1.0
        for leg in legs
    ]
    return "Normalized", "normalized units", weights


def infer_option_structures(trades: pd.DataFrame) -> list[dict]:
    working = trades.copy()
    legs_by_index: dict[int, dict] = {}
    for index, row in working.iterrows():
        side, side_confidence = infer_leg_side(row)
        notional = None if pd.isna(row["Notional"]) else abs(float(row["Notional"]))
        legs_by_index[index] = {
            "rowIndex": int(index),
            "uniqueId": str(row["UniqueID"]),
            "pair": str(row["Pair"]),
            "optionType": str(row["OptionType"]),
            "strike": float(row["Strike"]),
            "side": side,
            "sideLabel": "Long" if side == 1 else "Short",
            "sideConfidence": side_confidence,
            "notional": notional,
            "notionalCcy": str(row["NotionalCCY"]).strip(),
            "delta": float(row["Delta"]),
            "gamma": float(row["Gamma"]),
            "vega": float(row["VegaPortCCY"]),
            "theta": float(row["ThetaPortCCY"]),
            "pnl": float(row["PnL"]),
            "expiry": pd.Timestamp(row["ExpiryDate"]).strftime("%Y-%m-%d"),
            "shore": str(row["Shore"]),
        }

    group_columns = [
        "Pair",
        "ExpiryDate",
        "Shore",
        "NotionalCCY",
    ]
    structures = []
    for _, bucket in working.groupby(group_columns, dropna=False, sort=True):
        bucket_legs = [legs_by_index[index] for index in bucket.index]
        partition, ambiguous = best_bucket_partition(bucket_legs)
        if ambiguous:
            partition = [
                {
                    "indices": (index,),
                    "type": "Unclassified Leg",
                    "direction": "Long" if leg["side"] == 1 else "Short",
                    "score": 0,
                    "confidence": "Ambiguous",
                }
                for index, leg in enumerate(bucket_legs)
            ]

        for candidate in partition:
            selected = [bucket_legs[index] for index in candidate["indices"]]
            selected.sort(key=lambda leg: (leg["strike"], leg["optionType"]))
            mode, payout_currency, weights = payoff_configuration(
                selected, selected[0]["pair"]
            )
            for leg, weight in zip(selected, weights):
                leg["payoffWeight"] = weight
            structures.append(
                {
                    "pair": selected[0]["pair"],
                    "type": candidate["type"],
                    "direction": candidate["direction"],
                    "label": f"{candidate['direction']} {candidate['type']}",
                    "confidence": candidate["confidence"],
                    "expiry": selected[0]["expiry"],
                    "shore": selected[0]["shore"],
                    "strikes": " / ".join(f"{leg['strike']:g}" for leg in selected),
                    "ratio": notional_ratio_label(selected),
                    "pnl": sum(leg["pnl"] for leg in selected),
                    "delta": sum(leg["delta"] for leg in selected),
                    "gamma": sum(leg["gamma"] for leg in selected),
                    "vega": sum(leg["vega"] for leg in selected),
                    "theta": sum(leg["theta"] for leg in selected),
                    "payoffMode": mode,
                    "payoutCurrency": payout_currency,
                    "legs": selected,
                }
            )

    structures.sort(
        key=lambda item: (
            item["pair"],
            item["expiry"],
            item["label"],
            item["strikes"],
        )
    )
    for index, structure in enumerate(structures, start=1):
        structure["id"] = f"S{index:03d}"
    return structures


def leg_group_key(leg: dict) -> tuple[str, str, str, str]:
    return (
        leg["pair"],
        leg["expiry"],
        leg["shore"],
        leg["notionalCcy"],
    )


def limited_join(items: list[str], limit: int = 6) -> str:
    if len(items) <= limit:
        return "; ".join(items)
    return "; ".join(items[:limit]) + f"; +{len(items) - limit} more"


def candidate_log_label(candidate: dict, legs: list[dict]) -> str:
    member_ids = ",".join(
        legs[index]["uniqueId"] for index in candidate["indices"]
    )
    return f"{candidate['direction']} {candidate['type']} [{member_ids}]"


def pair_rejection_reason(first: dict, second: dict) -> str:
    reasons = []
    if first["side"] == second["side"]:
        reasons.append(f"same inferred side ({first['sideLabel']})")
    if (
        first["optionType"] == second["optionType"]
        and first["strike"] == second["strike"]
    ):
        reasons.append("same option type and strike")
    return " and ".join(reasons) or "not selected in the best full-bucket partition"


def explain_not_grouped_leg(
    leg: dict,
    status: str,
    all_legs: list[dict],
) -> str:
    same_pair = [
        other
        for other in all_legs
        if other["pair"] == leg["pair"] and other["uniqueId"] != leg["uniqueId"]
    ]
    bucket = [other for other in all_legs if leg_group_key(other) == leg_group_key(leg)]
    reasons = []

    if len(bucket) > 14:
        reasons.append(
            f"classification bucket has {len(bucket)} trades, above the 14-trade limit"
        )
    elif len(bucket) == 1:
        reasons.append("only trade sharing all four grouping fields")
    else:
        candidates = build_structure_candidates(bucket)
        leg_index = next(
            index
            for index, bucket_leg in enumerate(bucket)
            if bucket_leg["uniqueId"] == leg["uniqueId"]
        )
        matching_candidates = [
            candidate for candidate in candidates if leg_index in candidate["indices"]
        ]
        if matching_candidates:
            candidate_labels = sorted(
                {
                    candidate_log_label(candidate, bucket)
                    for candidate in matching_candidates
                }
            )
            if status == "UNCLASSIFIED":
                reasons.append(
                    "multiple equally scoring full-bucket partitions; "
                    "candidate matches: " + limited_join(candidate_labels)
                )
            else:
                reasons.append(
                    "valid candidate existed but the highest-scoring full-bucket "
                    "partition left this trade standalone; candidate matches: "
                    + limited_join(candidate_labels)
                )
        elif candidates and status == "UNCLASSIFIED":
            reasons.append(
                "the bucket had multiple equally scoring partitions, but this trade "
                "was not part of a valid candidate"
            )
        else:
            rejected = [
                f"{other['uniqueId']} ({pair_rejection_reason(leg, other)})"
                for other in bucket
                if other["uniqueId"] != leg["uniqueId"]
            ]
            reasons.append(
                "no supported combination with other trades in the bucket: "
                + limited_join(rejected)
            )

    excluded = []
    for other in same_pair:
        if leg_group_key(other) == leg_group_key(leg):
            continue
        differences = []
        if other["expiry"] != leg["expiry"]:
            differences.append(f"ExpiryDate={other['expiry']}")
        if other["shore"] != leg["shore"]:
            differences.append(f"Shore={other['shore']}")
        if other["notionalCcy"] != leg["notionalCcy"]:
            differences.append(f"NotionalCCY={other['notionalCcy']}")
        excluded.append(f"{other['uniqueId']} ({', '.join(differences)})")
    if excluded:
        reasons.append(
            "same-pair trades excluded by grouping fields: " + limited_join(excluded)
        )
    elif not same_pair:
        reasons.append("no other latest-snapshot trades for this currency pair")

    return "; ".join(reasons)


def print_structure_grouping_log(structures: list[dict]) -> None:
    grouped_trades = 0
    single_trades = 0
    unclassified_trades = 0

    print("Option structure grouping:")
    print(
        "  Status key: GROUPED=multi-leg structure; "
        "SINGLE=standalone vanilla; UNCLASSIFIED=no confident match"
    )
    all_legs = [leg for structure in structures for leg in structure["legs"]]
    for structure in structures:
        legs = structure["legs"]
        member_ids = ",".join(leg["uniqueId"] for leg in legs)
        currencies = ",".join(
            sorted({leg["notionalCcy"] or "(blank)" for leg in legs})
        )
        if structure["type"] == "Unclassified Leg":
            status = "UNCLASSIFIED"
            unclassified_trades += len(legs)
        elif len(legs) == 1:
            status = "SINGLE"
            single_trades += 1
        else:
            status = "GROUPED"
            grouped_trades += len(legs)

        for leg in legs:
            companions = ",".join(
                member["uniqueId"]
                for member in legs
                if member["uniqueId"] != leg["uniqueId"]
            ) or "none"
            print(
                f"  [{status}] ID={leg['uniqueId']} | "
                f"{leg['optionType']} K={leg['strike']:g} | "
                f"Pair={structure['pair']} | Expiry={structure['expiry']} | "
                f"Shore={structure['shore']} | NotionalCCY={currencies} | "
                f"Structure={structure['label']} | "
                f"Members={member_ids} | Companions={companions}"
            )
            if status != "GROUPED":
                print(
                    "    Reason: "
                    + explain_not_grouped_leg(leg, status, all_legs)
                )

    multi_leg_structures = sum(
        len(structure["legs"]) > 1
        and structure["type"] != "Unclassified Leg"
        for structure in structures
    )
    standalone_label = "trade" if single_trades == 1 else "trades"
    print(
        "Structure grouping summary: "
        f"{grouped_trades} grouped trades in {multi_leg_structures} "
        f"multi-leg structures; {single_trades} standalone {standalone_label}; "
        f"{unclassified_trades} unclassified trades"
    )


def inject_structure_analysis(output: Path, trades: pd.DataFrame) -> list[dict]:
    structures = infer_option_structures(trades)

    def value_class(value: float) -> str:
        return "pnl-positive" if value > 0 else "pnl-negative" if value < 0 else ""

    rows = []
    for structure in structures:
        confidence_class = structure["confidence"].lower()
        leg_chips = "".join(
            '<span class="structure-leg-chip">'
            f"<strong>{html.escape(leg['sideLabel'])} {html.escape(leg['optionType'])}</strong> "
            f"K {leg['strike']:g} · "
            f"{'N/A notional' if leg['notional'] is None else f'{leg['notional']:,.0f} {html.escape(leg['notionalCcy'])}'} · "
            f"ID {html.escape(leg['uniqueId'])}"
            "</span>"
            for leg in structure["legs"]
        )
        rows.append(
            f'<tr class="structure-row" data-structure-id="{structure["id"]}" '
            'tabindex="0" role="button">'
            f'<td><strong>{html.escape(structure["label"])}</strong></td>'
            f'<td>{html.escape(structure["pair"])}</td>'
            f'<td>{html.escape(structure["expiry"])}</td>'
            f'<td>{html.escape(structure["strikes"])}</td>'
            f'<td>{html.escape(structure["ratio"])}</td>'
            f'<td class="num {value_class(structure["pnl"])}">{html.escape(format_money(structure["pnl"]))}</td>'
            f'<td class="num {value_class(structure["delta"])}">{html.escape(format_money(structure["delta"]))}</td>'
            f'<td class="num {value_class(structure["gamma"])}">{html.escape(format_money(structure["gamma"]))}</td>'
            f'<td class="num {value_class(structure["vega"])}">{html.escape(format_money(structure["vega"]))}</td>'
            f'<td class="num {value_class(structure["theta"])}">{html.escape(format_money(structure["theta"]))}</td>'
            f'<td><span class="structure-confidence {confidence_class}">{html.escape(structure["confidence"])}</span></td>'
            "</tr>"
            f'<tr class="structure-leg-row" data-structure-detail="{structure["id"]}" hidden>'
            f'<td colspan="11"><div class="structure-leg-list">{leg_chips}</div></td></tr>'
        )

    if not rows:
        rows.append(
            '<tr><td colspan="11" class="structure-empty">'
            "No current option positions are available for structure inference.</td></tr>"
        )

    css = """
.structure-section{margin:0 0 24px}.structure-section-head{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin:0 0 12px}
.structure-section-head h2{margin:0;font-size:21px}.structure-section-head p{margin:4px 0 0;color:var(--muted);font-size:12px}
.structure-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(420px,.85fr);gap:18px;align-items:start}
.structure-card{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(23,49,81,.05)}
.structure-table-wrap{max-height:520px;overflow:auto}.structure-table{font-size:11px}.structure-table th{font-size:10px;cursor:default}
.structure-table td{padding:9px 10px}.structure-table td.num{font-size:12px;font-weight:600}
.structure-row{cursor:pointer}.structure-row.selected td{background:#eaf2ff}.structure-row:focus-visible{outline:2px solid #2463eb;outline-offset:-2px}
.structure-leg-row td{padding:9px 12px;background:#f4f7fb}.structure-leg-list{display:flex;flex-wrap:wrap;gap:7px}
.structure-leg-chip{padding:6px 8px;border:1px solid #d7e0e9;border-radius:7px;background:#fff;color:var(--muted);font-size:10px}
.structure-leg-chip strong{color:var(--ink)}.structure-confidence{display:inline-block;padding:4px 7px;border-radius:999px;font-size:10px;font-weight:700}
.structure-confidence.high{color:#0d6a54;background:#dff5ed}.structure-confidence.medium,.structure-confidence.low{color:#8a5500;background:#fff1d3}
.structure-confidence.ambiguous{color:#9b2c3d;background:#fde7ea}.structure-empty{text-align:center;color:var(--muted)}
.payoff-card{padding:15px}.payoff-card h3{margin:0;font-size:17px}.payoff-meta{margin:5px 0 10px;color:var(--muted);font-size:11px}
.payoff-card svg{display:block;width:100%;height:auto}.payoff-grid{stroke:#e7ecf2;stroke-width:1}.payoff-zero{stroke:#8796a7;stroke-width:1.2}
.payoff-strike{stroke:#d88917;stroke-width:1;stroke-dasharray:4 4}.payoff-line{fill:none;stroke:#2463eb;stroke-width:2.7;stroke-linecap:round;stroke-linejoin:round}
.payoff-axis{fill:#687789;font-size:10px}.payoff-strike-label{fill:#9a5d05;font-size:9px;font-weight:700}
.structure-note{padding:10px 14px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.45}
@media(max-width:1200px){.structure-layout{grid-template-columns:1fr}}
"""
    markup = f"""
<section class="structure-section">
  <div class="structure-section-head">
    <div><h2>Inferred option structures</h2><p>Grouped without PositionName · Click a row to inspect its legs and terminal payoff</p></div>
  </div>
  <div class="structure-layout">
    <article class="structure-card">
      <div class="structure-table-wrap"><table class="structure-table"><thead><tr><th>Structure</th><th>Pair</th><th>Expiry</th><th>Strikes</th><th>Ratio</th><th class="num">Current P&amp;L</th><th class="num">Delta</th><th class="num">Gamma</th><th class="num">Vega</th><th class="num">Theta</th><th>Confidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
      <div class="structure-note">Inference uses pair, expiry, shore, option type, signed risks, strikes, and notionals. Ambiguous combinations are not forced.</div>
    </article>
    <article class="structure-card payoff-card">
      <h3 id="payoffTitle">Terminal payoff</h3>
      <div id="payoffMeta" class="payoff-meta">Select a structure</div>
      <div id="payoffChart"></div>
      <div class="structure-note">Terminal intrinsic payoff before premium. Current MTM P&amp;L is shown separately and is not added to the curve.</div>
    </article>
  </div>
</section>
"""
    safe_json = json.dumps(structures, ensure_ascii=False).replace("</", "<\\/")
    script = r"""
<script>
const FXO_STRUCTURES=__STRUCTURE_JSON__;
(function(){
  function compact(value){
    var absolute=Math.abs(value),units=absolute>=1e9?[1e9,"bn"]:absolute>=1e6?[1e6,"m"]:absolute>=1e3?[1e3,"k"]:[1,""];
    var digits=absolute/units[0]>=100?0:1;
    return (value<0?"−":"")+(absolute/units[0]).toFixed(digits)+units[1];
  }
  function renderPayoff(id){
    var structure=FXO_STRUCTURES.find(function(item){return item.id===id});
    if(!structure)return;
    document.getElementById("payoffTitle").textContent=structure.label+" · "+structure.pair;
    document.getElementById("payoffMeta").textContent=structure.expiry+" expiry · "+structure.payoffMode+" payoff in "+structure.payoutCurrency;
    var strikes=structure.legs.map(function(leg){return leg.strike});
    var minimum=Math.min.apply(null,strikes),maximum=Math.max.apply(null,strikes),span=Math.max(maximum-minimum,Math.abs(minimum)*0.12,0.01);
    var low=Math.max(0,minimum-span*.75),high=maximum+span*.75,points=[];
    for(var index=0;index<=120;index+=1){
      var terminal=low+(high-low)*index/120,payoff=0;
      structure.legs.forEach(function(leg){
        var intrinsic=leg.optionType==="Call"?Math.max(terminal-leg.strike,0):Math.max(leg.strike-terminal,0);
        payoff+=leg.side*leg.payoffWeight*intrinsic;
      });
      points.push([terminal,payoff]);
    }
    var values=points.map(function(point){return point[1]}).concat([0]),minY=Math.min.apply(null,values),maxY=Math.max.apply(null,values),pad=Math.max((maxY-minY)*.12,Math.max(Math.abs(minY),Math.abs(maxY))*0.08,1e-9);
    minY-=pad;maxY+=pad;
    var width=720,height=360,left=78,right=24,top=24,bottom=52,plotWidth=width-left-right,plotHeight=height-top-bottom;
    function x(value){return left+(value-low)/(high-low)*plotWidth}
    function y(value){return top+(maxY-value)/(maxY-minY)*plotHeight}
    var svg=['<svg viewBox="0 0 '+width+' '+height+'" role="img" aria-label="Terminal payoff against terminal FX rate">'];
    for(var tick=0;tick<5;tick+=1){
      var yValue=minY+(maxY-minY)*tick/4,yPos=y(yValue);
      svg.push('<line class="payoff-grid" x1="'+left+'" y1="'+yPos+'" x2="'+(width-right)+'" y2="'+yPos+'"/>');
      svg.push('<text class="payoff-axis" x="'+(left-9)+'" y="'+(yPos+4)+'" text-anchor="end">'+compact(yValue)+'</text>');
    }
    for(var xTick=0;xTick<5;xTick+=1){
      var xValue=low+(high-low)*xTick/4,xPos=x(xValue);
      svg.push('<text class="payoff-axis" x="'+xPos+'" y="'+(height-19)+'" text-anchor="middle">'+xValue.toFixed(Math.abs(xValue)<10?4:2).replace(/0+$/,"").replace(/\.$/,"")+'</text>');
    }
    svg.push('<line class="payoff-zero" x1="'+left+'" y1="'+y(0)+'" x2="'+(width-right)+'" y2="'+y(0)+'"/>');
    Array.from(new Set(strikes)).sort(function(a,b){return a-b}).forEach(function(strike){
      var xPos=x(strike);svg.push('<line class="payoff-strike" x1="'+xPos+'" y1="'+top+'" x2="'+xPos+'" y2="'+(height-bottom)+'"/>');
      svg.push('<text class="payoff-strike-label" x="'+xPos+'" y="'+(top+10)+'" text-anchor="middle">K '+strike+'</text>');
    });
    var path=points.map(function(point,index){return(index===0?"M ":"L ")+x(point[0]).toFixed(2)+" "+y(point[1]).toFixed(2)}).join(" ");
    svg.push('<path class="payoff-line" d="'+path+'"/>');
    svg.push('<text class="payoff-axis" x="'+(left+plotWidth/2)+'" y="'+(height-3)+'" text-anchor="middle">Terminal '+structure.pair+' rate</text>');
    svg.push('</svg>');
    document.getElementById("payoffChart").innerHTML=svg.join("");
  }
  function selectStructure(row){
    document.querySelectorAll(".structure-row").forEach(function(item){item.classList.toggle("selected",item===row)});
    document.querySelectorAll(".structure-leg-row").forEach(function(item){item.hidden=item.dataset.structureDetail!==row.dataset.structureId});
    renderPayoff(row.dataset.structureId);
  }
  document.querySelectorAll(".structure-row").forEach(function(row){
    row.addEventListener("click",function(){selectStructure(row)});
    row.addEventListener("keydown",function(event){if(event.key==="Enter"||event.key===" "){event.preventDefault();selectStructure(row)}});
  });
  var first=document.querySelector(".structure-row");if(first)selectStructure(first);
})();
</script>
""".replace("__STRUCTURE_JSON__", safe_json)

    document = output.read_text(encoding="utf-8")
    if "</style>" not in document:
        raise RuntimeError("Could not locate dashboard style hook")
    document = document.replace("</style>", css + "\n</style>", 1)
    chart_hook = '<section class="chart-grid"><article class="chart-card"><h2>Delta</h2>'
    if chart_hook not in document:
        raise RuntimeError("Could not locate dashboard chart hook")
    document = document.replace(chart_hook, markup + "\n" + chart_hook, 1)
    document = document.replace("</body>", script + "\n</body>", 1)
    output.write_text(document, encoding="utf-8")
    return structures


def inject_ytd_pnl(
    output: Path,
    book_history: pd.DataFrame,
    pair_history: pd.DataFrame,
    netted: pd.DataFrame,
) -> None:
    book_points = [
        (pd.Timestamp(row.CobDate), float(row.YtdPnL))
        for row in book_history.itertuples()
    ]
    latest_book = book_points[-1][1]
    comparison_date, current_pnl, wow_change, contributors = build_wow_summary(
        book_history, pair_history
    )
    greek_metrics = [
        ("Delta", "NetDelta"),
        ("Gamma", "NetGamma"),
        ("Vega", "NetVega"),
        ("Theta", "NetTheta"),
    ]
    greek_columns = [column for _, column in greek_metrics]
    greeks_by_pair = netted.groupby("Pair")[greek_columns].sum()
    book_greeks = greeks_by_pair.sum()

    def value_class(value: float) -> str:
        return (
            "pnl-positive"
            if value > 0
            else "pnl-negative"
            if value < 0
            else ""
        )

    def greek_cells(pair: str | None = None) -> str:
        if pair is None:
            values = book_greeks
        elif pair in greeks_by_pair.index:
            values = greeks_by_pair.loc[pair]
        else:
            values = None

        cells = []
        for _, column in greek_metrics:
            value = 0.0 if values is None else float(values[column])
            cells.append(
                f'<td class="num {value_class(value)}">'
                f"{html.escape(format_money(value))}</td>"
            )
        return "".join(cells)

    def expiry_cell(pair: str) -> str:
        expiries = sorted(
            {
                pd.Timestamp(value)
                for value in netted.loc[netted["Pair"].eq(pair), "ExpiryDate"]
            }
        )
        text = " · ".join(date.strftime("%d %b %Y") for date in expiries) or "—"
        return f'<td class="pnl-expiry">{html.escape(text)}</td>'

    current_class = value_class(current_pnl)
    if wow_change is None:
        wow_text = "N/A"
        wow_class = ""
        comparison_label = "No 1-week comparison available"
        contribution_rows = (
            '<tr><td colspan="8" class="pnl-no-change">'
            "No 1-week comparison date is available.</td></tr>"
        )
    else:
        wow_text = format_money(wow_change)
        wow_class = value_class(wow_change)
        comparison_label = f"vs {comparison_date:%d %b %Y}"
        contribution_rows = "".join(
            "<tr>"
            f"<td>{html.escape(pair)}</td>"
            f'<td class="num {value_class(current)}">'
            f"{html.escape(format_money(current))}</td>"
            f'<td class="num {value_class(change)}">'
            f"{html.escape(format_money(change))}</td>"
            f"{greek_cells(pair)}"
            f"{expiry_cell(pair)}"
            "</tr>"
            for pair, current, change in contributors
        )
        if not contribution_rows:
            contribution_rows = (
                '<tr><td colspan="8" class="pnl-no-change">'
                "No currency-pair P&amp;L changes in this window.</td></tr>"
            )

    whole_book_row = (
        '<tfoot><tr class="pnl-total-row"><td>Whole book</td>'
        f'<td class="num {current_class}">{html.escape(format_money(current_pnl))}</td>'
        f'<td class="num {wow_class}">{html.escape(wow_text)}</td>'
        f"{greek_cells()}"
        '<td class="pnl-expiry"></td>'
        "</tr></tfoot>"
    )

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
.pnl-headlines{display:grid;grid-template-columns:repeat(2,minmax(0,260px));gap:12px;margin:0 0 12px}
.pnl-kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:0 4px 14px rgba(23,49,81,.05)}
.pnl-kpi span,.pnl-kpi small{display:block;color:var(--muted);font-size:11px}.pnl-kpi strong{display:block;margin:5px 0 3px;font-size:25px}
.pnl-contribution-card{margin:0 0 18px;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(23,49,81,.05)}
.pnl-contribution-head{display:flex;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--line)}
.pnl-contribution-head h3{margin:0;font-size:15px}.pnl-contribution-head span{color:var(--muted);font-size:11px}
.pnl-contribution-card table{font-size:12px}.pnl-contribution-card th{position:static;padding:9px 16px;cursor:default}.pnl-contribution-card td{padding:9px 16px}
.pnl-contribution-card td.num{font-size:18px}
.pnl-expiry{min-width:170px;white-space:normal;color:var(--muted);line-height:1.45}
.pnl-total-row td{background:#edf3f9;border-top:2px solid #cbd6e2;font-weight:700}
.pnl-positive{color:var(--pos)}.pnl-negative{color:var(--neg)}.pnl-no-change{text-align:center;color:var(--muted)}
.pnl-card-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 10px 2px}
.pnl-card-head h2{margin:0}.pnl-latest{font-size:19px;font-weight:700;color:var(--pos);white-space:nowrap}
.pnl-card svg{display:block;width:100%;height:auto}.pnl-grid-line{stroke:#e7ecf2;stroke-width:1}
.pnl-zero-line{stroke:#9ba8b6;stroke-width:1.25;stroke-dasharray:5 4}.pnl-axis-label{font-size:11px;fill:#687789}
.pnl-point{stroke:#fff;stroke-width:1;cursor:crosshair}.pnl-point:hover{r:5}
.pnl-legend{display:flex;flex-wrap:wrap;gap:8px 15px;padding:0 13px 12px;color:var(--muted);font-size:11px}
.pnl-legend-item{display:inline-flex;align-items:center;gap:5px}.pnl-legend-item i{display:inline-block;width:9px;height:9px;border-radius:50%}
.pnl-legend-item strong{color:var(--ink);font-weight:600}
@media(max-width:1100px){.pnl-section-head{align-items:flex-start;flex-direction:column}.pnl-headlines{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.pnl-headlines{grid-template-columns:1fr}}
"""
    markup = f"""
<section class="pnl-section">
  <div class="pnl-section-head">
    <div><h2>YTD P&amp;L</h2><p>Rebased to the first available CobDate · Last observed trade P&amp;L is carried forward by UniqueID after disappearance</p></div>
  </div>
  <div class="pnl-headlines">
    <article class="pnl-kpi"><span>Current P&amp;L</span><strong class="{current_class}">{html.escape(format_money(current_pnl))}</strong><small>As of {book_points[-1][0]:%d %b %Y}</small></article>
    <article class="pnl-kpi"><span>WoW change</span><strong class="{wow_class}">{html.escape(wow_text)}</strong><small>{html.escape(comparison_label)}</small></article>
  </div>
  <div class="pnl-contribution-card">
    <div class="pnl-contribution-head"><h3>Currency-pair contribution to WoW P&amp;L</h3><span>Only non-zero changes shown</span></div>
    <table><thead><tr><th>Currency pair</th><th class="num">Current P&amp;L</th><th class="num">WoW contribution</th><th class="num">Delta</th><th class="num">Gamma</th><th class="num">Vega</th><th class="num">Theta</th><th>Expiry dates</th></tr></thead><tbody>{contribution_rows}</tbody>{whole_book_row}</table>
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
    inject_ytd_pnl(output, book_history, pair_history, netted)
    structures = inject_structure_analysis(output, trades)

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
    print_structure_grouping_log(structures)


if __name__ == "__main__":
    main()
