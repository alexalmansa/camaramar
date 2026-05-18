#!/usr/bin/env python3
import csv
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)

STOP_WORDS = {
    "de",
    "del",
    "la",
    "el",
    "els",
    "les",
    "d",
    "i",
    "port",
    "ports",
    "marina",
    "marines",
    "embarcador",
    "embarcadors",
    "nautic",
    "nautics",
}

TRUSTED_SEARCH_DOMAINS = {
    "webcamscatalunya.com",
    "camaramar.com",
    "skylinewebcams.com",
    "windy.com",
    "windfinder.com",
    "webcamgalore.com",
    "youtube.com",
    "youtu.be",
    "ports.gencat.cat",
    "portdebarcelona.cat",
    "porttarragona.cat",
    "ccma.cat",
    "feratel.com",
}

MANUAL_ALIASES = {
    "port de segur de calafell": ["calafell", "segur"],
    "port de coma ruga": ["coma ruga", "comarruga"],
    "port de roda de bera": ["roda de bera", "roda bera"],
    "port de vallcarca sitges": ["vallcarca", "sitges"],
    "port de sitges aiguadolc": ["sitges", "aiguadolc", "aiguadolc"],
    "port de l hospitalet de l infant vandellos i l hospitalet de l infant": [
        "hospitalet de l infant",
        "hospitalet",
        "vandellos",
    ],
    "port de sant jordi d alfama": ["sant jordi d alfama", "alfama"],
    "port de les cases d alcanar": ["cases d alcanar", "alcanar"],
    "marina dels canals de santa margarida": ["santa margarida", "roses"],
    "marina d empuriabrava": ["empuriabrava"],
    "port de marina palamos": ["marina palamos", "palamos"],
    "port marina port d aro": ["port d aro", "aro"],
    "port balis": ["balis", "sant andreu de llavaneres", "llavaneres"],
    "port forum": ["forum", "barcelona"],
    "port olimpic": ["olimpic", "barcelona"],
    "port de la rapita": ["rapita", "sant carles de la rapita"],
    "port d alcanar": ["alcanar"],
    "port de deltebre": ["deltebre", "riu ebre", "ebre"],
}

AREA_RULES = [
    (
        "Costa Brava (Girona)",
        [
            "portbou",
            "colera",
            "llanca",
            "selva",
            "roses",
            "santa margarida",
            "empuriabrava",
            "escala",
            "estartit",
            "aiguablava",
            "llafranc",
            "palamos",
            "aro",
            "sant feliu",
            "cala canyelles",
            "blanes",
        ],
    ),
    (
        "Barcelona Coast",
        [
            "arenys",
            "balis",
            "mataro",
            "premia",
            "masnou",
            "badalona",
            "forum",
            "olimpic",
            "ginesta",
            "garraf",
            "vallcarca",
            "sitges",
            "vilanova",
            "barcelona",
        ],
    ),
    (
        "Costa Daurada (Tarragona)",
        [
            "calafell",
            "coma ruga",
            "roda de bera",
            "torredembarra",
            "salou",
            "cambrils",
            "hospitalet",
            "calafat",
            "alfama",
            "ametlla",
            "ampolla",
            "tarragona",
        ],
    ),
    (
        "Terres de l'Ebre",
        [
            "deltebre",
            "tortosa",
            "amposta",
            "sant jaume",
            "rapita",
            "alcanar",
            "cases d alcanar",
        ],
    ),
]


class Fetcher:
    def __init__(self) -> None:
        self.cache: dict[str, str] = {}

    def get(self, url: str, timeout: int = 12, retries: int = 2) -> str:
        if url in self.cache:
            return self.cache[url]
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": UA,
                        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = r.read().decode("utf-8", errors="replace")
                self.cache[url] = data
                return data
            except Exception as err:  # noqa: BLE001
                last_err = err
                time.sleep(0.4 * (attempt + 1))
        if last_err:
            raise last_err
        raise RuntimeError("fetch failed")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def core_port_phrase(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", name).strip()
    n = re.sub(
        r"^(port\s+(de|del|d['’])\s+|port\s+|marina\s+(dels|de|d['’])\s+|marina\s+|embarcador\s+de\s+)",
        "",
        n,
        flags=re.I,
    )
    return n.strip()


def significant_tokens(text: str) -> list[str]:
    toks = [t for t in normalize(text).split() if len(t) >= 4 and t not in STOP_WORDS]
    return list(dict.fromkeys(toks))


def port_aliases(name: str) -> list[str]:
    base = normalize(name)
    core = normalize(core_port_phrase(name))
    aliases = [core] if core else []
    aliases.extend(MANUAL_ALIASES.get(base, []))
    aliases.extend(MANUAL_ALIASES.get(core, []))
    aliases = [normalize(a) for a in aliases if normalize(a)]
    return list(dict.fromkeys(aliases))


def area_for_port(name: str) -> str:
    n = f" {normalize(name)} "
    for area, keys in AREA_RULES:
        if any(f" {normalize(k)} " in n for k in keys):
            return area
    return "Other"


def host_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


def canonicalize_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url)
    except Exception:  # noqa: BLE001
        return url

    # Drop anchors always.
    fragment = ""
    query = p.query

    # Snapshot image links often rotate query params; keep one canonical URL.
    if any(p.path.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        query = ""

    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, p.params, query, fragment))


