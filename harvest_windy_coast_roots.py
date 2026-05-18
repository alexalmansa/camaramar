#!/usr/bin/env python3
import csv
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent

WINDY_LIST_ENDPOINT = "https://node.windy.com/webcams/v1.0/list"
WINDY_DETAIL_ENDPOINT = "https://node.windy.com/webcams/v1.0/detail/"
UA = "surfcheck-windy-harvester/1.0 (+local-build)"

OUT_CSV = ROOT / "windy_coast_root_sources.csv"

COAST_POINTS = [
    ("A Coruna", 43.37, -8.41),
    ("Vigo", 42.23, -8.77),
    ("Gijon", 43.54, -5.66),
    ("Santander", 43.46, -3.80),
    ("Bilbao", 43.35, -3.02),
    ("San Sebastian", 43.32, -1.99),
    ("Costa Brava", 42.24, 3.20),
    ("Barcelona", 41.38, 2.20),
    ("Garraf", 41.25, 1.93),
    ("Tarragona", 41.08, 1.23),
    ("Ebro", 40.62, 0.59),
    ("Castellon", 39.97, -0.03),
    ("Valencia", 39.45, -0.32),
    ("Alicante", 38.35, -0.48),
    ("Cartagena", 37.60, -0.99),
    ("Almeria", 36.83, -2.46),
    ("Malaga", 36.72, -4.42),
    ("Cadiz", 36.53, -6.29),
    ("Huelva", 37.21, -7.02),
    ("Lagos", 37.10, -8.67),
    ("Faro", 37.01, -7.93),
    ("Sines", 37.95, -8.87),
    ("Cascais", 38.69, -9.42),
    ("Nazare", 39.60, -9.07),
    ("Aveiro", 40.64, -8.73),
    ("Porto", 41.15, -8.67),
    ("Viana do Castelo", 41.70, -8.83),
    ("Mallorca", 39.57, 2.65),
    ("Menorca", 39.95, 4.11),
]

COAST_KEYWORDS = [
    "beach",
    "playa",
    "platja",
    "praia",
    "surf",
    "port",
    "marina",
    "costa",
    "coast",
    "mar",
    "sea",
    "ocean",
    "puerto",
    "harbor",
    "harbour",
    "cala",
]

BLOCK_HOST_FRAGMENTS = {
    "dgt.es",
    "infocar.dgt.es",
    "bizkaimove.com",
    "movilidad.malaga.eu",
    "barcelona.cat",
    "com-shi-va.barcelona.cat",
    "bizkaia.eus",
    "lusoponte.pt",
}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def host_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def has_embedded_credentials(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    return bool(parsed.username or parsed.password)


def looks_coastal(title: str, page_url: str, city: str) -> bool:
    blob = f"{title} {page_url} {city}".lower()
    return any(k in blob for k in COAST_KEYWORDS)


def main() -> None:
    ids = set()

    for _, lat, lon in COAST_POINTS:
        params = urllib.parse.urlencode(
            {
                "nearby": f"{lat:.5f},{lon:.5f}",
                "lang": "en",
                "limit": 25,
            }
        )
        url = f"{WINDY_LIST_ENDPOINT}?{params}"
        try:
            payload = fetch_json(url)
        except Exception:
            continue
        for cam in payload.get("cams", []):
            cid = cam.get("id")
            if isinstance(cid, int):
                ids.add(cid)
        time.sleep(0.03)

    rows = []
    for idx, cid in enumerate(sorted(ids), start=1):
        try:
            detail = fetch_json(f"{WINDY_DETAIL_ENDPOINT}{cid}?lang=en")
        except Exception:
            continue

        page_url = (detail.get("pageUrl") or "").strip()
        stream_url = (detail.get("stream") or "").strip()
        if not page_url:
            continue
        if has_embedded_credentials(page_url):
            continue

        host = host_of(page_url)
        if host.endswith("windy.com") or host == "webcams.windy.com":
            continue
        if any(frag in host for frag in BLOCK_HOST_FRAGMENTS):
            continue

        location = detail.get("location") or {}
        lat = location.get("lat")
        lon = location.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue

        country = (location.get("country") or "").strip()
        if country not in {"Spain", "Portugal"}:
            continue
        city = (location.get("city") or "").strip()
        title = (detail.get("title") or f"Windy Cam {cid}").strip()

        if not looks_coastal(title, page_url, city):
            continue

        rows.append(
            {
                "windy_id": str(cid),
                "windy_url": f"https://windy.com/webcams/{cid}",
                "title": title,
                "root_source_url": page_url,
                "stream_url": stream_url,
                "lat": f"{lat:.6f}",
                "lng": f"{lon:.6f}",
                "city": city,
                "subcountry": (location.get("subcountry") or "").strip(),
                "country": country,
            }
        )

        if idx % 100 == 0:
            print(f"Resolved details: {idx}/{len(ids)}")
        time.sleep(0.02)

    # Deduplicate exact windy ID and root URL pairs.
    seen = set()
    deduped = []
    for row in rows:
        key = (row["windy_id"], row["root_source_url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    deduped.sort(key=lambda r: (r["country"], r["subcountry"], r["city"], r["title"]))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "windy_id",
                "windy_url",
                "title",
                "root_source_url",
                "stream_url",
                "lat",
                "lng",
                "city",
                "subcountry",
                "country",
            ],
        )
        writer.writeheader()
        writer.writerows(deduped)

    hosts = Counter(host_of(r["root_source_url"]) for r in deduped)
    print("Coast points:", len(COAST_POINTS))
    print("Unique Windy camera IDs:", len(ids))
    print("Root-source cameras exported:", len(deduped))
    print("Top hosts:", hosts.most_common(15))
    print("CSV:", OUT_CSV)


if __name__ == "__main__":
    main()
