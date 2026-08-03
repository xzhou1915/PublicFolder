/* ============================================================================
   FX correlation regime snapshot
   ----------------------------------------------------------------------------
   Source : dbo.FxRates (DataDate, Ticker, Value)
            Ticker quoted USDXXX; Value = units of XXX per 1 USD.

   Method : 1. invert to XXXUSD and take log returns, computed over consecutive
               JOINT observation dates so both legs span the same interval
            2. rolling Pearson correlation, ST = 60 obs, LT = 240 obs
            3. Spread = Corr_ST - Corr_LT  (full daily series)
            4. ZScore = Spread / STDEV(Spread over trailing 240 obs)
               -- not demeaned: the null is Spread = 0, i.e. ST equals LT
            5. keep the latest computable row per pair

   Read   : ZScore = size of the regime shift, in the pair's own units.
            Corr_ST = where the correlation actually landed (-1 -> 1 vs 0 -> 1).

   Warm-up: 240 (LT) + 240 (std window) = 480 joint observations per pair.
   ============================================================================ */

WITH px AS (
    SELECT
        DataDate,
        Ticker,
        CAST(Value AS FLOAT) AS v
    FROM dbo.FxRates
    WHERE Value > 0
),

/* one row per unordered pair per jointly observed date */
pr AS (
    SELECT
        a.DataDate,
        a.Ticker AS Ticker1,
        b.Ticker AS Ticker2,
        a.v      AS v1,
        b.v      AS v2
    FROM px AS a
    JOIN px AS b
      ON b.DataDate = a.DataDate
     AND b.Ticker   > a.Ticker
),

/* XXXUSD log return = ln(1/V_t) - ln(1/V_t-1) = ln(V_t-1 / V_t)
   LAG partitioned by pair, so returns bridge consecutive joint dates only */
rt AS (
    SELECT
        DataDate,
        Ticker1,
        Ticker2,
        LOG(LAG(v1) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate) / v1) AS x,
        LOG(LAG(v2) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate) / v2) AS y
    FROM pr
),

/* rolling moments; WHERE runs before the window functions, so the frames
   never see the leading NULL-return row */
mom AS (
    SELECT
        DataDate,
        Ticker1,
        Ticker2,
        COUNT(*) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS n60,
        SUM(x)   OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sx60,
        SUM(y)   OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sy60,
        SUM(x*x) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sxx60,
        SUM(y*y) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS syy60,
        SUM(x*y) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sxy60,
        COUNT(*) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS n240,
        SUM(x)   OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS sx240,
        SUM(y)   OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS sy240,
        SUM(x*x) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS sxx240,
        SUM(y*y) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS syy240,
        SUM(x*y) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                       ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS sxy240
    FROM rt
    WHERE x IS NOT NULL
      AND y IS NOT NULL
),

terms AS (
    SELECT
        DataDate, Ticker1, Ticker2, n60, n240,
        n60  * sxy60  - sx60  * sy60   AS cov60,
        n60  * sxx60  - sx60  * sx60   AS varx60,
        n60  * syy60  - sy60  * sy60   AS vary60,
        n240 * sxy240 - sx240 * sy240  AS cov240,
        n240 * sxx240 - sx240 * sx240  AS varx240,
        n240 * syy240 - sy240 * sy240  AS vary240
    FROM mom
),

/* full windows only; variance guards keep SQRT off zero/negative */
rho AS (
    SELECT
        DataDate, Ticker1, Ticker2,
        CASE WHEN n60 = 60 AND varx60 > 0 AND vary60 > 0
             THEN cov60 / SQRT(varx60 * vary60) END AS Corr_ST,
        CASE WHEN n240 = 240 AND varx240 > 0 AND vary240 > 0
             THEN cov240 / SQRT(varx240 * vary240) END AS Corr_LT
    FROM terms
),

spr AS (
    SELECT
        DataDate, Ticker1, Ticker2, Corr_ST, Corr_LT,
        Corr_ST - Corr_LT AS Spread
    FROM rho
),

/* STDEV ignores NULLs, so COUNT(Spread) enforces a genuinely full window */
sprstd AS (
    SELECT
        DataDate, Ticker1, Ticker2, Corr_ST, Corr_LT, Spread,
        STDEV(Spread) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                            ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS SpreadStd,
        COUNT(Spread) OVER (PARTITION BY Ticker1, Ticker2 ORDER BY DataDate
                            ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS nSpread
    FROM spr
),

scored AS (
    SELECT
        DataDate, Ticker1, Ticker2, Corr_ST, Corr_LT, Spread, SpreadStd,
        Spread / NULLIF(SpreadStd, 0) AS ZScore,
        ROW_NUMBER() OVER (PARTITION BY Ticker1, Ticker2
                           ORDER BY DataDate DESC) AS rn
    FROM sprstd
    WHERE nSpread = 240
      AND SpreadStd > 0
)

SELECT
    DataDate,
    SUBSTRING(Ticker1, 4, LEN(Ticker1)) AS CCY1,
    SUBSTRING(Ticker2, 4, LEN(Ticker2)) AS CCY2,
    CAST(Corr_ST   AS DECIMAL(9,4)) AS Corr_ST,
    CAST(Corr_LT   AS DECIMAL(9,4)) AS Corr_LT,
    CAST(Spread    AS DECIMAL(9,4)) AS Spread,
    CAST(SpreadStd AS DECIMAL(9,4)) AS SpreadStd,
    CAST(ZScore    AS DECIMAL(9,3)) AS ZScore
FROM scored
WHERE rn = 1
ORDER BY ABS(ZScore) DESC;
