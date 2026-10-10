"""Inline SVG chart fragments for the post. Deterministic, origin-free, theme-aware.

One accent (the site's `--color-interactive`) for every data mark, neutral gray for the
`hidden` bucket. Ink/grid/axis come from the site's CSS variables, so the fragments follow
the page theme when inlined. The site's dark mode is the `.dark` class on <html>.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from census.buckets import BUCKETS

STYLE = """<style>
svg.census{--census-accent:var(--color-interactive,#0e6f89);--census-gray:#8a8478;\
--census-ink:var(--color-text-body,#15171a);--census-muted:var(--color-text-muted,#55606b);\
--census-grid:var(--color-border,#e2ded7);--census-axis:var(--color-border-strong,#cfcabf);\
font-family:inherit;font-size:12px}
.dark svg.census{--census-gray:#8a9099}
svg.census .census-grid{stroke:var(--census-grid);stroke-width:1}
svg.census .census-axis{stroke:var(--census-axis);stroke-width:1}
svg.census .census-line{fill:none;stroke:var(--census-accent);stroke-width:2;\
stroke-linejoin:round;stroke-linecap:round}
svg.census .census-line[data-bucket="hidden"]{stroke:var(--census-gray)}
svg.census .census-bar{fill:var(--census-accent)}
svg.census .census-bar[data-bucket="hidden"]{fill:var(--census-gray)}
svg.census .census-point{fill:transparent}
svg.census text{fill:var(--census-muted)}
svg.census .census-label,svg.census .census-panel-title{fill:var(--census-ink)}
svg.census .census-panel-title{font-weight:600}
</style>"""

BUCKET_NAME = {
    "google-era": "Google-era builds",
    "incubator-era": "Incubator-era builds",
    "current": "Current line",
    "hidden": "Version hidden",
}
BUCKET_SHORT = {
    "google-era": "Google era",
    "incubator-era": "Incubator era",
    "current": "current",
    "hidden": "hidden",
}


RANK_BAND_LABELS = {
    "top 1k": "top 1k",
    "top 5k": "1k\u20135k",
    "top 10k": "5k\u201310k",
    "top 50k": "10k\u201350k",
    "top 100k": "50k\u2013100k",
    "top 500k": "100k\u2013500k",
    "top 1M": "500k\u20131M",
    "top 5M": "1M\u20135M",
    "top 10M": "5M\u201310M",
    "top 50M": "10M\u201350M",
    "unranked": "unranked",
}


def _fmt(n: float, share: bool = False) -> str:
    return f"{n * 100:.1f}%" if share else f"{int(n):,}"


def _axis_fmt(n: float, share: bool = False) -> str:
    if share:
        pct = n * 100
        return f"{pct:g}%"
    return f"{int(n):,}"


def _nice_ceiling(v: float) -> float:
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= v:
            return m * mag
    return 10 * mag


def _open(width: int, height: int, title: str, desc: str, slug: str) -> str:
    return (
        f'<svg class="census" role="img" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="100%" '
        f'aria-labelledby="census-{slug}-title census-{slug}-desc">'
        f'{STYLE}<title id="census-{slug}-title">{escape(title)}</title>'
        f'<desc id="census-{slug}-desc">{escape(desc)}</desc>'
    )


def series_svg(series_rows: list[dict], width: int = 720) -> str:
    dates = sorted({r["date"] for r in series_rows})
    by: dict[str, dict[str, int]] = {b: {} for b in BUCKETS}
    for r in series_rows:
        by[r["bucket"]][r["date"]] = int(r["origins"])
    left, right, top, bottom = 56, 24, 20, 36
    panel_h, gap = 96, 36
    pw = width - left - right
    height = top + len(BUCKETS) * panel_h + (len(BUCKETS) - 1) * gap + bottom

    def x(i: int) -> float:
        return left + (pw * i / max(len(dates) - 1, 1))

    out = [_open(width, height, "PageSpeed-serving origins per monthly crawl, by build era",
                 f"Four small line charts from {dates[0]} to {dates[-1]}, one per era bucket, "
                 "each with its own vertical scale.", "series")]
    titles = []
    body = []
    for n, b in enumerate(BUCKETS):
        p_top = top + n * (panel_h + gap)
        ymax = _nice_ceiling(max(by[b].values(), default=0))

        def y(v: float, p_top: int = p_top, ymax: float = ymax) -> float:
            return p_top + panel_h - panel_h * v / ymax

        titles.append(f'<text class="census-panel-title" x="{left}" y="{p_top - 8}">'
                      f"{escape(BUCKET_NAME[b])}</text>")
        for k in range(3):
            gy = p_top + panel_h * k / 2
            cls = "census-axis" if k == 2 else "census-grid"
            body.append(f'<line class="{cls}" x1="{left}" y1="{gy:.1f}" x2="{left + pw}" y2="{gy:.1f}"/>')
            body.append(f'<text x="{left - 8}" y="{gy + 4:.1f}" text-anchor="end">'
                        f"{_axis_fmt(ymax * (2 - k) / 2)}</text>")
        pts = [(x(i), y(by[b].get(d, 0))) for i, d in enumerate(dates)]
        d_attr = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        hid = ' data-bucket="hidden"' if b == "hidden" else ""
        body.append(f'<path class="census-line"{hid} d="{d_attr}"/>')
        for (px, py), d in zip(pts, dates, strict=True):
            body.append(
                f'<circle class="census-point" cx="{px:.1f}" cy="{py:.1f}" r="6"><title>'
                f"{escape(BUCKET_NAME[b])}, {d}: {_fmt(by[b].get(d, 0))} origins</title></circle>"
            )
    out.append('<g class="census-legend">' + "".join(titles) + "</g>")
    out.extend(body)
    base = top + len(BUCKETS) * panel_h + (len(BUCKETS) - 1) * gap
    for i, d in enumerate(dates):
        if d.endswith("-01-01"):
            out.append(f'<text x="{x(i):.1f}" y="{base + 20}" text-anchor="middle">{d[:4]}</text>')
    out.append("</svg>")
    return "".join(out)


def bars_svg(rows: list[dict], *, label_key: str, value_key: str, title: str, desc: str,
             color_key: str | None = None, value_is_share: bool = False, width: int = 720,
             slug: str = "bars") -> str:
    pitch, bar_h, left, right, top = 28, 18, 250, 24, 16
    height = top + pitch * len(rows) + 16
    values = [float(r[value_key]) for r in rows]
    vmax = _nice_ceiling(max(values) if values else 1.0)
    pw = width - left - right
    out = [_open(width, height, title, desc, slug)]
    out.append(f'<line class="census-axis" x1="{left}" y1="{top}" x2="{left}" '
               f'y2="{top + pitch * len(rows)}"/>')
    for i, r in enumerate(rows):
        v = float(r[value_key])
        y0 = top + i * pitch + (pitch - bar_h) / 2
        label = str(r[label_key])
        hid = ' data-bucket="hidden"' if color_key and r.get(color_key) == "hidden" else ""
        if v > 0:  # a zero value draws no bar at all
            w = max(pw * v / vmax, 1.0)
            x1 = left + w
            rad = f"{min(4.0, w):g}"  # a bar narrower than its corner keeps right of the axis
            d = (f"M{left} {y0:.1f} H{x1 - float(rad):.1f} a{rad} {rad} 0 0 1 {rad} {rad} "
                 f"v{bar_h - 2 * float(rad):g} a{rad} {rad} 0 0 1 -{rad} {rad} H{left} Z")
            out.append(f'<path class="census-bar"{hid} d="{d}"><title>{escape(label)}: '
                       f"{_fmt(v, value_is_share)}</title></path>")
        lx = left - 8
        if color_key and r.get(color_key):
            era = BUCKET_SHORT.get(r[color_key], str(r[color_key]))
            out.append(f'<text class="census-era" x="{lx}" y="{y0 + bar_h - 4:.1f}" '
                       f'text-anchor="end">{escape(era)}</text>')
            lx -= int(len(era) * 6.5) + 10
        out.append(f'<text class="census-label" x="{lx}" y="{y0 + bar_h - 4:.1f}" '
                   f'text-anchor="end">{escape(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def _trunc(s: str, n: int = 28) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def render_all(census: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = census["tables"]
    files = {
        "series.svg": series_svg(t["series"]),
        "distribution.svg": bars_svg(
            t["distribution"][:12], label_key="version", value_key="origins",
            title="Origins per reported version, latest crawl",
            desc="Horizontal bars, one per version string, with its era beside the label.",
            color_key="bucket", slug="distribution"),
        "ranks.svg": bars_svg(
            [{**r, "rank": RANK_BAND_LABELS[r["rank"]]}
             for r in t["ranks"] if r.get("all_origins") != "0"],
            label_key="rank", value_key="share",
            title="PageSpeed share within each exclusive rank band",
            desc="Horizontal bars of the share of origins per exclusive rank band that serve PageSpeed.",
            value_is_share=True, slug="ranks"),
        "networks.svg": bars_svg(
            [{"network": _trunc(r["network"]), "share": str(float(r["share_pct"]) / 100)}
             for r in t["networks_top10"]],
            label_key="network", value_key="share",
            title="Ten largest networks by share of PageSpeed-serving origins",
            desc="Horizontal bars of network share, latest crawl, desktop.",
            value_is_share=True, slug="networks"),
    }
    paths = []
    for name, svg in files.items():
        p = out_dir / name
        p.write_text(svg + "\n", encoding="utf-8")
        paths.append(p)
    return paths
