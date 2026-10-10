-- sql/q2_latest_pages.sql
-- Latest crawl, both clients, one row per origin.
-- PageSpeed presence = detected on ANY client (same rule as q1). info = desktop-preferred
-- among the clients that detected it ('' when the version is hidden). rank = MIN across
-- clients (same as q0). WordPress and cPanel = detected on any client.
WITH per_row AS (
  SELECT
    root_page, client, rank,
    EXISTS (SELECT 1 FROM UNNEST(technologies) AS t WHERE t.technology = 'Google PageSpeed') AS ps,
    (SELECT t.info[SAFE_OFFSET(0)] FROM UNNEST(technologies) AS t
      WHERE t.technology = 'Google PageSpeed' LIMIT 1) AS info,
    EXISTS (SELECT 1 FROM UNNEST(technologies) AS t WHERE t.technology = 'WordPress') AS wp,
    EXISTS (SELECT 1 FROM UNNEST(technologies) AS t WHERE t.technology = 'cPanel') AS cpanel
  FROM `httparchive.crawl.pages`
  WHERE date = @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
),
roots AS (
  SELECT
    root_page,
    LOGICAL_OR(ps) AS pagespeed,
    ARRAY_AGG(IF(ps, IFNULL(info, ''), NULL) IGNORE NULLS
              ORDER BY IF(client = 'desktop', 0, 1) LIMIT 1)[SAFE_OFFSET(0)] AS info,
    MIN(rank) AS rank,
    LOGICAL_OR(wp) AS wordpress,
    LOGICAL_OR(cpanel) AS cpanel
  FROM per_row
  GROUP BY root_page
)
SELECT
  pagespeed,
  IFNULL(info, '') AS info,
  rank,
  wordpress,
  cpanel,
  COUNT(*) AS origins
FROM roots
GROUP BY 1, 2, 3, 4, 5
ORDER BY origins DESC
