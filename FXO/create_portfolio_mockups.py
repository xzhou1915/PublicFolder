from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch


OUT = Path("/home/ubuntu/PublicFolder/FXO")
AS_OF = pd.Timestamp("2026-09-09")


def sample_positions() -> pd.DataFrame:
    rows = [
        ("USDZAR Curncy", "Offshore", "Put", 16.35, "2026-10-23", -177732, 123342, 250_000_000, "USD", 123211),
        ("USDZAR Curncy", "Offshore", "Call", 18.10, "2026-12-18", 112400, 68400, 180_000_000, "USD", -420000),
        ("USDZAR Curncy", "Onshore", "Put", 16.80, "2027-03-19", -82400, 47200, 120_000_000, "USD", 310500),
        ("EURUSD Curncy", "Offshore", "Call", 1.12, "2026-09-25", 145600, 93400, 200_000_000, "USD", 780000),
        ("EURUSD Curncy", "Offshore", "Put", 1.07, "2026-11-20", -118200, 71500, 160_000_000, "USD", -235000),
        ("EURUSD Curncy", "Offshore", "Call", 1.15, "2027-01-15", 96400, 52600, 140_000_000, "USD", 445000),
        ("USDJPY Curncy", "Offshore", "Call", 151.00, "2026-10-09", 164300, 101200, 220_000_000, "USD", -615000),
        ("USDJPY Curncy", "Offshore", "Put", 142.00, "2026-12-11", -132600, 84200, 190_000_000, "USD", 525000),
        ("USDJPY Curncy", "Onshore", "Put", 139.00, "2027-06-18", -68500, 31100, 100_000_000, "USD", 184000),
        ("GBPUSD Curncy", "Offshore", "Put", 1.28, "2026-09-18", -156800, 119300, 175_000_000, "USD", 290000),
        ("GBPUSD Curncy", "Offshore", "Call", 1.36, "2026-12-31", 89300, 49800, 125_000_000, "USD", -165000),
        ("USDCNH Curncy", "Offshore", "Call", 7.35, "2026-11-06", 137900, 88800, 210_000_000, "USD", 362000),
        ("USDCNH Curncy", "Offshore", "Put", 7.05, "2027-02-26", -105400, 55700, 150_000_000, "USD", -338000),
        ("AUDUSD Curncy", "Offshore", "Call", 0.69, "2026-10-30", 74500, 60300, 90_000_000, "USD", 211000),
        ("AUDUSD Curncy", "Offshore", "Put", 0.64, "2027-03-26", -62300, 37600, 80_000_000, "USD", -97000),
        ("EURGBP Curncy", "Offshore", "Put", 0.83, "2027-01-29", -71300, 42900, 95_000_000, "USD", 156000),
    ]
    cols = ["Underlying", "Shore", "OptionType", "Strike", "ExpiryDate", "Delta", "Gamma", "Notional", "NotionalCCY", "PnL"]
    df = pd.DataFrame(rows, columns=cols)
    df["ExpiryDate"] = pd.to_datetime(df["ExpiryDate"])
    df["DTE"] = (df["ExpiryDate"] - AS_OF).dt.days
    df["Pair"] = df["Underlying"].str.replace(" Curncy", "", regex=False)
    df["ExpiryMonth"] = df["ExpiryDate"].dt.to_period("M").astype(str)
    return df


def money(v, decimals=1):
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000:
        return f"{sign}${v/1_000_000_000:.{decimals}f}bn"
    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:.{decimals}f}m"
    if v >= 1_000:
        return f"{sign}${v/1_000:.0f}k"
    return f"{sign}${v:.0f}"


def base_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "figure.facecolor": "#f4f7fb",
        "axes.facecolor": "white",
        "axes.edgecolor": "#d9e1ea",
        "axes.titleweight": "bold",
        "axes.titlesize": 12,
        "xtick.color": "#526273",
        "ytick.color": "#526273",
        "text.color": "#172433",
    })


