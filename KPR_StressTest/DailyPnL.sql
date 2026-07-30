/*==========================================================================
  Historical daily P&L replay  --  static delta, exact reprice (Method B)

  Inputs   #latest_exposure (Ticker_CCY3, Days, Delta_USD_USDDirection)
           #rates           (Date, Ticker, CurveID, Value)      Value = USDXXX
           #mapping_table   (Ticker, CurveId, Ticker_CCY3, Days)

  Output   #DailyPnL        (Dates, Ticker_CCY3, Delta_USD_USDDirection,
                             DailyPnL, CumDailyPnL, IsCarried)
           #Diagnostics     (Severity, Issue, Ticker_CCY3, Detail)

  Method   Today's exposure is held constant and pushed through historical
           rate moves.  P&L is the exact reprice of a static USD notional:

               DailyPnL = Delta * (1 - Value_prev / Value_t)

           Value is quoted USDXXX (foreign units per 1 USD), so Value rising
           = USD strengthening = gain on a positive (long USD) delta.

           Worked check.  Delta = -10,000,000 on AUD (short 10mm USD /
           long 15mm AUD).  USDAUD 1.5000 -> 1.5150:
               -10,000,000 * (1 - 1.5000/1.5150) = -99,009.90 USD
           A loss, because USD rallied while we were short it.

  Note     Daily P&L under Method B will not sum to the exact reprice of the
           full-period move.  That is inherent to any daily replay against a
           static delta -- the period total is spread across days, not lost.
==========================================================================*/

SET NOCOUNT ON;

DECLARE @StartDate date = '2024-01-01';
DECLARE @EndDate   date = '2024-12-31';


