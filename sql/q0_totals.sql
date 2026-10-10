-- Denominators: distinct root pages per crawl (union of desktop and mobile) and per rank.
-- rank can differ between clients for one origin; MIN keeps the better (smaller) rank.
WITH roots AS (
  SELECT date, root_page, MIN(rank) AS rank
  FROM `httparchive.crawl.pages`
  WHERE date BETWEEN @start_date AND @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
  GROUP BY date, root_page
)
SELECT date, rank, COUNT(*) AS origins
FROM roots
GROUP BY date, rank
ORDER BY date, rank
