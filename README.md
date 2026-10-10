# pagespeed-census

A reproducible census of the mod_pagespeed / ngx_pagespeed installed base, built from
[HTTP Archive](https://httparchive.org/) crawl data in BigQuery. It publishes aggregates only:
no origins, no hostnames, no IP addresses.

Maintained by We-Amp B.V. Code: Apache-2.0 (`LICENSE`). Data and charts: CC BY 4.0 (`LICENSE-DATA`).
How the numbers are made, and what they cannot tell you: `METHODOLOGY.md`.
The write-up of the 2026-09-01 crawl: https://modpagespeed.com/blog/pagespeed-installed-base-2026/

## What is published

For each crawl, in `data/<date>/`:

- `series.csv`: origins per version bucket, per month.
- `disagreements.csv`: origins whose detecting clients reported different versions.
- `distribution.csv`: origins per reported version, with its bucket, for the crawl.
- `ranks.csv`: PageSpeed origins by HTTP Archive rank bucket.
- `cooccurrence.csv`: WordPress and cPanel detection, PageSpeed origins against all origins.
- `servers.csv`: module engine against the `Server` header family.
- `detection.csv`: how many header-bearing pages technology detection flags.
- `networks_top10.csv`: the ten largest networks by share (shares only).
- `census.json`: all tables above plus the headline figures, in one file.
- `billing.json`: what each query scanned, in run order.
- `rib-snapshot.json`: which routing snapshot was used and how many IPs it mapped.
- `SHA256SUMS`: hashes of the CSVs, `census.json` and the charts. `census verify` checks them.

Charts are in `charts/<date>/*.svg`.

## What is not published

Origins, hostnames, IP addresses, and the per-network version split. `census guard` scans the
published files for origins, hostnames and IP addresses and fails if any appear. The network table
carries shares only.

## Reproduce

You need `gcloud auth application-default login` on a Google Cloud project with BigQuery enabled.
Queries are billed to the project named in the environment variable `CENSUS_BQ_PROJECT`; when it
is unset, the application-default project is used. `--start` defaults to `2020-12-01`.

The network table depends on a routing snapshot. It reproduces only with the pinned snapshot
attached to the GitHub release of this crawl (`ipasn.dat`, `asnames.json`, `rib-fetched-at.txt`).
Unpack it into a directory and pass that directory as `--snapshot-dir`.

```
uv sync
uv run census dry-run --date <crawl>
uv run census run --date <crawl> --execute
uv run census aggregate --date <crawl>
uv run census networks --date <crawl> --execute --snapshot-dir <snapshot-dir>
uv run census charts --date <crawl>
uv run census verify --date <crawl>
uv run census guard
```

`dry-run` spends nothing. `run` and `networks` execute under byte caps. `verify` checks the
regenerated tables and charts against the committed `SHA256SUMS` and lists every file that differs.
`census manifest` rewrites `SHA256SUMS`; it is the maintainer's step when publishing a new crawl,
not part of a reproduction.

Without `--snapshot-dir`, `networks` downloads the routing table of the day, which gives a
different network table.

## Acknowledgements

Crawl data: [HTTP Archive](https://httparchive.org/). Routing prefixes: the University of Oregon
[RouteViews](https://www.routeviews.org/) project. Network names: the
[CIDR Report](https://www.cidr-report.org/) AS-name list. Both are read with
[pyasn](https://github.com/hadiasghari/pyasn).

## Cite

We-Amp B.V., "The state of the PageSpeed installed base". Data: CC BY 4.0.
https://github.com/We-Amp/pagespeed-census