/*--------------------------------------------------------------------------
  1.  Positions.  Exposure joined through the mapping table to a rate
      series.  Keyed on (Ticker_CCY3, Days) so this still works when Days
      stops being 0.  USD is dropped -- there is no USDUSD to revalue.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#positions') IS NOT NULL DROP TABLE #positions;

SELECT  e.Ticker_CCY3,
        e.Days,
        e.Delta_USD_USDDirection,
        m.Ticker,
        m.CurveID
INTO    #positions
FROM    #latest_exposure e
JOIN    #mapping_table   m ON m.Ticker_CCY3 = e.Ticker_CCY3
                          AND m.Days        = e.Days
WHERE   e.Ticker_CCY3 <> 'USD';

CREATE CLUSTERED INDEX ix_positions ON #positions (Ticker, CurveID);


/*--------------------------------------------------------------------------
  2.  Date spine.  Every date on which any mapped series quoted inside the
      window.  Built from observed dates rather than a calendar, so dates
      the whole USD complex was shut (US holidays) never enter the spine
      and never generate carry-forward rows.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#spine') IS NOT NULL DROP TABLE #spine;

SELECT  DISTINCT r.[Date]
INTO    #spine
FROM    #rates r
WHERE   r.[Date] BETWEEN @StartDate AND @EndDate
  AND   EXISTS (SELECT 1
                FROM   #positions p
                WHERE  p.Ticker  = r.Ticker
                  AND  p.CurveID = r.CurveID);


/*--------------------------------------------------------------------------
  3.  Seed.  Last observation strictly before @StartDate, so the first day
      of the window earns a real P&L instead of a NULL.  A NULL seed means
      the series has no history before the window -- surfaced in step 6.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#seed') IS NOT NULL DROP TABLE #seed;

SELECT  p.Ticker,
        p.CurveID,
        s.SeedDate,
        s.SeedValue
INTO    #seed
FROM    (SELECT DISTINCT Ticker, CurveID FROM #positions) p
OUTER APPLY (
        SELECT  TOP (1) r.[Date] AS SeedDate, r.[Value] AS SeedValue
        FROM    #rates r
        WHERE   r.Ticker  = p.Ticker
          AND   r.CurveID = p.CurveID
          AND   r.[Date]  < @StartDate
          AND   r.[Value] IS NOT NULL
        ORDER BY r.[Date] DESC
) s;


/*--------------------------------------------------------------------------
  4.  Panel.  Every position on every spine date, carrying the raw quote
      where one exists.  FillGrp is the islands key for the forward fill:
      a running count of non-null quotes, so each gap inherits the group
      of the last real observation before it.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#panel') IS NOT NULL DROP TABLE #panel;

SELECT  sp.[Date] AS Dates,
        p.Ticker_CCY3,
        p.Days,
        p.Delta_USD_USDDirection,
        p.Ticker,
        p.CurveID,
        r.[Value] AS RawValue,
        COUNT(r.[Value]) OVER (PARTITION BY p.Ticker_CCY3, p.Days
                               ORDER BY sp.[Date]
                               ROWS UNBOUNDED PRECEDING) AS FillGrp
INTO    #panel
FROM    #positions p
CROSS JOIN #spine sp
LEFT JOIN #rates r ON r.Ticker  = p.Ticker
                  AND r.CurveID = p.CurveID
                  AND r.[Date]  = sp.[Date];


/*--------------------------------------------------------------------------
  5.  Forward-fill and price the move.

      FilledValue  last known quote on or before Dates, falling back to the
                   pre-window seed for any leading gap.  NULL only when the
                   series has no observation at or before that date at all.
      PrevValue    previous spine date's filled value; the seed supplies it
                   on the first day of the window.
      IsCarried    1 where the quote was filled rather than observed.

      A carried day gives FilledValue = PrevValue, hence exactly zero P&L,
      and the move lands whole on the next real quote.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#priced') IS NOT NULL DROP TABLE #priced;

WITH filled AS (
    SELECT  pn.*,
            sd.SeedValue,
            COALESCE(MAX(pn.RawValue) OVER (PARTITION BY pn.Ticker_CCY3,
                                                         pn.Days,
                                                         pn.FillGrp),
                     sd.SeedValue) AS FilledValue
    FROM    #panel pn
    JOIN    #seed  sd ON sd.Ticker  = pn.Ticker
                     AND sd.CurveID = pn.CurveID
)
SELECT  f.Dates,
        f.Ticker_CCY3,
        f.Days,
        f.Delta_USD_USDDirection,
        f.Ticker,
        f.CurveID,
        f.RawValue,
        f.FilledValue,
        COALESCE(LAG(f.FilledValue) OVER (PARTITION BY f.Ticker_CCY3, f.Days
                                          ORDER BY f.Dates),
                 f.SeedValue) AS PrevValue,
        CASE WHEN f.RawValue IS NULL THEN 1 ELSE 0 END AS IsCarried
INTO    #priced
FROM    filled f;


/*--------------------------------------------------------------------------
  6.  Result.  Rectangular: one row per date per currency.
      DailyPnL is NULL only where the series had no price to work from --
      those rows are listed in #Diagnostics rather than silently zeroed,
      because a zero would quietly flatter the portfolio total.

      CumDailyPnL is the running total per currency from @StartDate.  SUM()
      skips NULLs, so an unpriced date leaves the cumulative flat rather
      than poisoning the rest of the series -- check Days_Unpriced in the
      summary before reading a cumulative that spans one.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#DailyPnL') IS NOT NULL DROP TABLE #DailyPnL;

WITH pnl AS (
    SELECT  pr.Dates,
            pr.Ticker_CCY3,
            pr.Days,
            pr.Delta_USD_USDDirection,
            CAST(pr.Delta_USD_USDDirection
                 * (1.0 - CAST(pr.PrevValue AS float) / NULLIF(pr.FilledValue, 0))
                 AS decimal(38,10)) AS DailyPnL,
            pr.IsCarried
    FROM    #priced pr
)
SELECT  p.Dates,
        p.Ticker_CCY3,
        p.Delta_USD_USDDirection,
        p.DailyPnL,
        SUM(p.DailyPnL) OVER (PARTITION BY p.Ticker_CCY3, p.Days
                              ORDER BY p.Dates
                              ROWS UNBOUNDED PRECEDING) AS CumDailyPnL,
        p.IsCarried
INTO    #DailyPnL
FROM    pnl p;

CREATE CLUSTERED INDEX ix_dailypnl ON #DailyPnL (Dates, Ticker_CCY3);


/*--------------------------------------------------------------------------
  7.  Diagnostics.  Everything that was dropped, fanned out, filled or left
      unpriced, in one place.
--------------------------------------------------------------------------*/
IF OBJECT_ID('tempdb..#Diagnostics') IS NOT NULL DROP TABLE #Diagnostics;

CREATE TABLE #Diagnostics (
    Severity    varchar(10),
    Issue       varchar(60),
    Ticker_CCY3 varchar(10)  NULL,
    Detail      varchar(400) NULL
);

-- Exposure rows that found no mapping.  These contribute no P&L at all.
INSERT #Diagnostics
SELECT 'ERROR', 'Exposure has no mapping row', e.Ticker_CCY3,
       CONCAT('Days=', e.Days, '  Delta=', e.Delta_USD_USDDirection)
FROM   #latest_exposure e
WHERE  e.Ticker_CCY3 <> 'USD'
  AND  NOT EXISTS (SELECT 1 FROM #mapping_table m
                   WHERE m.Ticker_CCY3 = e.Ticker_CCY3 AND m.Days = e.Days);

-- Mapping fans out: one exposure row would be counted more than once.
INSERT #Diagnostics
SELECT 'ERROR', 'Mapping is not unique (P&L double-counted)', m.Ticker_CCY3,
       CONCAT('Days=', m.Days, '  matches ', COUNT(*), ' mapping rows')
FROM   #mapping_table m
WHERE  EXISTS (SELECT 1 FROM #latest_exposure e
               WHERE e.Ticker_CCY3 = m.Ticker_CCY3 AND e.Days = m.Days)
GROUP BY m.Ticker_CCY3, m.Days
HAVING COUNT(*) > 1;

-- Duplicate quotes: same series, same date, more than one price.
INSERT #Diagnostics
SELECT 'ERROR', 'Duplicate rate rows (P&L double-counted)', p.Ticker_CCY3,
       CONCAT(r.Ticker, '/', r.CurveID, ' on ', CONVERT(varchar(10), r.[Date], 23),
              ': ', COUNT(*), ' rows')
