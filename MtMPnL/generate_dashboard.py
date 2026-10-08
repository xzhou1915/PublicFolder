#!/usr/bin/env python3
"""Generate a self-contained Strategy MtM P&L dashboard from a CSV file."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


CORE_COLUMNS = ("CobDate", "Strategy", "Ticker", "MtM_PnL")
POSITION_COLUMNS = ("PS1", "CCY1", "Amount1")
VALUE_DATE_COLUMN = "ValueDT"


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def parse_named_date(value: str, line_number: int, field_name: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError(f"line {line_number}: {field_name} is blank")

    iso_candidate = raw[:10]
    try:
        return datetime.fromisoformat(iso_candidate).date().isoformat()
    except ValueError:
        pass

    for fmt in ("%Y%m%d", "%Y/%m/%d", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(
        f"line {line_number}: unsupported {field_name} {value!r}; "
        "use YYYY-MM-DD"
    )


def parse_date(value: str, line_number: int) -> str:
    return parse_named_date(value, line_number, "CobDate")


def parse_pnl(value: str, line_number: int) -> float:
    raw = value.strip()
    if not raw or raw.lower() in {"na", "n/a", "null", "none", "nan"}:
        return 0.0
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[$,\s]", "", raw.strip("()"))
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: invalid MtM_PnL {value!r}") from exc
    if not math.isfinite(number):
        return 0.0
    return -number if negative else number


def parse_position_amount(value: str, line_number: int) -> float:
    raw = value.strip()
    if not raw or raw.lower() in {"na", "n/a", "null", "none", "nan"}:
        raise ValueError(f"line {line_number}: Amount1 is blank")
    cleaned = re.sub(r"[$,\s]", "", raw)
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: invalid Amount1 {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"line {line_number}: Amount1 must be non-negative")
    return number


def read_csv(
    path: Path,
) -> tuple[
    list[list[object]],
    list[str],
    bool,
    int,
    list[list[object]],
    bool,
    bool,
]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("input CSV is empty")

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    raw_rows = [
        row
        for row in csv.reader(text.splitlines(), dialect)
        if any(x.strip() for x in row)
    ]
    if not raw_rows:
        raise ValueError("input CSV has no data rows")

    core_wanted = {normalized_header(name): name for name in CORE_COLUMNS}
    position_wanted = {
        normalized_header(name): name for name in POSITION_COLUMNS
    }
    value_date_header = normalized_header(VALUE_DATE_COLUMN)
    first = [normalized_header(cell) for cell in raw_rows[0]]
    has_header = all(name in first for name in core_wanted)

    if has_header:
        indexes = {
            core_wanted[name]: first.index(name) for name in core_wanted
        }
        position_presence = [name in first for name in position_wanted]
        if any(position_presence) and not all(position_presence):
            raise ValueError(
                "position columns must include PS1, CCY1, and Amount1 together"
            )
        has_positions = all(position_presence)
        has_value_dates = value_date_header in first
        if has_value_dates and not has_positions:
            raise ValueError(
                "ValueDT requires PS1, CCY1, and Amount1 position columns"
            )
        if has_positions:
            indexes.update(
                {
                    position_wanted[name]: first.index(name)
                    for name in position_wanted
                }
            )
        if has_value_dates:
            indexes[VALUE_DATE_COLUMN] = first.index(value_date_header)
        data_rows = raw_rows[1:]
        first_line = 2
    else:
        if 4 < len(raw_rows[0]) < 7:
            raise ValueError(
                "headerless input must contain either four columns or seven "
                "columns ending with PS1, CCY1, Amount1; ValueDT may be an "
                "eighth column"
            )
        has_positions = len(raw_rows[0]) >= 7
        has_value_dates = len(raw_rows[0]) >= 8
        indexes = {name: index for index, name in enumerate(CORE_COLUMNS)}
        if has_positions:
            indexes.update(
                {
                    name: len(CORE_COLUMNS) + index
                    for index, name in enumerate(POSITION_COLUMNS)
                }
            )
        if has_value_dates:
            indexes[VALUE_DATE_COLUMN] = 7
        data_rows = raw_rows
        first_line = 1

    aggregated: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    position_aggregated: defaultdict[
        tuple[str, str, str, str, str, str], float
    ] = defaultdict(float)
    source_rows = 0
    for offset, row in enumerate(data_rows):
        line_number = first_line + offset
        if len(row) < 4:
            raise ValueError(
                f"line {line_number}: expected four columns in the order "
                "CobDate, Strategy, Ticker, MtM_PnL"
            )
        try:
            cob_date = parse_date(row[indexes["CobDate"]], line_number)
            strategy = row[indexes["Strategy"]].strip()
            ticker = row[indexes["Ticker"]].strip()
            pnl = parse_pnl(row[indexes["MtM_PnL"]], line_number)
        except IndexError as exc:
            raise ValueError(f"line {line_number}: missing required column value") from exc
        if not strategy:
            raise ValueError(f"line {line_number}: Strategy is blank")
        if not ticker:
            raise ValueError(f"line {line_number}: Ticker is blank")
        aggregated[(cob_date, strategy, ticker)] += pnl
        if has_positions:
            try:
                side = row[indexes["PS1"]].strip().title()
                currency = row[indexes["CCY1"]].strip().upper()
                amount = parse_position_amount(
                    row[indexes["Amount1"]], line_number
                )
                value_date = (
                    parse_named_date(
                        row[indexes[VALUE_DATE_COLUMN]],
                        line_number,
                        VALUE_DATE_COLUMN,
                    )
                    if has_value_dates
                    else ""
                )
            except IndexError as exc:
                raise ValueError(
                    f"line {line_number}: missing PS1, CCY1, Amount1, or "
                    "ValueDT value"
                ) from exc
            if side not in {"Buy", "Sell"}:
                raise ValueError(
                    f"line {line_number}: PS1 must be Buy or Sell; found {side!r}"
                )
            if not currency:
                raise ValueError(f"line {line_number}: CCY1 is blank")
            position_aggregated[
                (cob_date, strategy, ticker, side, currency, value_date)
            ] += amount
        source_rows += 1

    rows = [
        [date, strategy, ticker, round(value, 6)]
        for (date, strategy, ticker), value in sorted(aggregated.items())
    ]
    dates = sorted({row[0] for row in rows})
    if not dates:
        raise ValueError("input CSV contains no valid data rows")
    position_rows = [
        [
            date,
            strategy,
            ticker,
            side,
            currency,
            round(value, 6),
            value_date or None,
        ]
        for (
            date,
            strategy,
            ticker,
            side,
            currency,
            value_date,
        ), value in sorted(position_aggregated.items())
        if date == dates[-1]
    ]
    return (
        rows,
        dates,
        has_header,
        source_rows,
        position_rows,
        has_positions,
        has_value_dates,
    )


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Strategy MtM P&amp;L</title>
  <style>
    :root {
      --bg:#f3f6fb; --panel:#fff; --line:#dfe6ef; --line2:#edf1f6;
      --text:#162033; --muted:#69758a; --blue:#2563eb; --blue-soft:#eaf1ff;
      --green:#07835a; --green-soft:#e7f7f0; --red:#c23b4b; --red-soft:#fff0f2;
      --shadow:0 8px 26px rgba(28,45,78,.07);
    }
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
    button,input,select{font:inherit}
    .shell{max-width:1580px;margin:0 auto;padding:24px}
    .top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}
    h1{font-size:26px;line-height:1.15;margin:0 0 7px;letter-spacing:-.02em}
    .subtitle{color:var(--muted);font-size:14px}
    .asof{text-align:right;color:var(--muted);font-size:13px;white-space:nowrap}
    .asof strong{display:block;color:var(--text);font-size:15px;margin-bottom:2px}
    .nav-row{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:0 0 14px}
    .crumbs{display:flex;align-items:center;gap:8px;min-height:36px;flex-wrap:wrap}
    .crumb{border:1px solid var(--line);background:#fff;color:var(--muted);padding:7px 11px;border-radius:8px;cursor:pointer}
    .crumb.active{border-color:#b8caf6;background:var(--blue-soft);color:var(--blue);font-weight:700}
    .chev{color:#a4adbb}
    .filters{display:flex;align-items:end;gap:10px}
    .filter-field{display:grid;gap:3px}
    .filter-field label{font-size:10px;color:var(--muted);font-weight:750;text-transform:uppercase;letter-spacing:.055em}
    .filter-field select{min-width:180px;border:1px solid var(--line);border-radius:8px;padding:7px 30px 7px 9px;background:#fff;color:var(--text);outline:none}
    .filter-field select:focus{border-color:#9bb5f5;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
    .filter-field select:disabled{background:#f1f4f8;color:#9ba5b4}
    .kpis{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px;margin-bottom:16px}
    .kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;box-shadow:var(--shadow)}
    .kpi-label{color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.055em;margin-bottom:7px}
    .kpi-value{font-size:25px;line-height:1.1;font-weight:760;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
    .kpi-note{font-size:11px;color:var(--muted);margin-top:7px}
    .positive{color:var(--green)!important}.negative{color:var(--red)!important}.neutral{color:var(--text)!important}
    .grid{display:grid;grid-template-columns:minmax(460px,.95fr) minmax(560px,1.35fr);gap:16px;align-items:start}
    .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);overflow:hidden}
    .panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border-bottom:1px solid var(--line2)}
    .panel-title{font-size:16px;font-weight:750}.panel-sub{font-size:12px;color:var(--muted);margin-top:2px}
    .search{width:180px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;color:var(--text);outline:none;background:#fbfcfe}
    .search:focus{border-color:#9bb5f5;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
    .table-wrap{overflow:auto;max-height:570px}
    table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
    th{position:sticky;top:0;z-index:2;background:#f8fafc;color:#617086;font-size:11px;text-transform:uppercase;letter-spacing:.035em;text-align:right;padding:10px 11px;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
    th:first-child{text-align:left}.sort-mark{display:inline-block;width:10px;color:#9aa5b4}
    td{padding:10px 11px;border-bottom:1px solid var(--line2);text-align:right;white-space:nowrap}
    td:first-child{text-align:left;font-weight:650;color:#263349;max-width:190px;overflow:hidden;text-overflow:ellipsis}
    tbody tr{cursor:pointer;transition:.12s background}
    tbody tr:hover{background:#f6f9ff}tbody tr.selected{background:var(--blue-soft)}
    .money{font-weight:680}.small{font-size:12px;color:var(--muted)}
    .tag{display:inline-block;margin-left:6px;padding:1px 5px;border-radius:999px;background:#eef3ff;color:#4869b2;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;vertical-align:1px}
    .chart-panel{min-height:626px}
    .chart-area{position:relative;padding:10px 16px 0;height:405px}
    #lineChart{display:block;width:100%;height:100%}
    .tooltip{position:absolute;display:none;pointer-events:none;background:#172033;color:#fff;border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 8px 20px rgba(0,0,0,.18);white-space:nowrap;z-index:5}
    .tooltip strong{display:block;font-size:14px;margin-top:2px}
    .bar-section{border-top:1px solid var(--line2);padding:14px 18px 18px}
    .bar-title{font-size:13px;font-weight:750;margin-bottom:11px}
    .bars{display:grid;gap:8px;max-height:155px;overflow:auto;padding-right:4px}
    .bar-row{display:grid;grid-template-columns:minmax(70px,125px) 1fr 88px;align-items:center;gap:10px;font-size:12px;cursor:pointer}
    .bar-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:650}
    .bar-track{position:relative;height:16px;background:#f0f3f8;border-radius:4px;overflow:hidden}
    .bar-zero{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#aab4c3;z-index:2}
    .bar{position:absolute;top:2px;height:12px;border-radius:3px;min-width:1px}
    .bar.pos{left:50%;background:#29a37a}.bar.neg{right:50%;background:#e05b68}
    .bar-value{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
    .detail{margin-top:16px}
    .detail .table-wrap{max-height:420px}
    .position-detail th{cursor:default}.position-detail td:first-child{max-width:none}
    .position-detail td.num{font-size:15px;font-weight:700}
    .expiry-chart-area{position:relative;height:330px;overflow-x:auto;overflow-y:hidden;padding:12px 16px 8px}
    #expiryChart{display:none;height:100%}
    .expiry-empty{height:100%;display:flex;align-items:center;justify-content:center;color:var(--muted);text-align:center;padding:28px}
    .expiry-tooltip{white-space:normal;min-width:190px;max-width:310px}
    .expiry-tooltip .contributor{display:flex;justify-content:space-between;gap:16px;margin-top:3px}
    .expiry-tooltip .contributor-label{max-width:190px;overflow:hidden;text-overflow:ellipsis}
    .empty{padding:32px;text-align:center;color:var(--muted)}
    .footer{color:var(--muted);font-size:11px;margin-top:12px;text-align:right}
    @media(max-width:1050px){.grid{grid-template-columns:1fr}.chart-panel{min-height:580px}.kpis{grid-template-columns:repeat(3,1fr)}}
    @media(max-width:780px){.nav-row{display:block}.filters{margin-top:10px}.filter-field{flex:1}.filter-field select{width:100%;min-width:0}}
    @media(max-width:680px){.shell{padding:14px}.top{display:block}.asof{text-align:left;margin-top:10px}.kpis{grid-template-columns:repeat(2,1fr)}.grid{display:block}.panel{margin-bottom:14px}.search{width:145px}.kpi-value{font-size:21px}.chart-area{height:330px}}
  </style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div><h1>Strategy MtM P&amp;L</h1><div class="subtitle">Daily and cumulative performance by strategy and currency pair</div></div>
    <div class="asof"><strong id="asOf"></strong><span id="sourceMeta"></span></div>
  </div>

  <div class="nav-row">
    <div class="crumbs" id="crumbs"></div>
    <div class="filters">
      <div class="filter-field"><label for="strategySelect">Strategy</label><select id="strategySelect"></select></div>
      <div class="filter-field"><label for="tickerSelect">Ticker</label><select id="tickerSelect" disabled></select></div>
    </div>
  </div>
  <section class="kpis" id="kpis"></section>

  <section class="grid">
    <div class="panel">
      <div class="panel-head">
        <div><div class="panel-title">Strategies</div><div class="panel-sub" id="strategyCount"></div></div>
        <input class="search" id="strategySearch" placeholder="Search strategy" aria-label="Search strategy">
      </div>
      <div class="table-wrap">
        <table id="strategyTable">
          <thead><tr>
            <th data-key="name">Strategy <span class="sort-mark"></span></th>
            <th data-key="latest"><span class="latest-date-label">__LATEST_DATE__</span> <span class="sort-mark"></span></th>
            <th data-key="w1">1W P&amp;L <span class="sort-mark"></span></th>
            <th data-key="mtd">MTD P&amp;L <span class="sort-mark"></span></th>
            <th data-key="ytd">YTD P&amp;L <span class="sort-mark"></span></th>
            <th data-key="cumulative">Cumulative P&amp;L <span class="sort-mark"></span></th>
            <th data-key="tickers">Pairs <span class="sort-mark"></span></th>
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="panel chart-panel">
      <div class="panel-head"><div><div class="panel-title" id="chartTitle"></div><div class="panel-sub" id="chartSub"></div></div></div>
      <div class="chart-area" id="chartArea"><svg id="lineChart" role="img"></svg><div class="tooltip" id="tooltip"></div></div>
      <div class="bar-section"><div class="bar-title" id="barTitle"></div><div class="bars" id="bars"></div></div>
    </div>
  </section>

  <section class="panel detail position-detail">
    <div class="panel-head"><div><div class="panel-title" id="positionTitle">Latest position breakdown</div><div class="panel-sub" id="positionSub"></div></div></div>
    <div class="table-wrap">
      <table id="positionTable">
        <thead><tr>
          <th>Ticker</th>
          <th>Strategy</th>
          <th>CCY1</th>
          <th>Gross Buy</th>
          <th>Gross Sell</th>
          <th>Net Position</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>
  <section class="panel detail expiry-detail">
    <div class="panel-head"><div><div class="panel-title" id="expiryTitle">Expiry distribution</div><div class="panel-sub" id="expirySub"></div></div></div>
    <div class="expiry-chart-area" id="expiryChartArea">
      <div class="expiry-empty" id="expiryEmpty">Select a Ticker to view its expiry distribution.</div>
      <svg id="expiryChart" role="img"></svg>
      <div class="tooltip expiry-tooltip" id="expiryTooltip"></div>
    </div>
  </section>
  <section class="panel detail">
    <div class="panel-head"><div><div class="panel-title" id="detailTitle">Currency-pair detail</div><div class="panel-sub" id="detailSub"></div></div></div>
    <div class="table-wrap" id="detailWrap">
      <table id="tickerTable">
        <thead><tr>
          <th data-key="name">Ticker <span class="sort-mark"></span></th>
          <th data-key="latest"><span class="latest-date-label">__LATEST_DATE__</span> <span class="sort-mark"></span></th>
          <th data-key="w1">1W P&amp;L <span class="sort-mark"></span></th>
          <th data-key="mtd">MTD P&amp;L <span class="sort-mark"></span></th>
          <th data-key="ytd">YTD P&amp;L <span class="sort-mark"></span></th>
          <th data-key="cumulative">Cumulative P&amp;L <span class="sort-mark"></span></th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>
  <div class="footer" id="footer"></div>
</main>

<script>
const PAYLOAD = __PAYLOAD__;
const dates = PAYLOAD.dates;
const positionRows = PAYLOAD.positions || [];
const strategies = [...new Set(PAYLOAD.rows.map(r => r[1]))].sort((a,b)=>a.localeCompare(b));
const dateIndex = new Map(dates.map((d,i)=>[d,i]));
const zeroSeries = () => Array(dates.length).fill(0);
const book = zeroSeries();
const byStrategy = new Map();
const byTicker = new Map();
const byStrategyTicker = new Map();
const tickersByStrategy = new Map();
const allTickers = new Set();
const syntheticDefinitions = new Map([
  ['BRLBRF',['USD/BRL','USD/BRF']],
  ['CNHCNY',['USD/CNH','USD/CNY']],
  ['KRWKRO',['USD/KRW','USD/KRO']]
]);
const syntheticNames = new Set();

for (const [date,strategy,ticker,value] of PAYLOAD.rows) {
  if (syntheticDefinitions.has(ticker)) continue;
  const i = dateIndex.get(date);
  book[i] += value;
  if (!byStrategy.has(strategy)) byStrategy.set(strategy, zeroSeries());
  byStrategy.get(strategy)[i] += value;
  if (!byTicker.has(ticker)) byTicker.set(ticker, zeroSeries());
  byTicker.get(ticker)[i] += value;
  const key = strategy + '\u0000' + ticker;
  if (!byStrategyTicker.has(key)) byStrategyTicker.set(key, zeroSeries());
  byStrategyTicker.get(key)[i] += value;
  if (!tickersByStrategy.has(strategy)) tickersByStrategy.set(strategy, new Set());
  tickersByStrategy.get(strategy).add(ticker);
  allTickers.add(ticker);
}

const addSeries = seriesList => dates.map((_,i)=>seriesList.reduce((sum,series)=>sum+(series?.[i]||0),0));
for (const [synthetic,legs] of syntheticDefinitions) {
  const bookLegs=legs.filter(leg=>byTicker.has(leg)).map(leg=>byTicker.get(leg));
  if (!bookLegs.length) continue;
  byTicker.set(synthetic,addSeries(bookLegs));
  allTickers.add(synthetic);
  syntheticNames.add(synthetic);
  for (const strategy of strategies) {
    const strategyLegs=legs.map(leg=>byStrategyTicker.get(strategy+'\u0000'+leg)).filter(Boolean);
    if (!strategyLegs.length) continue;
    byStrategyTicker.set(strategy+'\u0000'+synthetic,addSeries(strategyLegs));
    tickersByStrategy.get(strategy)?.add(synthetic);
  }
}

const state = {strategy:null, ticker:null, strategySort:{key:'latest',dir:-1}, tickerSort:{key:'latest',dir:-1}, search:''};
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const signClass = v => v == null || Math.abs(v) < 0.000001 ? 'neutral' : v > 0 ? 'positive' : 'negative';
function fmt(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a=Math.abs(v), sign=v<0?'−':'';
  if (a>=1e9) return sign+'$'+(a/1e9).toFixed(a>=10e9?1:2)+'bn';
  if (a>=1e6) return sign+'$'+(a/1e6).toFixed(a>=10e6?1:2)+'m';
  if (a>=1e3) return sign+'$'+Math.round(a/1e3).toLocaleString()+'k';
  return sign+'$'+Math.round(a).toLocaleString();
}
const exact = v => (v<0?'−':'')+'$'+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});
function fmtPosition(v,signed=true) {
  const a=Math.abs(v),sign=v<0?'−':signed&&v>0?'+':'';
  if(a>=1e9)return sign+(a/1e9).toFixed(a>=10e9?1:2)+'bn';
  if(a>=1e6)return sign+(a/1e6).toFixed(a>=10e6?1:2)+'m';
  if(a>=1e3)return sign+Math.round(a/1e3).toLocaleString()+'k';
  return sign+Math.round(a).toLocaleString();
}
function periodStartIndex(kind) {
  const last = new Date(dates.at(-1)+'T00:00:00Z');
  let cutoff=last;
  if (kind==='w1') cutoff = new Date(last.getTime()-6*86400000);
  if (kind==='mtd') cutoff = new Date(Date.UTC(last.getUTCFullYear(),last.getUTCMonth(),1));
  if (kind==='ytd') cutoff = new Date(Date.UTC(last.getUTCFullYear(),0,1));
  const target=cutoff.toISOString().slice(0,10);
  const idx=dates.findIndex(d=>d>=target);
  return idx>=0?idx:dates.length-1;
}
const starts={w1:periodStartIndex('w1'),mtd:periodStartIndex('mtd'),ytd:periodStartIndex('ytd')};
function metrics(series) {
  const sumFrom=i=>series.slice(i).reduce((a,b)=>a+b,0);
  return {latest:series.at(-1),w1:sumFrom(starts.w1),mtd:sumFrom(starts.mtd),ytd:sumFrom(starts.ytd),cumulative:sumFrom(0)};
}
function activeSeries() {
  if (!state.strategy) return state.ticker ? byTicker.get(state.ticker) || zeroSeries() : book;
  if (!state.ticker) return byStrategy.get(state.strategy) || zeroSeries();
  return byStrategyTicker.get(state.strategy+'\u0000'+state.ticker) || zeroSeries();
}
function activeLabel() { return state.ticker ? `${state.strategy||'All strategies'} / ${state.ticker}` : state.strategy || 'Whole book'; }
function metricCell(v){return `<td class="money ${signClass(v)}">${fmt(v)}</td>`}

function renderCrumbs(){
  const parts=[`<button class="crumb ${!state.strategy&&!state.ticker?'active':''}" data-level="book">Whole book</button>`];
  if(state.strategy){parts.push('<span class="chev">›</span>',`<button class="crumb ${!state.ticker?'active':''}" data-level="strategy">${esc(state.strategy)}</button>`);}
  if(state.ticker){parts.push('<span class="chev">›</span>',`<button class="crumb active" data-level="ticker">${esc(state.ticker)}</button>`);}
  const el=document.getElementById('crumbs');el.innerHTML=parts.join('');
  el.querySelectorAll('button').forEach(b=>b.onclick=()=>{if(b.dataset.level==='book'){state.strategy=null;state.ticker=null;}if(b.dataset.level==='strategy')state.ticker=null;render();});
}
function renderSelectors(){
  const strategySelect=document.getElementById('strategySelect');
  strategySelect.innerHTML='<option value="">Whole book</option>'+strategies.map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
  strategySelect.value=state.strategy||'';
  const tickerSelect=document.getElementById('tickerSelect');
  tickerSelect.disabled=false;
  const tickers=[...(state.strategy?tickersByStrategy.get(state.strategy)||[]:allTickers)].sort((a,b)=>a.localeCompare(b));
  const allLabel=state.strategy?'All tickers':'All tickers across strategies';
  tickerSelect.innerHTML=`<option value="">${allLabel}</option>`+tickers.map(name=>`<option value="${esc(name)}">${esc(name)}${syntheticNames.has(name)?' · synthetic':''}</option>`).join('');
  tickerSelect.value=state.ticker||'';
}
function renderKpis(){
  const m=metrics(activeSeries());
  const items=[['Latest daily P&L',m.latest,dates.at(-1)],['1 week P&L',m.w1,`from ${dates[starts.w1]}`],['MTD P&L',m.mtd,`from ${dates[starts.mtd]}`],['YTD P&L',m.ytd,`from ${dates[starts.ytd]}`],['Cumulative P&L',m.cumulative,`from ${dates[0]}`]];
  document.getElementById('kpis').innerHTML=items.map(([label,v,note])=>`<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value ${signClass(v)}">${fmt(v)}</div><div class="kpi-note">${note}</div></div>`).join('');
}
function strategyRows(){
  return strategies.map(name=>{const m=metrics(byStrategy.get(name)||zeroSeries());const tickers=[...(tickersByStrategy.get(name)||[])].filter(ticker=>!syntheticNames.has(ticker)).length;return {...m,name,tickers};});
}
function compareRows(a,b,sort){
  const av=a[sort.key],bv=b[sort.key];
  if(typeof av==='string')return sort.dir*av.localeCompare(bv);
  const aa=av==null?-Infinity:av,bb=bv==null?-Infinity:bv;
  return sort.dir*(aa-bb);
}
function updateSortMarks(tableId,sort){
  document.querySelectorAll(`#${tableId} th`).forEach(th=>{const s=th.querySelector('.sort-mark');if(s)s.textContent=th.dataset.key===sort.key?(sort.dir===1?'▲':'▼'):'';});
}
function renderStrategies(){
  const query=state.search.toLowerCase();
  const rows=strategyRows().filter(r=>r.name.toLowerCase().includes(query)).sort((a,b)=>compareRows(a,b,state.strategySort));
  document.querySelector('#strategyTable tbody').innerHTML=rows.map(r=>`<tr data-name="${esc(r.name)}" class="${state.strategy===r.name?'selected':''}"><td title="${esc(r.name)}">${esc(r.name)}</td>${metricCell(r.latest)}${metricCell(r.w1)}${metricCell(r.mtd)}${metricCell(r.ytd)}${metricCell(r.cumulative)}<td>${r.tickers}</td></tr>`).join('');
  document.querySelectorAll('#strategyTable tbody tr').forEach(tr=>tr.onclick=()=>{state.strategy=tr.dataset.name;state.ticker=null;render();});
  document.getElementById('strategyCount').textContent=`${rows.length} of ${strategies.length} strategies · click a row to drill down`;
  updateSortMarks('strategyTable',state.strategySort);
}
function tickerRows(){
  const tickers=state.strategy?[...(tickersByStrategy.get(state.strategy)||[])]:[...allTickers];
  return tickers.map(name=>{const series=state.strategy?byStrategyTicker.get(state.strategy+'\u0000'+name):byTicker.get(name);const m=metrics(series||zeroSeries());return {...m,name,synthetic:syntheticNames.has(name)};}).sort((a,b)=>compareRows(a,b,state.tickerSort));
}
function renderTickers(){
  const body=document.querySelector('#tickerTable tbody');
  const rows=tickerRows();
  document.getElementById('detailTitle').textContent=state.strategy?`${state.strategy} · currency-pair detail`:'All strategies · currency-pair detail';
  document.getElementById('detailSub').textContent=`${rows.length} ticker${rows.length===1?'':'s'} · click a row to isolate ${state.strategy?'its':'cross-strategy'} history`;
  body.innerHTML=rows.map(r=>`<tr data-name="${esc(r.name)}" class="${state.ticker===r.name?'selected':''}"><td>${esc(r.name)}${r.synthetic?'<span class="tag">Synthetic</span>':''}</td>${metricCell(r.latest)}${metricCell(r.w1)}${metricCell(r.mtd)}${metricCell(r.ytd)}${metricCell(r.cumulative)}</tr>`).join('');
  body.querySelectorAll('tr').forEach(tr=>tr.onclick=()=>{state.ticker=tr.dataset.name;render();});
  updateSortMarks('tickerTable',state.tickerSort);
}
function renderPositions(){
  const body=document.querySelector('#positionTable tbody');
  const title=document.getElementById('positionTitle'),sub=document.getElementById('positionSub');
  title.textContent=state.strategy||state.ticker?`${activeLabel()} · latest position breakdown`:'Latest position breakdown';
  sub.textContent=`As of ${dates.at(-1)} · grouped by Ticker; CCY1 is the Amount1 unit`;
  if(!PAYLOAD.positionColumns){body.innerHTML='<tr><td colspan="6" class="empty">PS1, CCY1, and Amount1 are not present in this input file.</td></tr>';return;}
  if(!state.strategy&&!state.ticker){body.innerHTML='<tr><td colspan="6" class="empty">Select a Strategy or Ticker to inspect its latest position.</td></tr>';return;}
  const selectedTickers=state.ticker?(syntheticNames.has(state.ticker)?new Set(syntheticDefinitions.get(state.ticker)):new Set([state.ticker])):null;
  const grouped=new Map();
  for(const [,strategy,ticker,side,currency,amount] of positionRows){
    if(state.strategy&&strategy!==state.strategy)continue;
    if(selectedTickers&&!selectedTickers.has(ticker))continue;
    const key=strategy+'\u0000'+ticker+'\u0000'+currency;
    if(!grouped.has(key))grouped.set(key,{strategy,ticker,currency,buy:0,sell:0});
    grouped.get(key)[side.toLowerCase()]+=amount;
  }
  const rows=[...grouped.values()].map(row=>({...row,net:row.buy-row.sell})).sort((a,b)=>a.ticker.localeCompare(b.ticker)||a.strategy.localeCompare(b.strategy)||a.currency.localeCompare(b.currency));
  body.innerHTML=rows.map(row=>`<tr><td>${esc(row.ticker)}</td><td>${esc(row.strategy)}</td><td>${esc(row.currency)}</td><td class="num positive">${fmtPosition(row.buy,false)}</td><td class="num negative">${fmtPosition(row.sell,false)}</td><td class="num ${signClass(row.net)}">${fmtPosition(row.net)}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">No latest-date positions match this selection.</td></tr>';
}
function renderExpiryDistribution(){
  const area=document.getElementById('expiryChartArea'),svg=document.getElementById('expiryChart'),empty=document.getElementById('expiryEmpty'),tip=document.getElementById('expiryTooltip');
  const title=document.getElementById('expiryTitle'),sub=document.getElementById('expirySub');
  title.textContent=state.ticker?`${state.strategy||'Whole book'} / ${state.ticker} · expiry distribution`:'Expiry distribution';
  tip.style.display='none';
  const showMessage=message=>{svg.style.display='none';empty.style.display='flex';empty.textContent=message;sub.textContent=`As of ${dates.at(-1)}`;};
  if(!PAYLOAD.valueDateColumn){showMessage('ValueDT is not present in this input file.');return;}
  if(!state.ticker){showMessage('Select a Ticker to view its expiry distribution.');return;}
  const selectedTickers=syntheticNames.has(state.ticker)?new Set(syntheticDefinitions.get(state.ticker)):new Set([state.ticker]);
  const filtered=positionRows.filter(([,strategy,ticker,,,,valueDate])=>(!state.strategy||strategy===state.strategy)&&selectedTickers.has(ticker)&&valueDate);
  if(!filtered.length){showMessage('No latest-date positions with ValueDT match this selection.');return;}
  const currencies=[...new Set(filtered.map(row=>row[4]))];
  if(currencies.length!==1){showMessage(`Cannot aggregate this Ticker because it has multiple CCY1 units: ${currencies.join(', ')}.`);return;}
  const currency=currencies[0],grouped=new Map();
  for(const [,strategy,ticker,side,,amount,valueDate] of filtered){
    const expiryMonth=valueDate.slice(0,7);
    if(!grouped.has(expiryMonth))grouped.set(expiryMonth,{month:expiryMonth,buy:0,sell:0,contributors:new Map()});
    const row=grouped.get(expiryMonth),sideKey=side.toLowerCase();
    row[sideKey]+=amount;
    const contributorKey=ticker+'\u0000'+strategy;
    if(!row.contributors.has(contributorKey))row.contributors.set(contributorKey,{ticker,strategy,buy:0,sell:0});
    row.contributors.get(contributorKey)[sideKey]+=amount;
  }
  const data=[...grouped.values()].map(row=>({...row,net:row.buy-row.sell})).sort((a,b)=>a.month.localeCompare(b.month));
  empty.style.display='none';svg.style.display='block';
  const syntheticNote=syntheticNames.has(state.ticker)?' · underlying legs combined':'';
  sub.textContent=`As of ${dates.at(-1)} · net Amount1 (Buy − Sell) by ValueDT month in ${currency}${syntheticNote} · hover for contributors`;
  const pad={l:86,r:30,t:35,b:58},h=Math.max(285,area.clientHeight-20),w=Math.max(560,area.clientWidth-32,data.length*110+pad.l+pad.r);
  svg.style.width=w+'px';svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
  const plotHeight=h-pad.t-pad.b,plotWidth=w-pad.l-pad.r,maxAbs=Math.max(1,...data.map(row=>Math.abs(row.net)))*1.12;
  const y=value=>pad.t+(maxAbs-value)/(maxAbs*2)*plotHeight;
  const slot=plotWidth/data.length,x=index=>pad.l+(index+.5)*slot,zeroY=y(0),barWidth=Math.min(54,slot*.58),parts=[];
  parts.push(`<text x="${pad.l}" y="17" fill="#65738a" font-size="11" font-weight="700">NET POSITION (${esc(currency)})</text>`);
  for(let index=0;index<5;index++){
    const value=maxAbs-index*(maxAbs*2)/4,yy=pad.t+index*plotHeight/4;
    parts.push(`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="${index===2?'#9aa5b4':'#e8edf4'}" stroke-width="${index===2?'1.3':'1'}"/><text x="${pad.l-10}" y="${yy+4}" text-anchor="end" fill="#748096" font-size="11">${fmtPosition(value)}</text>`);
  }
  data.forEach((row,index)=>{
    const yy=y(row.net),top=Math.min(yy,zeroY),height=Math.max(2,Math.abs(yy-zeroY)),fill=row.net>0?'#29a37a':row.net<0?'#e05b68':'#9aa5b4';
    parts.push(`<rect x="${x(index)-barWidth/2}" y="${row.net===0?zeroY-1:top}" width="${barWidth}" height="${height}" rx="3" fill="${fill}" opacity=".9"/>`,`<text x="${x(index)}" y="${h-24}" text-anchor="middle" fill="#65738a" font-size="11">${row.month}</text>`,`<rect class="expiry-hit" data-index="${index}" x="${pad.l+index*slot}" y="${pad.t}" width="${slot}" height="${plotHeight}" fill="transparent"/>`);
  });
  svg.innerHTML=parts.join('');svg.setAttribute('aria-label',`${state.strategy||'Whole book'} / ${state.ticker} net position by expiry month`);
  const exactPosition=(value,signed=true)=>`${value<0?'−':signed&&value>0?'+':''}${Math.abs(value).toLocaleString(undefined,{maximumFractionDigits:0})} ${currency}`;
  svg.querySelectorAll('.expiry-hit').forEach(hit=>{
    hit.onmousemove=event=>{
      const row=data[Number(hit.dataset.index)];
      const contributors=[...row.contributors.values()].map(item=>({...item,net:item.buy-item.sell})).sort((a,b)=>Math.abs(b.net)-Math.abs(a.net));
      const contributorHtml=contributors.map(item=>{const label=syntheticNames.has(state.ticker)?`${item.ticker} · ${item.strategy}`:item.strategy;return `<div class="contributor"><span class="contributor-label" title="${esc(label)}">${esc(label)}</span><b class="${signClass(item.net)}">${exactPosition(item.net)}</b></div>`;}).join('');
      tip.innerHTML=`<strong>${row.month}</strong><div>Gross Buy: <b>${exactPosition(row.buy,false)}</b></div><div>Gross Sell: <b>${exactPosition(row.sell,false)}</b></div><div>Net: <b class="${signClass(row.net)}">${exactPosition(row.net)}</b></div><div class="small" style="margin-top:7px">Contributors</div>${contributorHtml}`;
      tip.style.display='block';
      const rect=area.getBoundingClientRect();let left=event.clientX-rect.left+area.scrollLeft+14;
      if(left+315>area.scrollLeft+area.clientWidth)left-=330;
      tip.style.left=Math.max(area.scrollLeft+4,left)+'px';tip.style.top=Math.max(8,event.clientY-rect.top-65)+'px';
    };
    hit.onmouseleave=()=>tip.style.display='none';
  });
}
function renderBars(){
  let rows;
  if(state.strategy&&state.ticker&&syntheticNames.has(state.ticker)){rows=syntheticDefinitions.get(state.ticker).map(name=>({name,value:metrics(byStrategyTicker.get(state.strategy+'\u0000'+name)||zeroSeries()).latest,type:'ticker'}));}
  else if(state.strategy){rows=tickerRows().filter(r=>!r.synthetic).map(r=>({name:r.name,value:r.latest,type:'ticker'}));}
  else if(state.ticker){rows=strategies.filter(name=>tickersByStrategy.get(name)?.has(state.ticker)).map(name=>({name,value:metrics(byStrategyTicker.get(name+'\u0000'+state.ticker)).latest,type:'strategyTicker'}));}
  else{rows=strategyRows().map(r=>({name:r.name,value:r.latest,type:'strategy'}));}
  rows.sort((a,b)=>Math.abs(b.value)-Math.abs(a.value));
  const max=Math.max(1,...rows.map(r=>Math.abs(r.value)));
  document.getElementById('barTitle').textContent=state.strategy&&state.ticker&&syntheticNames.has(state.ticker)?`Latest ${state.ticker} P&L by leg · ${state.strategy}`:state.strategy?`Latest daily P&L by ticker · ${state.strategy}`:state.ticker?`Latest ${state.ticker} P&L by strategy`:'Latest daily P&L by strategy';
  const el=document.getElementById('bars');
  el.innerHTML=rows.map(r=>{const width=50*Math.abs(r.value)/max;const cls=r.value>=0?'pos':'neg';return `<div class="bar-row" data-name="${esc(r.name)}" data-type="${r.type}"><div class="bar-name" title="${esc(r.name)}">${esc(r.name)}</div><div class="bar-track"><span class="bar-zero"></span><span class="bar ${cls}" style="width:${width}%"></span></div><div class="bar-value ${signClass(r.value)}">${fmt(r.value)}</div></div>`}).join('')||'<div class="empty">No values on the latest date.</div>';
  el.querySelectorAll('.bar-row').forEach(row=>row.onclick=()=>{if(row.dataset.type==='strategy'){state.strategy=row.dataset.name;state.ticker=null;}else if(row.dataset.type==='strategyTicker'){state.strategy=row.dataset.name;}else state.ticker=row.dataset.name;render();});
}
function drawChart(){
  const svg=document.getElementById('lineChart'), box=svg.getBoundingClientRect(), w=Math.max(420,box.width),h=Math.max(300,box.height),pad={l:72,r:76,t:30,b:43};
  svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
  const daily=activeSeries(), cumulative=[];
  daily.reduce((sum,value,i)=>(cumulative[i]=sum+value,sum+value),0);
  const range=values=>{let lo=Math.min(0,...values),hi=Math.max(0,...values),span=hi-lo;if(span===0)span=1;return [lo-span*.10,hi+span*.10];};
  const [dailyMin,dailyMax]=range(daily),[cumMin,cumMax]=range(cumulative);
  const plotWidth=w-pad.l-pad.r;
  const x=i=>pad.l+((i+.5)/dates.length)*plotWidth;
  const yDaily=v=>pad.t+(dailyMax-v)/(dailyMax-dailyMin)*(h-pad.t-pad.b);
  const yCum=v=>pad.t+(cumMax-v)/(cumMax-cumMin)*(h-pad.t-pad.b);
  const parts=[];
  parts.push(`<text x="${pad.l}" y="14" fill="#65738a" font-size="11" font-weight="700">DAILY P&L</text>`,`<text x="${w-pad.r}" y="14" text-anchor="end" fill="#2563eb" font-size="11" font-weight="700">CUMULATIVE P&L</text>`);
  for(let j=0;j<5;j++){
    const dailyValue=dailyMax-j*(dailyMax-dailyMin)/4,yy=pad.t+j*(h-pad.t-pad.b)/4,cumValue=cumMax-j*(cumMax-cumMin)/4;
    parts.push(`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#e8edf4"/><text x="${pad.l-10}" y="${yy+4}" text-anchor="end" fill="#748096" font-size="11">${fmt(dailyValue)}</text><text x="${w-pad.r+10}" y="${yy+4}" fill="#2563eb" font-size="11">${fmt(cumValue)}</text>`);
  }
  parts.push(`<line x1="${pad.l}" y1="${yDaily(0)}" x2="${w-pad.r}" y2="${yDaily(0)}" stroke="#8f9bad" stroke-width="1.3"/>`);
  const tickCount=Math.min(5,dates.length),used=new Set();
  for(let j=0;j<tickCount;j++){const i=Math.round(j*(dates.length-1)/Math.max(1,tickCount-1));if(used.has(i))continue;used.add(i);parts.push(`<text x="${x(i)}" y="${h-15}" text-anchor="middle" fill="#748096" font-size="11">${dates[i]}</text>`);}
  const slot=plotWidth/Math.max(1,dates.length),barWidth=Math.max(1,Math.min(18,slot*.66)),zeroY=yDaily(0);
  daily.forEach((value,i)=>{const yy=yDaily(value),top=Math.min(yy,zeroY),height=Math.max(1,Math.abs(yy-zeroY)),fill=value>=0?'#29a37a':'#e05b68';parts.push(`<rect x="${x(i)-barWidth/2}" y="${top}" width="${barWidth}" height="${height}" rx="1.5" fill="${fill}" opacity=".88"/>`);});
  const points=cumulative.map((v,i)=>`${x(i)},${yCum(v)}`).join(' ');
  parts.push(`<polyline points="${points}" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`);
  const last=cumulative.length-1;parts.push(`<circle cx="${x(last)}" cy="${yCum(cumulative[last])}" r="4" fill="#2563eb" stroke="#fff" stroke-width="2"/>`);
  parts.push(`<rect id="chartOverlay" x="${pad.l}" y="${pad.t}" width="${w-pad.l-pad.r}" height="${h-pad.t-pad.b}" fill="transparent"/>`);
  svg.innerHTML=parts.join('');svg.setAttribute('aria-label',`${activeLabel()} daily and cumulative P&L history`);
  const overlay=svg.querySelector('#chartOverlay'),tip=document.getElementById('tooltip'),areaEl=document.getElementById('chartArea');
  overlay.onmousemove=e=>{const rect=svg.getBoundingClientRect(),sx=(e.clientX-rect.left)*(w/rect.width),i=Math.max(0,Math.min(dates.length-1,Math.floor((sx-pad.l)/plotWidth*dates.length)));tip.style.display='block';tip.innerHTML=`${dates[i]}<div>Daily: <b>${exact(daily[i])}</b></div><div>Cumulative: <b>${exact(cumulative[i])}</b></div>`;let left=e.clientX-areaEl.getBoundingClientRect().left+12;if(left+190>areaEl.clientWidth)left-=200;tip.style.left=left+'px';tip.style.top=(e.clientY-areaEl.getBoundingClientRect().top-62)+'px';};
  overlay.onmouseleave=()=>tip.style.display='none';
}
function renderChart(){
  document.getElementById('chartTitle').textContent=`${activeLabel()} · daily and cumulative P&L`;
  document.getElementById('chartSub').textContent=`${dates[0]} to ${dates.at(-1)} · bars are daily P&L; blue curve is cumulative P&L`;
  drawChart();renderBars();
}
function render(){renderCrumbs();renderSelectors();renderKpis();renderStrategies();renderTickers();renderPositions();renderExpiryDistribution();renderChart();}

document.getElementById('asOf').textContent=`As of ${dates.at(-1)}`;
document.getElementById('sourceMeta').textContent=`${PAYLOAD.source} · ${PAYLOAD.sourceRows.toLocaleString()} source rows`;
document.getElementById('footer').textContent=`Generated ${PAYLOAD.generatedAt} · ${PAYLOAD.headerDetected?'Header detected':'Headerless sequence detected'} · MtM_PnL treated as daily P&L · ${PAYLOAD.positionColumns?'Position columns detected':'No position columns'} · ${PAYLOAD.valueDateColumn?'ValueDT detected':'No ValueDT'} · blank/null P&L treated as $0`;
document.getElementById('strategySearch').oninput=e=>{state.search=e.target.value;renderStrategies();};
document.getElementById('strategySelect').onchange=e=>{const next=e.target.value||null;if(next&&state.ticker&&!tickersByStrategy.get(next)?.has(state.ticker))state.ticker=null;state.strategy=next;render();};
document.getElementById('tickerSelect').onchange=e=>{state.ticker=e.target.value||null;render();};
document.querySelectorAll('#strategyTable th').forEach(th=>th.onclick=()=>{const key=th.dataset.key;if(state.strategySort.key===key)state.strategySort.dir*=-1;else state.strategySort={key,dir:key==='name'?1:-1};renderStrategies();});
document.querySelectorAll('#tickerTable th').forEach(th=>th.onclick=()=>{const key=th.dataset.key;if(state.tickerSort.key===key)state.tickerSort.dir*=-1;else state.tickerSort={key,dir:key==='name'?1:-1};renderTickers();});
new ResizeObserver(()=>drawChart()).observe(document.getElementById('chartArea'));
new ResizeObserver(()=>renderExpiryDistribution()).observe(document.getElementById('expiryChartArea'));
render();
</script>
</body>
</html>
'''


def build_dashboard(input_path: Path, output_path: Path) -> None:
    (
        rows,
        dates,
        has_header,
        source_rows,
        position_rows,
        has_positions,
        has_value_dates,
    ) = read_csv(input_path)
    payload = {
        "dates": dates,
        "rows": rows,
        "positions": position_rows,
        "positionColumns": has_positions,
        "valueDateColumn": has_value_dates,
        "source": input_path.name,
        "sourceRows": source_rows,
        "headerDetected": has_header,
        "generatedAt": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        HTML_TEMPLATE.replace("__LATEST_DATE__", dates[-1]).replace(
            "__PAYLOAD__", payload_json
        ),
        encoding="utf-8",
    )

    strategies = len({row[1] for row in rows})
    tickers = len({row[2] for row in rows})
    print(f"Generated: {output_path.resolve()}")
    print(
        f"Dates: {dates[0]} to {dates[-1]} | "
        f"Strategies: {strategies} | Tickers: {tickers} | "
        f"Source rows: {source_rows} | Latest position rows: {len(position_rows)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a static Strategy MtM P&L HTML dashboard."
    )
    parser.add_argument("csv_file", type=Path, help="Input CSV file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("index.html"),
        help="Output HTML path (default: index.html)",
    )
    args = parser.parse_args()
    if not args.csv_file.is_file():
        parser.error(f"input file does not exist: {args.csv_file}")
    try:
        build_dashboard(args.csv_file, args.output)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
