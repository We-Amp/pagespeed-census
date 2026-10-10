-- Latest crawl, both clients, root-page main documents: the PageSpeed header actually sent
-- (name + value), the Server header, and whether Wappalyzer detected PageSpeed on the same
-- origin. Aggregated: never one row per origin.
WITH hdr AS (
  SELECT
    client, root_page,
    (SELECT LOWER(name) FROM UNNEST(response_headers)
      WHERE LOWER(name) IN ('x-mod-pagespeed', 'x-page-speed') LIMIT 1) AS ps_header,
    (SELECT value FROM UNNEST(response_headers)
      WHERE LOWER(name) IN ('x-mod-pagespeed', 'x-page-speed') LIMIT 1) AS ps_value,
    (SELECT value FROM UNNEST(response_headers) WHERE LOWER(name) = 'server' LIMIT 1) AS server
  FROM `httparchive.crawl.requests`
  WHERE date = @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
    AND is_main_document
),
det AS (
  SELECT client, root_page, TRUE AS wappalyzer
  FROM `httparchive.crawl.pages`
  WHERE date = @crawl_date
    AND client IN ('desktop', 'mobile')
    AND is_root_page
    AND EXISTS (SELECT 1 FROM UNNEST(technologies) AS t WHERE t.technology = 'Google PageSpeed')
)
SELECT
  client,
  IFNULL(ps_header, '') AS ps_header,
  IFNULL(ps_value, '') AS ps_value,
  IFNULL(server, '') AS server,
  IFNULL(wappalyzer, FALSE) AS wappalyzer,
  COUNT(*) AS origins
FROM hdr
FULL OUTER JOIN det USING (client, root_page)
WHERE ps_header IS NOT NULL OR wappalyzer
GROUP BY 1, 2, 3, 4, 5
ORDER BY origins DESC