def is_camera_like_url(url: str) -> bool:
    low = url.lower()
    host = host_of(url)
    if low.startswith("javascript:"):
        return False
    if host == "webcamscatalunya.com":
        return False
    if any(
        bad in low
        for bad in [
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "google.com/maps",
            "doubleclick.net",
            "googletagmanager.com",
            "google-analytics.com",
            "adsbygoogle",
            "wp-content/uploads",
            "/feed/",
            "images-webcams.windy.com",
            "webcams.windy.com/webcams/public/embed/script/player.js",
        ]
    ):
        return False

    must_have = [
        "youtube.com/embed/",
        "youtu.be/",
        "/webcam",
        "webcam",
        "cameraembed",
        "/camera/",
        ".m3u8",
        ".mpd",
        "windy.com/webcams",
        "webcams.windy.com",
        "images-webcams.windy.com",
        "ccma.cat/el-temps/embed",
        "feratel.com/webtv",
    ]
    return any(k in low for k in must_have)


def extract_urls(doc: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'<>]+", doc, flags=re.I)
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = html.unescape(u).strip("),.;'\"")
        u = canonicalize_url(u)
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def extract_camera_links_from_html(doc: str) -> list[str]:
    links = [u for u in extract_urls(doc) if is_camera_like_url(u)]
    return unique(links)


def decode_ddg_result_href(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs and qs["uddg"]:
        return urllib.parse.unquote(qs["uddg"][0])
    return href


def parse_ports_from_home() -> list[dict]:
    home = (ROOT / "ports_home.html").read_text(encoding="utf-8", errors="ignore")
    anchors = re.findall(
        r'<a class="sitemap-item" href="(https://ports\.gencat\.cat/[^"]+)">(.*?)</a>',
        home,
        flags=re.I,
    )

    ports: list[dict] = []
    seen: set[str] = set()
    for href, text in anchors:
        name = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
        if not re.search(r"\b(port|marina|embarcador)\b", name, re.I):
            continue
        if href in seen:
            continue
        seen.add(href)
        ports.append(
            {
                "name": name,
                "official_url": href,
                "area": area_for_port(name),
                "aliases": port_aliases(name),
                "tokens": significant_tokens(name),
                "core": normalize(core_port_phrase(name)),
            }
        )

    for extra_name, extra_url in [
        ("Port de Barcelona", "https://www.portdebarcelona.cat/"),
        ("Port de Tarragona", "https://www.porttarragona.cat/"),
    ]:
        ports.append(
            {
                "name": extra_name,
                "official_url": extra_url,
                "area": area_for_port(extra_name),
                "aliases": port_aliases(extra_name),
                "tokens": significant_tokens(extra_name),
                "core": normalize(core_port_phrase(extra_name)),
            }
        )
    return ports


def text_match_score(port: dict, text: str) -> int:
    norm = f" {normalize(text)} "
    words = set(norm.split())
    score = 0

    core = port.get("core", "")
    if core and f" {core} " in norm:
        if len(core.split()) == 1 and core in {"barcelona", "tarragona", "girona"}:
            score += 1
        else:
            score += 3

    token_hits = 0
    for t in port.get("tokens", []):
        if t not in words:
            continue
        if t in {"barcelona", "tarragona", "girona"} and "port" not in words:
            continue
        token_hits += 1
    score += min(token_hits, 3)

    for alias in port.get("aliases", []):
        if alias and f" {alias} " in norm:
            score += 2

    return score


def catalog_matches(port: dict, catalog: list[dict]) -> list[str]:
    out: list[str] = []
    for cam in catalog:
        hay = " ".join(
            [
                cam.get("title", ""),
                cam.get("subtitle", ""),
                cam.get("path", ""),
                cam.get("sourceUrl", ""),
                cam.get("area", ""),
            ]
        )
        score = text_match_score(port, hay)
        if score >= 3:
            out.append(cam.get("sourceUrl", ""))
    return unique([u for u in out if u])


def webcamscat_matches(port: dict, fetcher: Fetcher) -> list[str]:
    queries: list[str] = []
    if port.get("core"):
        queries.append(port["core"])
    queries.extend(port.get("aliases", []))
    queries.extend(port.get("tokens", [])[:2])

    # Keep query count bounded and deterministic.
    queries = list(dict.fromkeys([q for q in queries if q]))[:2]

    post_links: list[str] = []
    camera_links: list[str] = []

    for q in queries:
        url = (
            "https://webcamscatalunya.com/wp-json/wp/v2/posts?search="
            + urllib.parse.quote(q)
            + "&per_page=15"
        )
        try:
            doc = fetcher.get(url)
            posts = json.loads(doc)
        except Exception:
            continue

        for p in posts:
            title = p.get("title", {}).get("rendered", "")
            link = p.get("link", "")
            content = p.get("content", {}).get("rendered", "")
            hay = " ".join([title, link, content[:2000]])
            score = text_match_score(port, hay)
            if score < 3:
                continue
            post_links.append(link)
            for u in extract_camera_links_from_html(content):
                camera_links.append(u)

    # If API content was too sparse for a match, pull post pages directly.
    direct_links = unique(post_links)
    for post_url in direct_links[:8]:
        try:
            page = fetcher.get(post_url, timeout=10, retries=1)
        except Exception:
            continue
        for u in extract_camera_links_from_html(page):
            camera_links.append(u)
        time.sleep(0.2)

    return unique(camera_links)


def ddg_webcam_search(port: dict, fetcher: Fetcher, max_links: int = 4) -> list[str]:
    query = f"{port['name']} webcam"
    url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        doc = fetcher.get(url, timeout=10, retries=1)
    except Exception:
        return []

    raw = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', doc, flags=re.I)
    out: list[str] = []
    for href in raw:
        u = decode_ddg_result_href(href)
        low = u.lower()
        host = host_of(u)
        if not host:
            continue
        if host not in TRUSTED_SEARCH_DOMAINS:
            continue
        if not any(k in low for k in ["webcam", "camera", "cam", "youtube", "windy", "stream"]):
            continue
        out.append(u)

    return unique(out)[:max_links]


def unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def main() -> None:
    ports = parse_ports_from_home()
    catalog = json.loads((ROOT / "merged_cameras.json").read_text(encoding="utf-8"))
    fetcher = Fetcher()

    rows: list[dict] = []

    for idx, port in enumerate(ports, start=1):
        name = port["name"]
        official_url = port["official_url"]

        official_links: list[str] = []
        try:
            page = fetcher.get(official_url)
            official_links = extract_camera_links_from_html(page)
        except Exception:
            official_links = []

        catalog_links = catalog_matches(port, catalog)
        webcamscat_links = webcamscat_matches(port, fetcher)

        combined = unique(official_links + catalog_links + webcamscat_links)
        if not combined:
            search_links = ddg_webcam_search(port, fetcher, max_links=4)
            combined = unique(combined + search_links)
        else:
            search_links = []
        combined = combined[:12]

        rows.append(
            {
                "port_name": name,
                "area": port["area"],
                "official_port_url": official_url,
                "camera_count": len(combined),
                "camera_links": " | ".join(combined),
                "official_page_links": " | ".join(official_links),
                "catalog_links": " | ".join(catalog_links),
                "webcamscatalunya_links": " | ".join(webcamscat_links),
                "search_links": " | ".join(search_links),
            }
        )

        print(f"[{idx:02d}/{len(ports)}] {name}: {len(combined)} links", flush=True)
        time.sleep(0.2)

    rows.sort(key=lambda r: (r["area"], normalize(r["port_name"])))

    out_csv = ROOT / "catalonia_ports_cameras.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "port_name",
                "area",
                "official_port_url",
                "camera_count",
                "camera_links",
                "official_page_links",
                "catalog_links",
                "webcamscatalunya_links",
                "search_links",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    found = sum(1 for r in rows if r["camera_count"] > 0)
    missing = len(rows) - found

    by_area: dict[str, dict[str, int]] = {}
    for r in rows:
        area = r["area"]
        if area not in by_area:
            by_area[area] = {"ports": 0, "with_camera": 0}
        by_area[area]["ports"] += 1
        if r["camera_count"] > 0:
            by_area[area]["with_camera"] += 1

    md: list[str] = []
    md.append("# Catalonia Ports Camera Audit")
    md.append("")
    md.append(f"- Ports checked: {len(rows)}")
    md.append(f"- Ports with at least one camera link: {found}")
    md.append(f"- Ports without camera links found: {missing}")
    md.append("")
    md.append("## Coverage By Area")
    md.append("")
    md.append("| Area | Ports | With camera |")
    md.append("|---|---:|---:|")
    for area in sorted(by_area):
        info = by_area[area]
        md.append(f"| {area} | {info['ports']} | {info['with_camera']} |")

    md.append("")
    md.append("## Ports")
    md.append("")
    md.append("| Area | Port | Cameras found |")
    md.append("|---|---|---:|")
    for r in rows:
        md.append(f"| {r['area']} | {r['port_name']} | {r['camera_count']} |")

    md.append("")
    md.append("## Ports Without Camera Links Found")
    for r in rows:
        if r["camera_count"] == 0:
            md.append(f"- [{r['area']}] {r['port_name']}")

    report_path = ROOT / "catalonia_ports_cameras_report.md"
    report_path.write_text("\n".join(md), encoding="utf-8")

    print(f"done: {found}/{len(rows)} ports with camera links", flush=True)
    print(f"csv: {out_csv}", flush=True)
    print(f"report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
