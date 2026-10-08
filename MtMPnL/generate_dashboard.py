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


EXPECTED_COLUMNS = ("CobDate", "Strategy", "Ticker", "MtM_PnL")


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def parse_date(value: str, line_number: int) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError(f"line {line_number}: CobDate is blank")

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
        f"line {line_number}: unsupported CobDate {value!r}; use YYYY-MM-DD"
    )


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


def read_csv(path: Path) -> tuple[list[list[object]], list[str], bool, int]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("input CSV is empty")

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    raw_rows = [row for row in csv.reader(text.splitlines(), dialect) if any(x.strip() for x in row)]
    if not raw_rows:
        raise ValueError("input CSV has no data rows")

    wanted = {normalized_header(name): name for name in EXPECTED_COLUMNS}
    first = [normalized_header(cell) for cell in raw_rows[0]]
    has_header = all(name in first for name in wanted)

    if has_header:
        indexes = {wanted[name]: first.index(name) for name in wanted}
        data_rows = raw_rows[1:]
        first_line = 2
    else:
        indexes = {name: index for index, name in enumerate(EXPECTED_COLUMNS)}
        data_rows = raw_rows
        first_line = 1

    aggregated: defaultdict[tuple[str, str, str], float] = defaultdict(float)
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
        source_rows += 1

    rows = [
        [date, strategy, ticker, round(value, 6)]
        for (date, strategy, ticker), value in sorted(aggregated.items())
    ]
    dates = sorted({row[0] for row in rows})
    if not dates:
        raise ValueError("input CSV contains no valid data rows")
    return rows, dates, has_header, source_rows


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
    button,input{font:inherit}
    .shell{max-width:1580px;margin:0 auto;padding:24px}
    .top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}
    h1{font-size:26px;line-height:1.15;margin:0 0 7px;letter-spacing:-.02em}
    .subtitle{color:var(--muted);font-size:14px}
    .asof{text-align:right;color:var(--muted);font-size:13px;white-space:nowrap}
    .asof strong{display:block;color:var(--text);font-size:15px;margin-bottom:2px}
    .crumbs{display:flex;align-items:center;gap:8px;margin:0 0 14px;min-height:34px}
    .crumb{border:1px solid var(--line);background:#fff;color:var(--muted);padding:7px 11px;border-radius:8px;cursor:pointer}
    .crumb.active{border-color:#b8caf6;background:var(--blue-soft);color:var(--blue);font-weight:700}
    .chev{color:#a4adbb}
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
    .empty{padding:32px;text-align:center;color:var(--muted)}
    .footer{color:var(--muted);font-size:11px;margin-top:12px;text-align:right}
    @media(max-width:1050px){.grid{grid-template-columns:1fr}.chart-panel{min-height:580px}.kpis{grid-template-columns:repeat(3,1fr)}}
    @media(max-width:680px){.shell{padding:14px}.top{display:block}.asof{text-align:left;margin-top:10px}.kpis{grid-template-columns:repeat(2,1fr)}.grid{display:block}.panel{margin-bottom:14px}.search{width:145px}.kpi-value{font-size:21px}.chart-area{height:330px}}
  </style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div><h1>Strategy MtM P&amp;L</h1><div class="subtitle">Whole-book, strategy and currency-pair views from one source file</div></div>
    <div class="asof"><strong id="asOf"></strong><span id="sourceMeta"></span></div>
  </div>

  <div class="crumbs" id="crumbs"></div>
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
            <th data-key="current">Current <span class="sort-mark"></span></th>
            <th data-key="dod">DoD <span class="sort-mark"></span></th>
            <th data-key="w1">1W <span class="sort-mark"></span></th>
            <th data-key="mtd">MTD <span class="sort-mark"></span></th>
            <th data-key="ytd">YTD <span class="sort-mark"></span></th>
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

  <section class="panel detail">
    <div class="panel-head"><div><div class="panel-title" id="detailTitle">Currency-pair detail</div><div class="panel-sub" id="detailSub"></div></div></div>
    <div class="table-wrap" id="detailWrap">
      <table id="tickerTable">
        <thead><tr>
          <th data-key="name">Ticker <span class="sort-mark"></span></th>
          <th data-key="current">Current <span class="sort-mark"></span></th>
          <th data-key="dod">DoD <span class="sort-mark"></span></th>
          <th data-key="w1">1W <span class="sort-mark"></span></th>
          <th data-key="mtd">MTD <span class="sort-mark"></span></th>
          <th data-key="ytd">YTD <span class="sort-mark"></span></th>
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
const strategies = [...new Set(PAYLOAD.rows.map(r => r[1]))].sort((a,b)=>a.localeCompare(b));
const dateIndex = new Map(dates.map((d,i)=>[d,i]));
const zeroSeries = () => Array(dates.length).fill(0);
const book = zeroSeries();
const byStrategy = new Map();
const byStrategyTicker = new Map();
const tickersByStrategy = new Map();

for (const [date,strategy,ticker,value] of PAYLOAD.rows) {
  const i = dateIndex.get(date);
  book[i] += value;
  if (!byStrategy.has(strategy)) byStrategy.set(strategy, zeroSeries());
  byStrategy.get(strategy)[i] += value;
  const key = strategy + '\u0000' + ticker;
  if (!byStrategyTicker.has(key)) byStrategyTicker.set(key, zeroSeries());
  byStrategyTicker.get(key)[i] += value;
  if (!tickersByStrategy.has(strategy)) tickersByStrategy.set(strategy, new Set());
  tickersByStrategy.get(strategy).add(ticker);
}

const state = {strategy:null, ticker:null, strategySort:{key:'current',dir:-1}, tickerSort:{key:'current',dir:-1}, search:''};
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
function baselineIndex(kind) {
  const last = new Date(dates.at(-1)+'T00:00:00Z');
  let cutoff;
  if (kind==='w1') cutoff = new Date(last.getTime()-7*86400000);
  if (kind==='mtd') cutoff = new Date(Date.UTC(last.getUTCFullYear(),last.getUTCMonth(),1)-86400000);
  if (kind==='ytd') cutoff = new Date(Date.UTC(last.getUTCFullYear(),0,1)-86400000);
  const target=cutoff.toISOString().slice(0,10);
  let idx=-1;
  for(let i=0;i<dates.length;i++){if(dates[i]<=target)idx=i;else break;}
  if(idx>=0)return idx;
  if(kind==='mtd'){const p=dates.findIndex(d=>d.slice(0,7)===dates.at(-1).slice(0,7));return p>=0?p:null;}
  if(kind==='ytd'){const p=dates.findIndex(d=>d.slice(0,4)===dates.at(-1).slice(0,4));return p>=0?p:null;}
  return null;
}
const refs={dod:dates.length>1?dates.length-2:null,w1:baselineIndex('w1'),mtd:baselineIndex('mtd'),ytd:baselineIndex('ytd')};
function metrics(series) {
  const current=series.at(-1);
  const change=i=>i==null?null:current-series[i];
  return {current,dod:change(refs.dod),w1:change(refs.w1),mtd:change(refs.mtd),ytd:change(refs.ytd)};
}
function activeSeries() {
  if (!state.strategy) return book;
  if (!state.ticker) return byStrategy.get(state.strategy) || zeroSeries();
  return byStrategyTicker.get(state.strategy+'\u0000'+state.ticker) || zeroSeries();
}
function activeLabel() { return state.ticker || state.strategy || 'Whole book'; }
function metricCell(v){return `<td class="money ${signClass(v)}">${fmt(v)}</td>`}

function renderCrumbs(){
  const parts=[`<button class="crumb ${!state.strategy?'active':''}" data-level="book">Whole book</button>`];
  if(state.strategy){parts.push('<span class="chev">›</span>',`<button class="crumb ${!state.ticker?'active':''}" data-level="strategy">${esc(state.strategy)}</button>`);}
  if(state.ticker){parts.push('<span class="chev">›</span>',`<button class="crumb active" data-level="ticker">${esc(state.ticker)}</button>`);}
  const el=document.getElementById('crumbs');el.innerHTML=parts.join('');
  el.querySelectorAll('button').forEach(b=>b.onclick=()=>{if(b.dataset.level==='book'){state.strategy=null;state.ticker=null;}if(b.dataset.level==='strategy')state.ticker=null;render();});
}
function renderKpis(){
  const m=metrics(activeSeries());
  const items=[['Current MtM',m.current,'Latest level'],['Day change',m.dod,refs.dod==null?'No prior date':`vs ${dates[refs.dod]}`],['1 week',m.w1,refs.w1==null?'No history':`vs ${dates[refs.w1]}`],['MTD',m.mtd,refs.mtd==null?'No history':`vs ${dates[refs.mtd]}`],['YTD',m.ytd,refs.ytd==null?'No history':`vs ${dates[refs.ytd]}`]];
  document.getElementById('kpis').innerHTML=items.map(([label,v,note])=>`<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value ${signClass(v)}">${fmt(v)}</div><div class="kpi-note">${note}</div></div>`).join('');
}
function strategyRows(){
  return strategies.map(name=>{const m=metrics(byStrategy.get(name));return {...m,name,tickers:tickersByStrategy.get(name)?.size||0};});
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
  document.querySelector('#strategyTable tbody').innerHTML=rows.map(r=>`<tr data-name="${esc(r.name)}" class="${state.strategy===r.name?'selected':''}"><td title="${esc(r.name)}">${esc(r.name)}</td>${metricCell(r.current)}${metricCell(r.dod)}${metricCell(r.w1)}${metricCell(r.mtd)}${metricCell(r.ytd)}<td>${r.tickers}</td></tr>`).join('');
  document.querySelectorAll('#strategyTable tbody tr').forEach(tr=>tr.onclick=()=>{state.strategy=tr.dataset.name;state.ticker=null;render();});
  document.getElementById('strategyCount').textContent=`${rows.length} of ${strategies.length} strategies · click a row to drill down`;
  updateSortMarks('strategyTable',state.strategySort);
}
function tickerRows(){
  if(!state.strategy)return [];
  return [...(tickersByStrategy.get(state.strategy)||[])].map(name=>{const m=metrics(byStrategyTicker.get(state.strategy+'\u0000'+name));return {...m,name};}).sort((a,b)=>compareRows(a,b,state.tickerSort));
}
function renderTickers(){
  const body=document.querySelector('#tickerTable tbody');
  if(!state.strategy){document.getElementById('detailTitle').textContent='Currency-pair detail';document.getElementById('detailSub').textContent='Select a strategy to see its tickers';body.innerHTML='<tr><td colspan="6" class="empty">Choose a strategy from the table above.</td></tr>';updateSortMarks('tickerTable',state.tickerSort);return;}
  const rows=tickerRows();
  document.getElementById('detailTitle').textContent=`${state.strategy} · currency-pair detail`;
  document.getElementById('detailSub').textContent=`${rows.length} ticker${rows.length===1?'':'s'} · click a row to isolate its history`;
  body.innerHTML=rows.map(r=>`<tr data-name="${esc(r.name)}" class="${state.ticker===r.name?'selected':''}"><td>${esc(r.name)}</td>${metricCell(r.current)}${metricCell(r.dod)}${metricCell(r.w1)}${metricCell(r.mtd)}${metricCell(r.ytd)}</tr>`).join('');
  body.querySelectorAll('tr').forEach(tr=>tr.onclick=()=>{state.ticker=tr.dataset.name;render();});
  updateSortMarks('tickerTable',state.tickerSort);
}
function renderBars(){
  let rows;
  if(state.strategy){rows=tickerRows().map(r=>({name:r.name,value:r.current,type:'ticker'}));}
  else{rows=strategyRows().map(r=>({name:r.name,value:r.current,type:'strategy'}));}
  rows.sort((a,b)=>Math.abs(b.value)-Math.abs(a.value));
  const max=Math.max(1,...rows.map(r=>Math.abs(r.value)));
  document.getElementById('barTitle').textContent=state.strategy?`Latest ticker composition · ${state.strategy}`:'Latest strategy composition';
  const el=document.getElementById('bars');
  el.innerHTML=rows.map(r=>{const width=50*Math.abs(r.value)/max;const cls=r.value>=0?'pos':'neg';return `<div class="bar-row" data-name="${esc(r.name)}" data-type="${r.type}"><div class="bar-name" title="${esc(r.name)}">${esc(r.name)}</div><div class="bar-track"><span class="bar-zero"></span><span class="bar ${cls}" style="width:${width}%"></span></div><div class="bar-value ${signClass(r.value)}">${fmt(r.value)}</div></div>`}).join('')||'<div class="empty">No values on the latest date.</div>';
  el.querySelectorAll('.bar-row').forEach(row=>row.onclick=()=>{if(row.dataset.type==='strategy'){state.strategy=row.dataset.name;state.ticker=null;}else state.ticker=row.dataset.name;render();});
}
function drawChart(){
  const svg=document.getElementById('lineChart'), box=svg.getBoundingClientRect(), w=Math.max(420,box.width),h=Math.max(300,box.height),pad={l:72,r:20,t:18,b:43};
  svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
  const series=activeSeries(), minValue=Math.min(0,...series),maxValue=Math.max(0,...series);
  let span=maxValue-minValue;if(span===0)span=1;
  const margin=span*.12,yMin=minValue-margin,yMax=maxValue+margin;
  const x=i=>pad.l+(dates.length===1?0.5:(i/(dates.length-1)))*(w-pad.l-pad.r);
  const y=v=>pad.t+(yMax-v)/(yMax-yMin)*(h-pad.t-pad.b);
  const parts=[];
  for(let j=0;j<5;j++){const val=yMax-j*(yMax-yMin)/4,yy=y(val);parts.push(`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#e8edf4"/><text x="${pad.l-10}" y="${yy+4}" text-anchor="end" fill="#748096" font-size="11">${fmt(val)}</text>`);}
  if(yMin<=0&&yMax>=0)parts.push(`<line x1="${pad.l}" y1="${y(0)}" x2="${w-pad.r}" y2="${y(0)}" stroke="#8f9bad" stroke-width="1.3"/>`);
  const tickCount=Math.min(5,dates.length),used=new Set();
  for(let j=0;j<tickCount;j++){const i=Math.round(j*(dates.length-1)/Math.max(1,tickCount-1));if(used.has(i))continue;used.add(i);parts.push(`<text x="${x(i)}" y="${h-15}" text-anchor="middle" fill="#748096" font-size="11">${dates[i]}</text>`);}
  const points=series.map((v,i)=>`${x(i)},${y(v)}`).join(' ');
  const area=`${x(0)},${y(0)} ${points} ${x(series.length-1)},${y(0)}`;
  parts.push(`<polygon points="${area}" fill="rgba(37,99,235,.09)"/>`,`<polyline points="${points}" fill="none" stroke="#2563eb" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`);
  const last=series.length-1;parts.push(`<circle cx="${x(last)}" cy="${y(series[last])}" r="4" fill="#2563eb" stroke="#fff" stroke-width="2"/>`);
  parts.push(`<rect id="chartOverlay" x="${pad.l}" y="${pad.t}" width="${w-pad.l-pad.r}" height="${h-pad.t-pad.b}" fill="transparent"/>`);
  svg.innerHTML=parts.join('');svg.setAttribute('aria-label',`${activeLabel()} MtM P&L history`);
  const overlay=svg.querySelector('#chartOverlay'),tip=document.getElementById('tooltip'),areaEl=document.getElementById('chartArea');
  overlay.onmousemove=e=>{const rect=svg.getBoundingClientRect(),sx=(e.clientX-rect.left)*(w/rect.width),i=Math.max(0,Math.min(dates.length-1,Math.round((sx-pad.l)/(w-pad.l-pad.r)*(dates.length-1))));tip.style.display='block';tip.innerHTML=`${dates[i]}<strong>${exact(series[i])}</strong>`;let left=e.clientX-areaEl.getBoundingClientRect().left+12;if(left+150>areaEl.clientWidth)left-=165;tip.style.left=left+'px';tip.style.top=(e.clientY-areaEl.getBoundingClientRect().top-48)+'px';};
  overlay.onmouseleave=()=>tip.style.display='none';
}
function renderChart(){
  document.getElementById('chartTitle').textContent=`${activeLabel()} · MtM history`;
  document.getElementById('chartSub').textContent=`${dates[0]} to ${dates.at(-1)} · daily snapshot levels`;
  drawChart();renderBars();
}
function render(){renderCrumbs();renderKpis();renderStrategies();renderTickers();renderChart();}

document.getElementById('asOf').textContent=`As of ${dates.at(-1)}`;
document.getElementById('sourceMeta').textContent=`${PAYLOAD.source} · ${PAYLOAD.sourceRows.toLocaleString()} source rows`;
document.getElementById('footer').textContent=`Generated ${PAYLOAD.generatedAt} · ${PAYLOAD.headerDetected?'Header detected':'Headerless sequence detected'} · blank/null P&L treated as $0`;
document.getElementById('strategySearch').oninput=e=>{state.search=e.target.value;renderStrategies();};
document.querySelectorAll('#strategyTable th').forEach(th=>th.onclick=()=>{const key=th.dataset.key;if(state.strategySort.key===key)state.strategySort.dir*=-1;else state.strategySort={key,dir:key==='name'?1:-1};renderStrategies();});
document.querySelectorAll('#tickerTable th').forEach(th=>th.onclick=()=>{const key=th.dataset.key;if(state.tickerSort.key===key)state.tickerSort.dir*=-1;else state.tickerSort={key,dir:key==='name'?1:-1};renderTickers();});
new ResizeObserver(()=>drawChart()).observe(document.getElementById('chartArea'));
render();
</script>
</body>
</html>
'''


def build_dashboard(input_path: Path, output_path: Path) -> None:
    rows, dates, has_header, source_rows = read_csv(input_path)
    payload = {
        "dates": dates,
        "rows": rows,
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
        HTML_TEMPLATE.replace("__PAYLOAD__", payload_json), encoding="utf-8"
    )

    strategies = len({row[1] for row in rows})
    tickers = len({row[2] for row in rows})
    print(f"Generated: {output_path.resolve()}")
    print(
        f"Dates: {dates[0]} to {dates[-1]} | "
        f"Strategies: {strategies} | Tickers: {tickers} | Source rows: {source_rows}"
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
