-- Latest crawl, desktop, root-page main documents that send a PageSpeed header:
-- one row per origin with its IP from the WebPageTest request record.
-- OUTPUT IS PER-ORIGIN: written to work/ only, never to data/.
-- type = 'html' is redundant with is_main_document but lets BigQuery prune by cluster
-- (dry run 2026-10-10: 0.40 TB with it, 1.1 TB without).
SELECT
  root_page,
  (SELECT value FROM UNNEST(response_headers)
    WHERE LOWER(name) IN ('x-mod-pagespeed', 'x-page-speed') LIMIT 1) AS ps_value,
  JSON_VALUE(payload, '$.ip_addr') AS ip_addr,
  JSON_VALUE(payload, '$._ip_addr') AS ip_addr_alt
FROM `httparchive.crawl.requests`
WHERE date = @crawl_date
  AND client = 'desktop'
  AND is_root_page
  AND is_main_document
  AND type = 'html'
  AND EXISTS (SELECT 1 FROM UNNEST(response_headers) AS h
              WHERE LOWER(h.name) IN ('x-mod-pagespeed', 'x-page-speed'))
