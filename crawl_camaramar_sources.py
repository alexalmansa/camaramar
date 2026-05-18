#!/usr/bin/env python3
import csv
import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"


@dataclass
class CameraRow:
    url: str
    path: str
    title: str
    status: str
    source_type: str
    source_count: int
    source_urls: str
    providers: str
    note: str
    http_status: str
    error: str


def read_urls(path: Path) -> List[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            urls.append(line)
    return urls


def fetch_html(url: str, timeout: int = 30) -> str:
    # Keep headers minimal to avoid Brotli payloads that urllib may not decode.
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        # urllib transparently handles gzip/deflate for most responses;
        # fallback decode as utf-8 with replacement.
        return raw.decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_webcam_block(doc: str) -> str:
    # Extract only the main webcam media segment, not the nearby-cameras section.
    m = re.search(r'<div id="webcam"[^>]*>', doc, flags=re.I)
    if not m:
        return ""
    tail = doc[m.end() :]

    fig = re.search(r"<figure\b[\s\S]*?</figure>", tail, flags=re.I)
    if fig:
        return fig.group(0)

    # Some pages have an empty webcam container; grab a short tail so caller can
    # still infer "no embed".
    return tail[:1500]


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def extract_sources(block: str) -> List[str]:
    found = []

    # Direct iframe embeds.
    found += re.findall(r'<iframe[^>]+src="(https?://[^"]+)"', block, flags=re.I)

    # HTML5 source tags.
    found += re.findall(r'<source[^>]+src="(https?://[^"]+)"', block, flags=re.I)

    # Video.js style: player.src({ src: '...' })
    found += re.findall(r"player\.src\(\{\s*src:\s*'([^']+)'", block, flags=re.I)
    found += re.findall(r'player\.src\(\{\s*src:\s*"([^"]+)"', block, flags=re.I)

    # Dash.js style: const url = "..."
    found += re.findall(r'const\s+url\s*=\s*"([^"]+)"', block, flags=re.I)
    found += re.findall(r"const\s+url\s*=\s*'([^']+)'", block, flags=re.I)

    # Generic player config patterns used by various libs.
    found += re.findall(r'\bsource\s*:\s*"(https?://[^"]+)"', block, flags=re.I)
    found += re.findall(r"\bsource\s*:\s*'(https?://[^']+)'", block, flags=re.I)
    found += re.findall(r'\bfile\s*:\s*"(https?://[^"]+)"', block, flags=re.I)
    found += re.findall(r"\bfile\s*:\s*'(https?://[^']+)'", block, flags=re.I)

    # Data attributes.
    found += re.findall(r'data-video="(https?://[^"]+)"', block, flags=re.I)
    found += re.findall(r"data-video='(https?://[^']+)'", block, flags=re.I)

    # Fallback direct manifest links present in inline scripts.
    found += re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', block, flags=re.I)
    found += re.findall(r'(https?://[^\s\'"]+\.mpd[^\s\'"]*)', block, flags=re.I)

    # Optional vendor player scripts (source hidden behind vendor JS).
    found += re.findall(r'<script[^>]+src="(https?://static\.videoo\.tv/[^"]+\.js)"', block, flags=re.I)

    cleaned = []
    for src in found:
        src = html.unescape(src.strip())
        src = re.sub(r"\s+", "", src)
        if src.startswith("http://") or src.startswith("https://"):
            cleaned.append(src)
    return unique_keep_order(cleaned)


def extract_external_links(block: str) -> List[str]:
    links = re.findall(r'<a[^>]+href="(https?://[^"]+)"', block, flags=re.I)
    out = []
    for link in links:
        low = link.lower()
        if "camaramar.com" in low:
            continue
        if "suscripciones" in low or "register" in low or "login" in low:
            continue
        out.append(link.strip())
    return unique_keep_order(out)


def infer_type(sources: List[str]) -> str:
    if not sources:
        return "none"
    first = sources[0].lower()
    if "ipcamlive.com/player" in first or "/player.php" in first:
        return "iframe"
    if first.endswith(".m3u8") or ".m3u8?" in first:
        return "hls"
    if first.endswith(".mpd") or ".mpd?" in first:
        return "dash"
    if "youtube.com" in first or "youtu.be" in first or "vimeo.com" in first:
        return "embed"
    if "videoo.tv" in first:
        return "vendor-js"
    return "unknown"


def providers_for_sources(sources: List[str]) -> List[str]:
    providers = []
    for src in sources:
        try:
            providers.append(urlparse(src).netloc)
        except Exception:
            continue
    return unique_keep_order([p for p in providers if p])


def extract_title(doc: str) -> str:
    m = re.search(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", doc, flags=re.I)
    if m:
        return clean_text(m.group(1))
    m = re.search(r"<title>\s*([^<]+?)\s*</title>", doc, flags=re.I)
    if m:
        return clean_text(m.group(1))
    return ""


def process_url(url: str) -> CameraRow:
    path = url.replace("https://www.camaramar.com", "")
    try:
        doc = fetch_html(url)
    except HTTPError as e:
        return CameraRow(url, path, "", "error", "none", 0, "", "", "", str(e.code), f"HTTPError: {e}")
    except URLError as e:
        return CameraRow(url, path, "", "error", "none", 0, "", "", "", "", f"URLError: {e}")
    except Exception as e:
        return CameraRow(url, path, "", "error", "none", 0, "", "", "", "", f"Exception: {e}")

    title = extract_title(doc)
    block = extract_webcam_block(doc)
    if not block:
        # Some pages still include an empty webcam container.
        block_match = re.search(r'<div id="webcam"[^>]*>([\s\S]*?)</div>', doc, flags=re.I)
        block = block_match.group(1) if block_match else ""

    low_block = block.lower()
    sources = extract_sources(block)
    external_links = extract_external_links(block) if not sources else []
    if not sources and external_links:
        sources = external_links
    providers = providers_for_sources(sources)
    source_type = infer_type(sources)

    if "/images/24h-lock.webp" in low_block:
        status = "locked"
        note = "subscription_lock"
    elif "/images/out-of-service.webp" in low_block:
        status = "offline"
        note = "out_of_service"
    elif external_links:
        status = "linked"
        source_type = "external-page"
        note = "external_reference"
    elif sources:
        status = "live"
        note = "source_extracted"
    elif "wire:id" in block or "webcam-video" in block:
        status = "unknown"
        note = "component_present_no_source"
    else:
        status = "unknown"
        note = "no_embed_found"

    return CameraRow(
        url=url,
        path=path,
        title=title,
        status=status,
        source_type=source_type,
        source_count=len(sources),
        source_urls=" | ".join(sources),
        providers=" | ".join(providers),
        note=note,
        http_status="200",
        error="",
    )


def write_csv(rows: List[CameraRow], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "url",
                "path",
                "title",
                "status",
                "source_type",
                "source_count",
                "source_urls",
                "providers",
                "note",
                "http_status",
                "error",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.url,
                    r.path,
                    r.title,
                    r.status,
                    r.source_type,
                    r.source_count,
                    r.source_urls,
                    r.providers,
                    r.note,
                    r.http_status,
                    r.error,
                ]
            )


def write_provider_summary(rows: List[CameraRow], out_path: Path) -> None:
    provider_counts = {}
    for r in rows:
        if not r.providers:
            continue
        for p in [x.strip() for x in r.providers.split("|") if x.strip()]:
            provider_counts[p] = provider_counts.get(p, 0) + 1

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["provider", "camera_count"])
        for provider, count in sorted(provider_counts.items(), key=lambda x: (-x[1], x[0])):
            w.writerow([provider, count])


