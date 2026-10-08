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

## Dashboard behavior

- `MtM_PnL` is treated as daily P&L.
- The chart shows daily P&L as positive/negative bars and its running cumulative sum as a blue curve.
- `Latest` is the summed daily P&L on the latest available `CobDate`.
- `1W`, `MTD`, and `YTD` are sums of daily P&L inside their respective periods.
- `Cumulative` is the sum of all available daily P&L in the input file.
- Repeated rows for the same `CobDate` / `Strategy` / `Ticker` are summed.
- Blank or null `MtM_PnL` values are treated as zero.
- `PS1` must be `Buy` or `Sell`; `Amount1` must be non-negative.
- Latest positions are grouped by `Ticker`. `CCY1` is displayed only as the
  currency unit of `Amount1`.
- Net position is calculated as gross Buy `Amount1` minus gross Sell `Amount1`.
- `ValueDT` is the position expiry date. After selecting a Ticker, the expiry
  chart plots its latest-date net `Amount1`, aggregated by calendar month.
- At Whole-book level, the expiry chart aggregates the selected Ticker across
  strategies. Selecting both a Strategy and Ticker filters it to that Strategy.
- Hovering an expiry bar shows gross Buy, gross Sell, net position, and the
  contributing strategies. Synthetic Tickers combine their underlying legs.

The strategy table and ticker-detail table are sortable. Use the Strategy and Ticker selectors, or click a table row or composition bar, to view an exact strategy/ticker combination. With `Strategy` set to `Whole book`, selecting a ticker aggregates its daily and cumulative P&L across all strategies.

Three view-only synthetic tickers are calculated for every date and strategy:

- `BRLBRF = USD/BRL + USD/BRF`
- `CNHCNY = USD/CNH + USD/CNY`
- `KRWKRO = USD/KRW + USD/KRO`

A missing leg contributes zero. Synthetic tickers are excluded from whole-book
totals, strategy totals, and actual-pair counts to prevent double-counting. They
are displayed alongside their underlying legs in a selected Strategy's latest
P&L-by-Ticker bars, so those displayed bars should not be summed together.
When selected in the position breakdown, a synthetic ticker displays its two
underlying ticker legs separately.
