# Methodology

## Unit and source

One row of this census is an **origin**: the root page of a site (scheme, host, `/`). Every number
comes from the monthly HTTP Archive crawl, read in BigQuery from `httparchive.crawl.pages` and
`httparchive.crawl.requests`, filtered to root pages. The desktop and mobile crawls are combined
per origin. When both report a value for one origin, the desktop value is used. `disagreements.csv`
counts origins whose detecting clients reported different version strings. A client that did not
detect PageSpeed at all is not a disagreement.

## Detection

An origin counts as PageSpeed-serving when HTTP Archive's technology detection records
`Google PageSpeed` on its root page. The version string is the value of the response header the
module sends: `X-Mod-Pagespeed` for the Apache module, `X-Page-Speed` for the nginx module.

Detection misses pages that send the header. In the latest desktop crawl, `detection.csv` splits the
header-bearing root pages by signal: seen by both, seen by the header only, seen by detection only.
Detection flags roughly four in five of the pages that send a PageSpeed header, so the
detection-based series is a floor. The raw-header count for the latest crawl is about a quarter
higher than the detection count. Earlier crawls were not cross-checked.

## Version buckets

| Bucket | Rule | Anchor |
|---|---|---|
| Google-era builds | version up to 1.13.35.2, and any later 1.13.x patch | `1.13.35.2-stable`, 5 February 2018 |
| Incubator-era builds | 1.14.x releases and unreleased trunk builds that report `1.15.0.0-<revision>` | `1.14.36.1`, July 2020 |
| Current line | major 1, exactly three numeric components, 1.15.0 or later (a suffix such as `+r19` is allowed) | `1.15.0`, June 2026 |
| Version hidden | header present, no module version | reported as hidden; not counted as unpatched |

A version is the leading run of three or four dot-separated numbers in the header value. Releases
of the current line carry three numbers. A value with four numbers at 1.15.0.0 or later is a build
of the old incubator trunk, which was never released, and is counted as incubator-era. Version
strings that are not module versions are treated as hidden: values with no parseable version, and
values with a major version of 2 or more, which this census does not read as versions of the 1.x
line and counts as hidden. `distribution.csv` lists a three-number version as written (`1.15.0`)
and a four-number version without its revision suffix (`1.15.0.0`).

The Google-era and incubator-era buckets are both out of fixes. The out-of-fixes share is computed
over origins that report a version. Because some origins hide their version, the true share
across all PageSpeed origins is unknown, in either direction.

## Series

`series.csv` starts at the crawl given by `--start` (default `2020-12-01`) and ends with the crawl
named in `census.json`. The denominator `all_origins` is the number of distinct root pages in each
crawl, both clients combined.

## Ranks, servers, co-occurrence

`ranks.csv` uses HTTP Archive's rank magnitude buckets (top 1k up to top 50M). HTTP Archive's rank
is empty for early crawls: in the data used here the first crawl with a rank is 2021-03-01, so
rank-based figures exist only from that date. Origins without a rank fall in the `unranked` row,
which is empty in the latest crawl. HTTP Archive's rank is the smallest magnitude bucket an origin
falls in, so the buckets are exclusive bands and the rows of `ranks.csv` sum to the total; the chart
labels them as bands.

`servers.csv` pairs the module's header with the family of the `Server` header on the same
response (desktop crawl). The module header name is the engine signal: `X-Mod-Pagespeed` is the
Apache module and `X-Page-Speed` is the nginx module. The `Server` header names the front-most
server, which is not always the one running the module. The Apache module also appears behind an
nginx front and behind Cloudflare; the `apache-module` rows of `servers.csv` give the counts. Read
the Server family as context, not as the engine.

`cooccurrence.csv` reports WordPress and cPanel detection on PageSpeed-serving origins against all
origins. The table shows zero cPanel detections among PageSpeed origins and very few across all
origins (`cpanel_origins` in `cooccurrence.csv`), so cPanel cannot be measured this way. Do not
read that as "no PageSpeed site runs cPanel". It is a limit of the detection, not a finding about
hosting.

## Networks