def card(ax, title, value, note, color="#2463eb"):
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.02,rounding_size=0.04",
                                transform=ax.transAxes, facecolor="white", edgecolor="#dfe6ee"))
    ax.text(.06, .76, title.upper(), fontsize=8.5, color="#657588", weight="bold", transform=ax.transAxes)
    ax.text(.06, .40, value, fontsize=20, color=color, weight="bold", transform=ax.transAxes)
    ax.text(.06, .13, note, fontsize=8.2, color="#748295", transform=ax.transAxes)


def overview(df):
    base_style()
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(4, 12, height_ratios=[.28, 1.0, 2.7, 2.6], hspace=.68, wspace=.8)
    title = fig.add_subplot(gs[0, :]); title.axis("off")
    title.text(0, .72, "FX Options Portfolio — Overview", fontsize=21, weight="bold")
    title.text(0, .05, "Illustrative data  •  As of 9 Sep 2026  •  USD notionals", fontsize=9.5, color="#6c7a89")

    pnl = df.PnL.sum(); gross = df.Notional.sum()
    cards = [
        ("Positions", f"{len(df)}", f"{df.Pair.nunique()} currency pairs", "#2463eb"),
        ("Gross notional", money(gross), "Sum of position notionals", "#2463eb"),
        ("Portfolio PnL", money(pnl), f"{(df.PnL > 0).sum()} winners / {(df.PnL < 0).sum()} losers", "#13966f" if pnl >= 0 else "#d94b55"),
        ("Next expiry", f"{df.DTE.min()} days", df.loc[df.DTE.idxmin(), "Pair"] + " · " + df.loc[df.DTE.idxmin(), "ExpiryDate"].strftime("%d %b"), "#e07a24"),
    ]
    for i, item in enumerate(cards):
        card(fig.add_subplot(gs[1, i*3:(i+1)*3]), *item)

    by_pair = df.groupby("Pair").agg(Notional=("Notional", "sum"), PnL=("PnL", "sum"), Delta=("Delta", "sum"), Gamma=("Gamma", "sum")).sort_values("Notional")
    ax1 = fig.add_subplot(gs[2, :6])
    colors = ["#326dd8" if p >= 0 else "#9bb4df" for p in by_pair.PnL]
    ax1.barh(by_pair.index, by_pair.Notional/1e6, color=colors)
    ax1.set_title("Where the notional sits", loc="left", pad=12)
    ax1.set_xlabel("Gross notional (USD m)")
    ax1.grid(axis="x", alpha=.18); ax1.spines[["top", "right", "left"]].set_visible(False)
    for y, (n, p) in enumerate(zip(by_pair.Notional/1e6, by_pair.PnL)):
        ax1.text(n+5, y, f"{n:.0f}m  |  PnL {money(p)}", va="center", fontsize=8.5)

    ax2 = fig.add_subplot(gs[2, 6:])
    bp = by_pair.sort_values("Delta")
    ax2.barh(bp.index, bp.Delta/1000, color=np.where(bp.Delta >= 0, "#23a37a", "#df5a63"))
    ax2.axvline(0, color="#526273", lw=.8)
    ax2.set_title("Directional exposure by pair", loc="left", pad=12)
    ax2.set_xlabel("Net delta (thousands, source units)")
    ax2.grid(axis="x", alpha=.18); ax2.spines[["top", "right", "left"]].set_visible(False)

    ax3 = fig.add_subplot(gs[3, :7])
    buckets = pd.cut(df.DTE, bins=[0, 30, 90, 180, 365, np.inf], labels=["0–30d", "31–90d", "91–180d", "181–365d", ">1y"])
    exp = df.assign(Bucket=buckets).groupby(["Bucket", "OptionType"], observed=False).Notional.sum().unstack(fill_value=0)/1e6
    x = np.arange(len(exp)); width=.34
    ax3.bar(x-width/2, exp.get("Call", 0), width, label="Call", color="#2463eb")
    ax3.bar(x+width/2, exp.get("Put", 0), width, label="Put", color="#9b66d9")
    ax3.set_xticks(x, exp.index); ax3.set_ylabel("USD m")
    ax3.set_title("Expiry ladder", loc="left", pad=12); ax3.legend(frameon=False, ncol=2)
    ax3.grid(axis="y", alpha=.18); ax3.spines[["top", "right"]].set_visible(False)

    ax4 = fig.add_subplot(gs[3, 7:]); ax4.axis("off")
    ax4.set_title("Attention list", loc="left", pad=12)
    nearest = df.nsmallest(3, "DTE")
    worst = df.nsmallest(2, "PnL")
    lines = ["EXPIRING SOON"] + [f"{r.Pair:<7}  {r.OptionType:<4}  {r.DTE:>3}d  ·  {money(r.Notional)}" for r in nearest.itertuples()]
    lines += ["", "LARGEST LOSSES"] + [f"{r.Pair:<7}  {r.OptionType:<4}  {money(r.PnL)}  ·  {r.ExpiryDate:%d %b %Y}" for r in worst.itertuples()]
    y=.9
    for line in lines:
        is_head = line in {"EXPIRING SOON", "LARGEST LOSSES"}
        ax4.text(.02, y, line, fontsize=9 if not is_head else 8.5, weight="bold" if is_head else "normal",
                 color="#687789" if is_head else "#1c2938", family="DejaVu Sans Mono" if not is_head else "DejaVu Sans")
        y -= .115 if line else .07
    fig.text(.01, .012, "Design intent: a 10-second senior view. Delta/Gamma are not summed across currency pairs.", fontsize=8, color="#728095")
    fig.savefig(OUT / "option_1_overview_dashboard.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def maturity_map(df):
    base_style()
    pairs = df.groupby("Pair").Notional.sum().sort_values(ascending=False).index
    months = pd.period_range(df.ExpiryDate.min().to_period("M"), df.ExpiryDate.max().to_period("M"), freq="M").astype(str)
    pivot = df.pivot_table(index="Pair", columns="ExpiryMonth", values="Notional", aggfunc="sum", fill_value=0).reindex(index=pairs, columns=months, fill_value=0)/1e6
    pnl = df.pivot_table(index="Pair", columns="ExpiryMonth", values="PnL", aggfunc="sum", fill_value=0).reindex(index=pairs, columns=months, fill_value=0)
    fig, ax = plt.subplots(figsize=(16, 7.8))
    vals = pivot.values
    im = ax.imshow(vals, cmap="Blues", aspect="auto", vmin=0, vmax=max(1, vals.max()))
    ax.set_xticks(range(len(months)), [pd.Period(m).strftime("%b\n%Y") for m in months])
    ax.set_yticks(range(len(pairs)), pairs)
    ax.tick_params(length=0); ax.spines[:].set_visible(False)
    ax.set_title("FX Options Maturity Map", loc="left", fontsize=21, pad=34)
    ax.text(0, 1.025, "Bubble-free concentration view: cell = gross notional; dot = PnL sign", transform=ax.transAxes, fontsize=9.5, color="#6c7a89")
    for i in range(len(pairs)):
        for j in range(len(months)):
            if vals[i, j] > 0:
                txt_color = "white" if vals[i, j] > vals.max()*.52 else "#173151"
                ax.text(j, i-.08, f"${vals[i,j]:.0f}m", ha="center", va="center", color=txt_color, fontsize=9, weight="bold")
                ax.text(j, i+.24, "●" if pnl.iloc[i,j] >= 0 else "●", ha="center", va="center",
                        color="#36c998" if pnl.iloc[i,j] >= 0 else "#f06a73", fontsize=8)
    legend = [Line2D([0],[0], marker='o', color='w', label='Positive PnL', markerfacecolor='#36c998', markersize=8),
              Line2D([0],[0], marker='o', color='w', label='Negative PnL', markerfacecolor='#f06a73', markersize=8)]
    ax.legend(handles=legend, frameon=False, ncol=2, loc="upper right", bbox_to_anchor=(1, 1.12))
    fig.text(.01, .02, "Best for: seeing clustered expiries and rollover/refinancing pressure by currency pair.", fontsize=9, color="#647487")
    fig.tight_layout(rect=[0, .04, 1, .96])
    fig.savefig(OUT / "option_2_maturity_heatmap.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def position_table(df):
    base_style()
    show = df.sort_values(["DTE", "Notional"], ascending=[True, False]).copy()
    show["Position"] = show.Pair + "  " + show.OptionType.str.upper()
    show["StrikeFmt"] = show.Strike.map(lambda x: f"{x:,.4f}".rstrip("0").rstrip("."))
    show["ExpiryFmt"] = show.ExpiryDate.dt.strftime("%d %b %Y")
    show["DTEFmt"] = show.DTE.map(lambda x: f"{x}d")
    show["NotionalFmt"] = show.Notional.map(money)
    show["DeltaFmt"] = show.Delta.map(lambda x: f"{x/1000:+.1f}k")
    show["GammaFmt"] = show.Gamma.map(lambda x: f"{x/1000:.1f}k")
    show["PnLFmt"] = show.PnL.map(lambda x: ("+" if x >= 0 else "") + money(x))
    cols = ["Position", "Shore", "StrikeFmt", "ExpiryFmt", "DTEFmt", "NotionalFmt", "DeltaFmt", "GammaFmt", "PnLFmt"]
    labels = ["POSITION", "SHORE", "STRIKE", "EXPIRY", "DTE", "NOTIONAL", "DELTA", "GAMMA", "PNL"]
    fig, ax = plt.subplots(figsize=(16, 10)); ax.axis("off")
    ax.text(0, 1.045, "FX Options — Position Blotter", transform=ax.transAxes, fontsize=21, weight="bold")
    ax.text(0, 1.012, "Sorted by next action date  •  Illustrative data  •  As of 9 Sep 2026", transform=ax.transAxes, fontsize=9.5, color="#6c7a89")
    table = ax.table(cellText=show[cols].values, colLabels=labels, loc="upper left", cellLoc="left", colLoc="left",
                     colWidths=[.145,.09,.075,.105,.05,.095,.075,.075,.085], bbox=[0, .05, 1, .93])
    table.auto_set_font_size(False); table.set_fontsize(8.6); table.scale(1, 1.65)
    for (r,c), cell in table.get_celld().items():
        cell.set_edgecolor("#e1e7ee"); cell.set_linewidth(.5)
        if r == 0:
            cell.set_facecolor("#173151"); cell.get_text().set_color("white"); cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("white" if r % 2 else "#f7f9fc")
            if c == 0:
                cell.get_text().set_weight("bold")
                cell.get_text().set_color("#2463eb" if "CALL" in cell.get_text().get_text() else "#8550ba")
            if c == 4 and show.iloc[r-1].DTE <= 30:
                cell.set_facecolor("#fff1dc"); cell.get_text().set_color("#b85d0d"); cell.get_text().set_weight("bold")
            if c == 8:
                cell.get_text().set_color("#138465" if show.iloc[r-1].PnL >= 0 else "#ce3f4b")
                cell.get_text().set_weight("bold")
    ax.text(0, .012, "Amber DTE = expires within 30 days. Use this as the drill-down beneath either visual summary.", transform=ax.transAxes, fontsize=8.5, color="#6c7a89")
    fig.savefig(OUT / "option_3_position_blotter.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    data = sample_positions()
    data.drop(columns=["Pair", "ExpiryMonth", "DTE"]).to_csv(OUT / "sample_fx_option_positions.csv", index=False, date_format="%Y-%m-%d")
    overview(data)
    maturity_map(data)
    position_table(data)
    print("Created 3 mockups and sample_fx_option_positions.csv")
