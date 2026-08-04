/* ============================================================================
   FX average pairwise correlation — 5 daily time series
   ----------------------------------------------------------------------------
   Source : dbo.FxRates (DataDate, Ticker, Value)   -- same input as
            fx_corr_regime_snapshot.sql, same ticker cleaning
            'USDJPY CMPN Curncy' | 'JPY Curncy' | 'USDJPY'  ->  JPY

   Method : rolling 60-observation correlation of daily XXXUSD log returns for
            every pair, averaged across pairs on each date.
              All   = every pair in the mapped universe
              G10 / Asia / EMEA / Latam = pairs whose BOTH legs sit in that basket

   Output : one row per DataDate per basket (long form; pivot at the bottom)
              AvgCorr           mean pairwise correlation
              MedCorr           median — diverges from the mean when a few
                                devaluation-driven pairs skew the basket
              PairCount         pairs actually contributing that day
              PairsWithBigMove  pairs whose window holds a >10% single-day move

   Quality: a pair is dropped for a given day when either leg has >30% exactly
            zero returns in its 60-day window (pegs, crawls, stale quotes).
            That is why PairCount must be read alongside AvgCorr — a step in
            the average that coincides with a step in PairCount is coverage
            changing, not correlation.

   Warm-up: 60 joint observations, so ~late March 2023 on data starting 2023-01.
   ============================================================================ */

WITH raw AS (
    SELECT
        DataDate,
        LTRIM(RTRIM(Ticker)) AS tk,
        CAST(Value AS FLOAT) AS v
    FROM dbo.FxRates
    WHERE Value > 0
),

tok AS (
    SELECT DataDate, UPPER(LEFT(tk, CHARINDEX(' ', tk + ' ') - 1)) AS t, v
    FROM raw
),

px AS (
    SELECT
        DataDate,
        CASE WHEN LEN(t) > 3 AND LEFT(t, 3) = 'USD'
             THEN SUBSTRING(t, 4, LEN(t))
             ELSE t END AS Ccy,
        v
    FROM tok
),

/* Basket membership. Edit here — this list also DEFINES the universe:
   any currency in the source table but absent below is excluded from every
   series, including 'All'. */
map AS (
    SELECT Ccy, Basket FROM (VALUES
        ('EUR','G10'  ),('JPY','G10'  ),('GBP','G10'  ),('CHF','G10'  ),
        ('AUD','G10'  ),('NZD','G10'  ),('CAD','G10'  ),('NOK','G10'  ),
        ('SEK','G10'  ),
        ('CNH','Asia' ),('KRW','Asia' ),('TWD','Asia' ),('INR','Asia' ),
        ('SGD','Asia' ),('THB','Asia' ),('MYR','Asia' ),('IDR','Asia' ),
        ('PHP','Asia' ),('VND','Asia' ),
        ('PLN','EMEA' ),('HUF','EMEA' ),('CZK','EMEA' ),('TRY','EMEA' ),
        ('ZAR','EMEA' ),('ILS','EMEA' ),('UAH','EMEA' ),('RUB','EMEA' ),
        ('RON','EMEA' ),('NGN','EMEA' ),('KZT','EMEA' ),('EGP','EMEA' ),
        ('BRL','Latam'),('MXN','Latam'),('CLP','Latam'),('COP','Latam'),
        ('PEN','Latam')
    ) AS v (Ccy, Basket)
),

uni AS (
    SELECT p.DataDate, p.Ccy, p.v
    FROM px  AS p
    JOIN map AS m ON m.Ccy = p.Ccy
),

/* one row per unordered pair per jointly observed date */
pr AS (
    SELECT
        a.DataDate,
        a.Ccy AS Ccy1, b.Ccy AS Ccy2,
        a.v   AS v1,   b.v   AS v2
    FROM uni AS a
    JOIN uni AS b
      ON b.DataDate = a.DataDate
     AND b.Ccy      > a.Ccy
),

/* XXXUSD log return = ln(V_t-1 / V_t); LAG partitioned by pair so both legs
   span the identical interval across mismatched holiday calendars */
rt AS (
    SELECT
        DataDate, Ccy1, Ccy2,
        LOG(LAG(v1) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate) / v1) AS x,
        LOG(LAG(v2) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate) / v2) AS y
    FROM pr
),

/* rolling 60-observation moments plus the two data-quality counters.
   WHERE runs before the window functions, so the leading NULL row is excluded
   from every frame. */