`networks_top10.csv` lists the ten largest networks by share of header-bearing desktop root
pages with an attributable IP in the latest desktop crawl.

- **Denominator.** Header-bearing desktop root pages with an attributable IP. The `coverage` block
  of `rib-snapshot.json` gives the rows read, the rows with an IP and the rows mapped to a network.
  This is not the larger headline union of desktop and mobile origins.
- **Which IP.** The IP comes from the crawl's own request record for the root page. It is the
  front-most address, so a site behind a CDN is attributed to the CDN. That is why
  CDNs appear in `networks_top10.csv`. The table shows where sites are served from, not
  where they are hosted.
- **Mapping.** IPs are mapped to networks with a routing snapshot. The prefixes come from a
  RouteViews RIB (IPv4 and IPv6, `--latestv46`). The network names come from the CIDR Report
  AS-name list, fetched with pyasn's `pyasn_util_asnames.py`. The snapshot was fetched on the date
  in `rib-snapshot.json`, which is later than the crawl. IPv6 addresses arrive bracketed in the
  archive and are unbracketed before lookup. The file's hashes identify the snapshot used.
- **Pinned snapshot.** Routing tables and network names change daily, so the network table
  reproduces only with the snapshot this release used. It is attached to the GitHub release of the
  crawl and is passed to `census networks` with `--snapshot-dir`.
- **Method field.** `attribution_method` is `httparchive-payload-ip`. The value `dns-fallback` is
  reserved for a disclosed DNS-only fallback. It was not needed.
- Only shares are published. No origin was contacted to produce this table.

## Billing record

`billing.json` lists the bytes each query scanned, in run order. Reproducing this release scans
about 1.28 TB (the sum of the last record per step).

## Limits

- Counts across crawls are not directly comparable because the crawl grew; use `share` and
  `all_origins` in `series.csv`.
- Site counts from technology-profiling services use other methods and samples and are not
  comparable with this census.
- The split between version-reporting and version-hidden origins shifts abruptly between some
  crawls. The three largest month-over-month moves of the hidden bucket are at the 2021-02-01,
  2021-07-01 and 2023-01-01 crawls. In each, the version-reporting count moves the other way by a
  similar amount. The census does not establish the cause.
- HTTP Archive covers sites that appear in Chrome's popularity data. Sites outside it are not
  counted. This census measures that sample, not the whole web.
- A hidden or altered header means the versioned count is a floor on the real base.
- Detection recall is below 100% (see Detection), so counts are floors.
- Technology-detection rules change over time. The recall cross-check covers the latest crawl only.
- cPanel co-occurrence cannot be measured this way (see above).
- Network shares describe the front-most address, not the hosting provider.
- Desktop and mobile coverage differ. The combination rule is stated so the numbers can be
  reproduced.

## Reproduce

You need `gcloud auth application-default login` on a Google Cloud project with BigQuery enabled.
Queries are billed to the project named in the environment variable `CENSUS_BQ_PROJECT`; when it
is unset, the application-default project is used. `--start` defaults to `2020-12-01`.

Download the pinned routing snapshot from the GitHub release of the crawl and unpack it into a
directory (`ipasn.dat`, `asnames.json`, `rib-fetched-at.txt`).

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

`dry-run` prints the bytes each query would scan and spends nothing. `run` and `networks` execute
under byte caps. `verify` compares every regenerated table and chart with the committed
`SHA256SUMS`, lists each file that differs and exits non-zero if any does. Do not run
`census manifest` before it: `manifest` rewrites `SHA256SUMS` from the files on disk and is the
maintainer's step when publishing a new crawl. The raw query results stay in the untracked `work/`
directory.

Without the pinned snapshot, `networks` downloads the routing table of the day and the network
table differs. `verify` then reports the files that differ.

## Acknowledgements

Crawl data: HTTP Archive. Routing prefixes: the University of Oregon RouteViews project. Network
names: the CIDR Report AS-name list. Both are read with pyasn.

## Cite

"The state of the PageSpeed installed base", We-Amp B.V. Data licensed CC BY 4.0.
https://github.com/We-Amp/pagespeed-census
