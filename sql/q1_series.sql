-- rank = MIN across ALL client rows of the origin (before the PageSpeed filter), exactly like q0.
-- PageSpeed-serving origins per crawl, by the Wappalyzer info value (version string or marker),
-- deduplicated per origin across clients with desktop preferred; disagreements counted.
WITH ranks AS (
  SELECT date, root_page, MIN(rank) AS rank
  FROM `httparchive.crawl.pages`
  WHERE date BETWEEN @start_date AND @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
  GROUP BY date, root_page
),
ps AS (
  SELECT
    date, client, root_page,
    (SELECT t.info[SAFE_OFFSET(0)]
       FROM UNNEST(technologies) AS t
      WHERE t.technology = 'Google PageSpeed' LIMIT 1) AS info
  FROM `httparchive.crawl.pages`
  WHERE date BETWEEN @start_date AND @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
    AND EXISTS (SELECT 1 FROM UNNEST(technologies) AS t WHERE t.technology = 'Google PageSpeed')
),
per_origin AS (
  SELECT
    date, root_page,
    ARRAY_AGG(info ORDER BY IF(client = 'desktop', 0, 1) LIMIT 1)[OFFSET(0)] AS info,
    COUNT(DISTINCT IFNULL(info, '')) > 1 AS disagree
  FROM ps
  GROUP BY date, root_page
)
SELECT
  date,
  IFNULL(info, '') AS info,
  rank,
  COUNT(*) AS origins,
  COUNTIF(disagree) AS disagreements
FROM per_origin
JOIN ranks USING (date, root_page)
GROUP BY date, info, rank
ORDER BY date, origins DESC