FROM   #rates r
JOIN   #positions p ON p.Ticker = r.Ticker AND p.CurveID = r.CurveID
WHERE  r.[Date] BETWEEN @StartDate AND @EndDate
GROUP BY p.Ticker_CCY3, r.Ticker, r.CurveID, r.[Date]
HAVING COUNT(*) > 1;

-- Series with no usable price anywhere: no seed and nothing in the window.
INSERT #Diagnostics
SELECT 'ERROR', 'No rates found for mapped series', p.Ticker_CCY3,
       CONCAT(p.Ticker, '/', p.CurveID, ' has no price at or before ',
              CONVERT(varchar(10), @EndDate, 23))
FROM   #positions p
WHERE  NOT EXISTS (SELECT 1 FROM #rates r
                   WHERE r.Ticker = p.Ticker AND r.CurveID = p.CurveID
                     AND r.[Date] <= @EndDate AND r.[Value] IS NOT NULL);

-- History starts mid-window: leading dates cannot be filled in either
-- direction, so DailyPnL is NULL there.
INSERT #Diagnostics
SELECT 'WARN', 'History starts mid-window, leading P&L is NULL', pr.Ticker_CCY3,
       CONCAT(COUNT(*), ' unpriced dates up to ',
              CONVERT(varchar(10), MAX(pr.Dates), 23))
FROM   #priced pr
WHERE  pr.FilledValue IS NULL
GROUP BY pr.Ticker_CCY3
HAVING COUNT(*) > 0;

-- Non-positive prices break the reprice and indicate bad data upstream.
INSERT #Diagnostics
SELECT 'ERROR', 'Non-positive rate', p.Ticker_CCY3,
       CONCAT(CONVERT(varchar(10), r.[Date], 23), ' Value=', r.[Value])
FROM   #rates r
JOIN   #positions p ON p.Ticker = r.Ticker AND p.CurveID = r.CurveID
WHERE  r.[Date] BETWEEN @StartDate AND @EndDate
  AND  r.[Value] <= 0;

-- Carry-forward volume.  A handful of days per currency is normal
-- (idiosyncratic local holidays); a large count means a stale feed.
INSERT #Diagnostics
SELECT 'INFO', 'Dates carried forward', pr.Ticker_CCY3,
       CONCAT(SUM(pr.IsCarried), ' of ', COUNT(*), ' dates filled')
FROM   #priced pr
GROUP BY pr.Ticker_CCY3
HAVING SUM(pr.IsCarried) > 0;

-- USD exposure, dropped by design.
INSERT #Diagnostics
SELECT 'INFO', 'USD exposure dropped (no rate to revalue)', e.Ticker_CCY3,
       CONCAT('Days=', e.Days, '  Delta=', e.Delta_USD_USDDirection)
FROM   #latest_exposure e
WHERE  e.Ticker_CCY3 = 'USD';


/*--------------------------------------------------------------------------
  8.  Output.
--------------------------------------------------------------------------*/

-- The P&L table.
SELECT   Dates, Ticker_CCY3, Delta_USD_USDDirection, DailyPnL, CumDailyPnL, IsCarried
FROM     #DailyPnL
ORDER BY Ticker_CCY3, Dates;

-- Per-currency summary.  CumPnL is the honest period number; SumDailyPnL
-- is the same figure spread across days.
SELECT   Ticker_CCY3,
         MIN(Dates)                AS FirstDate,
         MAX(Dates)                AS LastDate,
         COUNT(*)                  AS Days_Total,
         SUM(CAST(IsCarried AS int)) AS Days_Carried,
         SUM(CASE WHEN DailyPnL IS NULL THEN 1 ELSE 0 END) AS Days_Unpriced,
         MAX(Delta_USD_USDDirection) AS Delta_USD_USDDirection,
         SUM(DailyPnL)             AS SumDailyPnL
FROM     #DailyPnL
GROUP BY Ticker_CCY3
ORDER BY Ticker_CCY3;

-- Portfolio daily P&L.  Safe to group this way only because the table is
-- rectangular -- no currency can go missing from a day's total.
SELECT   Dates,
         SUM(DailyPnL) AS PortfolioDailyPnL,
         SUM(SUM(DailyPnL)) OVER (ORDER BY Dates
                                  ROWS UNBOUNDED PRECEDING) AS PortfolioCumPnL,
         SUM(CASE WHEN DailyPnL IS NULL THEN 1 ELSE 0 END) AS UnpricedCurrencies
FROM     #DailyPnL
GROUP BY Dates
ORDER BY Dates;

-- Issue log.  Read this before trusting the numbers above.
SELECT   Severity, Issue, Ticker_CCY3, Detail
FROM     #Diagnostics
ORDER BY CASE Severity WHEN 'ERROR' THEN 1 WHEN 'WARN' THEN 2 ELSE 3 END,
         Issue, Ticker_CCY3;