def write_markdown_report(rows: List[CameraRow], out_path: Path, runtime_s: float) -> None:
    total = len(rows)
    by_status = {}
    by_type = {}
    extracted = 0
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_type[r.source_type] = by_type.get(r.source_type, 0) + 1
        if r.source_count > 0:
            extracted += 1

    unresolved = [r for r in rows if r.status in ("unknown", "error")]
    top_live = [r for r in rows if r.status == "live" and r.source_urls][:25]

    lines = []
    lines.append("# Camaramar Full Source Crawl")
    lines.append("")
    lines.append(f"- Run date: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"- Pages crawled: {total}")
    lines.append(f"- Pages with extracted sources: {extracted}")
    lines.append(f"- Runtime: {runtime_s:.1f}s")
    lines.append("")
    lines.append("## Status Breakdown")
    for key in sorted(by_status):
        lines.append(f"- {key}: {by_status[key]}")
    lines.append("")
    lines.append("## Source Type Breakdown")
    for key in sorted(by_type):
        lines.append(f"- {key}: {by_type[key]}")
    lines.append("")
    lines.append("## Sample Live Sources (first 25)")
    lines.append("| title | path | type | providers | source_urls |")
    lines.append("|---|---|---|---|---|")
    for r in top_live:
        lines.append(f"| {r.title} | `{r.path}` | {r.source_type} | `{r.providers}` | `{r.source_urls}` |")
    lines.append("")
    lines.append(f"## Unresolved Or Error ({len(unresolved)})")
    lines.append("| path | status | note | error |")
    lines.append("|---|---|---|---|")
    for r in unresolved[:200]:
        lines.append(f"| `{r.path}` | {r.status} | {r.note} | {r.error or '-'} |")
    if len(unresolved) > 200:
        lines.append(f"| ... | ... | ... | plus {len(unresolved) - 200} more |")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parent
    urls_file = root / "webcam_urls.txt"
    if not urls_file.exists():
        print(f"Missing {urls_file}", file=sys.stderr)
        return 1

    urls = read_urls(urls_file)
    if not urls:
        print("No URLs found in webcam_urls.txt", file=sys.stderr)
        return 1

    start = time.time()
    rows: List[CameraRow] = []
    max_workers = 16

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_url, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), start=1):
            try:
                row = fut.result()
            except Exception as e:
                u = futures[fut]
                row = CameraRow(
                    url=u,
                    path=u.replace("https://www.camaramar.com", ""),
                    title="",
                    status="error",
                    source_type="none",
                    source_count=0,
                    source_urls="",
                    providers="",
                    note="exception_in_future",
                    http_status="",
                    error=str(e),
                )
            rows.append(row)
            if i % 100 == 0:
                print(f"Processed {i}/{len(urls)}")

    rows.sort(key=lambda r: r.path)
    elapsed = time.time() - start

    all_csv = root / "camaramar_all_camera_sources.csv"
    provider_csv = root / "camaramar_provider_summary.csv"
    unresolved_csv = root / "camaramar_unresolved.csv"
    report_md = root / "camaramar_full_report.md"

    write_csv(rows, all_csv)
    write_provider_summary(rows, provider_csv)
    write_csv([r for r in rows if r.status in ("unknown", "error")], unresolved_csv)
    write_markdown_report(rows, report_md, elapsed)

    live = sum(1 for r in rows if r.status == "live")
    linked = sum(1 for r in rows if r.status == "linked")
    locked = sum(1 for r in rows if r.status == "locked")
    offline = sum(1 for r in rows if r.status == "offline")
    unknown = sum(1 for r in rows if r.status == "unknown")
    error = sum(1 for r in rows if r.status == "error")

    print(f"Done in {elapsed:.1f}s")
    print(f"total={len(rows)} live={live} linked={linked} locked={locked} offline={offline} unknown={unknown} error={error}")
    print(f"Wrote: {all_csv}")
    print(f"Wrote: {provider_csv}")
    print(f"Wrote: {unresolved_csv}")
    print(f"Wrote: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
