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

- `Current MtM` is the summed MtM level on the latest available `CobDate`.
- `Day change` compares with the previous available snapshot.
- `1 week` compares with the latest snapshot on or before seven calendar days earlier.
- `MTD` and `YTD` compare with the last snapshot before the period; if none exists, they use the first snapshot inside the period.
- Repeated rows for the same `CobDate` / `Strategy` / `Ticker` are summed.
- Blank or null `MtM_PnL` values are treated as zero.

The strategy table and ticker-detail table are sortable. Click a strategy, ticker, or composition bar to drill into its P&L history.
