# Strategy MtM P&L dashboard

Generate a self-contained static HTML dashboard from a CSV containing:

```text
CobDate,Strategy,Ticker,MtM_PnL,PS1,CCY1,Amount1,ValueDT
```

The file may include that header or be headerless in the same column order. The
earlier four-column and seven-column formats remain supported, but they cannot
display an expiry distribution without `ValueDT`.

## Run

From this folder:

```bash
python3 generate_dashboard.py /path/to/your_file.csv -o index.html
```

Open `index.html` in a browser. The generated file has no server or internet dependency.

Edit `MACRO_1_STRATEGIES` near the top of `generate_dashboard.py` to maintain
the hard-coded Macro 1 Strategy names. Matching is exact and case-sensitive;
every other Strategy is assigned to Macro 2.

## Dashboard behavior

- `MtM_PnL` is treated as daily P&L.
- The chart shows daily P&L as positive/negative bars and its running cumulative sum as a blue curve.
- `Latest` is the summed daily P&L on the latest available `CobDate`.
- `1W`, `MTD`, and `YTD` are sums of daily P&L inside their respective periods.
- `Cumulative` is the sum of all available daily P&L in the input file.
- Repeated rows for the same `CobDate` / `Strategy` / `Ticker` are summed.
- Blank or null `MtM_PnL` values are treated as zero.
- The drill-down hierarchy is Whole book → Macro group → Strategy → Ticker.
- Whole book summarizes Macro 1 versus Macro 2. Selecting a Macro group filters
  all charts, tables, positions, and expiry distributions to its Strategies.
- `PS1` must be `Buy` or `Sell`; `Amount1` must be non-negative.
- Latest positions are grouped by `Ticker`. `CCY1` is displayed only as the
  currency unit of `Amount1`.
- Net position is calculated as gross Buy `Amount1` minus gross Sell `Amount1`.
- `ValueDT` is the position expiry date. After selecting a Ticker, the expiry
  chart plots its latest-date net `Amount1`, aggregated by calendar month.
- At Whole-book level, the expiry chart aggregates the selected Ticker across
  strategies. Macro group and Strategy selections progressively narrow it.
- Hovering an expiry bar shows gross Buy, gross Sell, net position, and the
  contributing strategies. Synthetic Tickers combine their underlying legs.

The summary and Ticker-detail tables are sortable. Use the Macro group,
Strategy, and Ticker selectors—or click a table row or composition bar—to move
through the hierarchy. Selecting a Ticker at Whole-book or Macro-group level
aggregates its daily and cumulative P&L across the Strategies in that scope.

Three view-only synthetic Tickers can be calculated:

- `BRLBRF = USD/BRL + USD/BRF`
- `CNHCNY = USD/CNH + USD/CNY`
- `KRWKRO = USD/KRW + USD/KRO`

Synthetic tickers are created only when both required legs exist in the current
book, Macro group, or Strategy scope. They are excluded from whole-book, Macro,
Strategy totals, and actual-pair counts to prevent double-counting. They
are displayed alongside their underlying legs in a selected Strategy's latest
P&L-by-Ticker bars, so those displayed bars should not be summed together.
Within a Strategy, a synthetic Ticker is created only when both underlying legs
are present. Selecting both a Strategy and Ticker reduces the latest P&L bar
section to that one selected Ticker.
When selected in the position breakdown, a synthetic ticker displays its two
underlying ticker legs separately.
