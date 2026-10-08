# Strategy MtM P&L dashboard

Generate a self-contained static HTML dashboard from a CSV containing:

```text
CobDate,Strategy,Ticker,MtM_PnL
```

The file may include that header or be headerless in the same column order.

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

The strategy table and ticker-detail table are sortable. Use the Strategy and Ticker selectors, or click a table row or composition bar, to view an exact strategy/ticker combination. With `Strategy` set to `Whole book`, selecting a ticker aggregates its daily and cumulative P&L across all strategies.