mom AS (
    SELECT
        DataDate, Ccy1, Ccy2,
        COUNT(*) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS n,
        SUM(x)   OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sx,
        SUM(y)   OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sy,
        SUM(x*x) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sxx,
        SUM(y*y) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS syy,
        SUM(x*y) OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS sxy,
        SUM(CASE WHEN ABS(x) < 1e-12 THEN 1 ELSE 0 END)
                 OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS zx,
        SUM(CASE WHEN ABS(y) < 1e-12 THEN 1 ELSE 0 END)
                 OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS zy,
        MAX(CASE WHEN ABS(x) > 0.10 OR ABS(y) > 0.10 THEN 1 ELSE 0 END)
                 OVER (PARTITION BY Ccy1, Ccy2 ORDER BY DataDate
                       ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS big
    FROM rt
    WHERE x IS NOT NULL
      AND y IS NOT NULL
),

terms AS (
    SELECT
        DataDate, Ccy1, Ccy2, n, zx, zy, big,
        n * sxy - sx * sy AS cov,
        n * sxx - sx * sx AS varx,
        n * syy - sy * sy AS vary
    FROM mom
),

/* full window, non-degenerate variance, and neither leg more than 30% flat
   (18 of 60 observations) */
rho AS (
    SELECT
        DataDate, Ccy1, Ccy2, big,
        CASE WHEN n = 60 AND varx > 0 AND vary > 0 AND zx <= 18 AND zy <= 18
             THEN cov / SQRT(varx * vary) END AS r
    FROM terms
),

ok AS (
    SELECT DataDate, Ccy1, Ccy2, r, big
    FROM rho
    WHERE r IS NOT NULL
),

/* every surviving pair contributes to 'All'; it additionally contributes to a
   regional basket only when BOTH legs belong to that basket */
tagged AS (
    SELECT DataDate, 'All' AS Basket, r, big
    FROM ok
    UNION ALL
    SELECT o.DataDate, m1.Basket, o.r, o.big
    FROM ok  AS o
    JOIN map AS m1 ON m1.Ccy = o.Ccy1
    JOIN map AS m2 ON m2.Ccy = o.Ccy2
                  AND m2.Basket = m1.Basket
)

/* PERCENTILE_CONT exists only as an analytic function in T-SQL, so the group
   is collapsed with DISTINCT over matching PARTITION BY clauses rather than
   GROUP BY */
SELECT DISTINCT
    DataDate,
    Basket,
    CAST(AVG(r) OVER (PARTITION BY DataDate, Basket) AS DECIMAL(9,4)) AS AvgCorr,
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r)
             OVER (PARTITION BY DataDate, Basket) AS DECIMAL(9,4))    AS MedCorr,
    COUNT(*)  OVER (PARTITION BY DataDate, Basket)                    AS PairCount,
    SUM(big)  OVER (PARTITION BY DataDate, Basket)                    AS PairsWithBigMove
FROM tagged
ORDER BY DataDate, Basket;


/* ----------------------------------------------------------------------------
   Wide form for plotting — wrap the statement above as a CTE named s:

   SELECT DataDate,
          MAX(CASE WHEN Basket = 'All'   THEN AvgCorr END) AS [All],
          MAX(CASE WHEN Basket = 'G10'   THEN AvgCorr END) AS G10,
          MAX(CASE WHEN Basket = 'Asia'  THEN AvgCorr END) AS Asia,
          MAX(CASE WHEN Basket = 'EMEA'  THEN AvgCorr END) AS EMEA,
          MAX(CASE WHEN Basket = 'Latam' THEN AvgCorr END) AS Latam
   FROM   s
   GROUP  BY DataDate
   ORDER  BY DataDate;
---------------------------------------------------------------------------- */

/* ----------------------------------------------------------------------------
   Run first: confirm every source ticker maps to a currency that appears in
   the basket list. Anything with Basket = NULL is silently absent from all
   five series.

   SELECT DISTINCT q.Ticker, q.Ccy, m.Basket
   FROM  (SELECT Ticker,
                 CASE WHEN LEN(t) > 3 AND LEFT(t,3) = 'USD'
                      THEN SUBSTRING(t,4,LEN(t)) ELSE t END AS Ccy
          FROM  (SELECT Ticker,
                        UPPER(LEFT(LTRIM(RTRIM(Ticker)),
                              CHARINDEX(' ', LTRIM(RTRIM(Ticker)) + ' ') - 1)) AS t
                 FROM dbo.FxRates) AS a) AS q
   LEFT JOIN (SELECT Ccy, Basket FROM (VALUES
             ('EUR','G10'),('JPY','G10'),('GBP','G10'),('CHF','G10'),('AUD','G10'),
             ('NZD','G10'),('CAD','G10'),('NOK','G10'),('SEK','G10'),
             ('CNH','Asia'),('KRW','Asia'),('TWD','Asia'),('INR','Asia'),('SGD','Asia'),
             ('THB','Asia'),('MYR','Asia'),('IDR','Asia'),('PHP','Asia'),('VND','Asia'),
             ('PLN','EMEA'),('HUF','EMEA'),('CZK','EMEA'),('TRY','EMEA'),('ZAR','EMEA'),
             ('ILS','EMEA'),('UAH','EMEA'),('RUB','EMEA'),('RON','EMEA'),('NGN','EMEA'),
             ('KZT','EMEA'),('EGP','EMEA'),
             ('BRL','Latam'),('MXN','Latam'),('CLP','Latam'),('COP','Latam'),('PEN','Latam')
             ) AS v (Ccy, Basket)) AS m ON m.Ccy = q.Ccy
   ORDER BY m.Basket, q.Ccy;
---------------------------------------------------------------------------- */
