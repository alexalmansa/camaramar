#!/usr/bin/env python3
import csv
import html
import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
import time
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEOCODE_CACHE_PATH = ROOT / "geocode_cache.json"
GEOCODER_UA = "surfcheck-geocoder/1.0 (+local-build)"
GEOCODER_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
MAX_NEW_GEOCODES = int(os.environ.get("SURFCHECK_MAX_NEW_GEOCODES", "1200"))
WINDY_DETAIL_ENDPOINT = "https://node.windy.com/webcams/v1.0/detail/"

SKYLINE_AREA_MAP = {
    "andalucia": "Andalusia",
    "aragon": "Aragon",
    "asturias": "Asturias",
    "islas-baleares": "Balearic Islands",
    "comunidad-autonoma-vasca": "Basque Country",
    "canarias": "Canary Islands",
    "cantabria": "Cantabria",
    "castilla-y-leon": "Castile and Leon",
    "castiglia-la-mancia": "Castilla-La Mancha",
    "cataluna": "Catalonia",
    "comunidad-de-madrid": "Community of Madrid",
    "galicia": "Galicia",
    "region-de-murcia": "Region of Murcia",
    "comunidad-valenciana": "Valencian Community",
    "algarve": "Algarve",
    "lisboa": "Lisbon Area",
    "madeira": "Madeira",
    "centro": "Central Portugal",
}

SPAIN_AREA_KEYWORDS = [
    (
        "Catalonia",
        [
            "cataluna",
            "catalunya",
            "barcelona",
            "tarragona",
            "girona",
            "sitges",
            "salou",
            "cambrils",
            "vilanova",
            "badalona",
            "masnou",
            "mataro",
            "roses",
            "palamos",
            "llafranc",
            "estartit",
            "escala",
            "blanes",
            "calafell",
            "torredembarra",
            "ametlla",
            "rapita",
            "alcanar",
        ],
    ),
    (
        "Basque Country",
        [
            "euskadi",
            "bizkaia",
            "vizcaya",
            "guipuzcoa",
            "gipuzkoa",
            "donostia",
            "san-sebastian",
            "zarautz",
            "getaria",
            "bermeo",
            "mundaka",
            "sopelana",
            "sopela",
            "lekeitio",
            "ondarroa",
            "getxo",
            "bilbao",
        ],
    ),
    (
        "Galicia",
        [
            "galicia",
            "coruna",
            "a-coruna",
            "pontevedra",
            "vigo",
            "baiona",
            "cangas",
            "larino",
            "burela",
            "sanxenxo",
            "cambre",
            "camarinas",
        ],
    ),
    (
        "Cantabria",
        ["cantabria", "santander", "suances", "laredo", "castro-urdiales", "noja"],
    ),
    (
        "Asturias",
        ["asturias", "gijon", "aviles", "llanes", "ribadesella", "luarca"],
    ),
    (
        "Andalusia",
        [
            "andalucia",
            "cadiz",
            "huelva",
            "malaga",
            "almeria",
            "granada",
            "motril",
            "marbella",
            "estepona",
            "conil",
            "tarifa",
            "barbate",
            "roquetas",
        ],
    ),
    (
        "Region of Murcia",
        ["murcia", "mazarron", "cartagena", "aguilas", "la-manga", "manga"],
    ),
    (
        "Valencian Community",
        [
            "comunidad-valenciana",
            "valencia",
            "alicante",
            "castellon",
            "cullera",
            "benicarlo",
            "canet",
            "farnals",
            "voramar",
            "forti",
            "patacona",
            "alboraya",
            "lalbir",
            "gandia",
            "grava",
            "roda",
            "roqueta",
            "piles",
            "denia",
            "calpe",
            "altea",
            "javea",
            "xabia",
            "torrevieja",
        ],
    ),
    (
        "Balearic Islands",
        ["illes-balears", "baleares", "mallorca", "menorca", "ibiza", "formentera"],
    ),
    (
        "Canary Islands",
        [
            "canarias",
            "tenerife",
            "lanzarote",
            "fuerteventura",
            "grancanaria",
            "gran-canaria",
            "la-palma",
            "la-gomera",
        ],
    ),
]

PORTUGAL_AREA_KEYWORDS = [
    ("Lisbon Area", ["lisboa", "lisbon", "cascais", "estoril", "setubal", "nazare"]),
    ("Algarve", ["algarve", "portimao", "lagos", "albufeira", "vilamoura"]),
    ("Madeira", ["madeira", "funchal"]),
    ("Central Portugal", ["aveiro", "coimbra", "figueira"]),
]

REGION_CENTROIDS = {
    "Spain": (40.20, -3.70),
    "Portugal": (39.45, -8.00),
    "Catalonia": (41.75, 1.80),
}

AREA_CENTROIDS = {
    ("Catalonia", "Barcelona Coast"): (41.35, 2.15),
    ("Catalonia", "Costa Brava (Girona)"): (42.05, 3.15),
    ("Catalonia", "Costa Daurada (Tarragona)"): (41.05, 1.20),
    ("Catalonia", "Terres de l'Ebre"): (40.70, 0.70),
    ("Spain", "Catalonia"): (41.75, 2.20),
    ("Spain", "Basque Country"): (43.30, -2.70),
    ("Spain", "Galicia"): (42.45, -8.75),
    ("Spain", "Cantabria"): (43.35, -3.80),
    ("Spain", "Asturias"): (43.45, -5.85),
    ("Spain", "Andalusia"): (36.80, -4.85),
    ("Spain", "Region of Murcia"): (37.75, -0.95),
    ("Spain", "Valencian Community"): (39.45, -0.35),
    ("Spain", "Balearic Islands"): (39.60, 2.95),
    ("Spain", "Canary Islands"): (28.25, -16.45),
    ("Spain", "Aragon"): (41.60, -0.90),
    ("Spain", "Castile and Leon"): (42.20, -4.70),
    ("Spain", "Community of Madrid"): (40.42, -3.70),
    ("Spain", "Castilla-La Mancha"): (39.80, -3.05),
    ("Spain", "Other"): (40.20, -3.70),
    ("Portugal", "Lisbon Area"): (38.72, -9.14),
    ("Portugal", "Algarve"): (37.08, -8.20),
    ("Portugal", "Madeira"): (32.75, -17.00),
    ("Portugal", "Central Portugal"): (40.20, -8.45),
    ("Portugal", "Other"): (39.45, -8.00),
}

AREA_SPREAD_DEGREES = {
    ("Catalonia", "Barcelona Coast"): 0.09,
    ("Catalonia", "Costa Brava (Girona)"): 0.11,
    ("Catalonia", "Costa Daurada (Tarragona)"): 0.10,
    ("Catalonia", "Terres de l'Ebre"): 0.09,
    ("Spain", "Other"): 0.65,
    ("Portugal", "Other"): 0.35,
}

PORTS_EXCLUDED_BY_REQUEST = {
    "port d arenys de mar",
    "port de barcelona",
}

BADALONA_PORT_NAME_KEYS = {"port de badalona"}
BADALONA_INLINE_SOURCES = [
    "http://cnbadalona.cat/cam/llevant.php",
    "http://cnbadalona.cat/cam/ponent.php",
]
CASTELLDEFELS_17NUDOS_KEYS = {"club nautic castelldefels 17nudos"}
PORT_GINESTA_NAME_KEYS = {"port ginesta"}

PORT_BASE_COORDS = {
    "marina dels canals de santa margarida": (42.2622, 3.1669),
    "port de roses": (42.2626, 3.1752),
    "port de llafranc": (41.8920, 3.1728),
    "port de marina palamos": (41.8456, 3.1286),
    "port de palamos": (41.8458, 3.1293),
    "port marina port d aro": (41.8154, 3.0678),
    "port ginesta": (41.2658, 1.9295),
    "port olimpic": (41.3902, 2.1980),
    "port de badalona": (41.4372, 2.2472),
    "port de mataro": (41.5382, 2.4465),
    "port de sitges aiguadolc": (41.2349, 1.8236),
    "port de vallcarca sitges": (41.2327, 1.8796),
    "port de vilanova i la geltru": (41.2169, 1.7292),
    "club nautic castelldefels 17nudos": (41.265324, 1.969525),
    "port de segur de calafell": (41.1864, 1.6081),
    "port de torredembarra": (41.1361, 1.4050),
    "port de salou": (41.0767, 1.1449),
    "port de cambrils": (41.0679, 1.0588),
    "port de tarragona": (41.1072, 1.2364),
    "port de l ametlla de mar": (40.8866, 0.8036),
    "port de la rapita": (40.6204, 0.5931),
    "port d alcanar": (40.5484, 0.5305),
}

GLOBAL_BLOCK_TERMS = [
    "port d arenys de mar",
    "port d'arenys de mar",
    "port d’arenys de mar",
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def load_geocode_cache() -> dict:
    if not GEOCODE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_geocode_cache(cache: dict) -> None:
    cleaned = {}
    for key, value in cache.items():
        if not value:
            continue
        if not isinstance(value, dict):
            continue
        lat = value.get("lat")
        lng = value.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            cleaned[key] = {"lat": float(lat), "lng": float(lng), "q": value.get("q", "")}
    GEOCODE_CACHE_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def split_first(value: str, sep: str = " | ") -> str:
    items = [x.strip() for x in value.split(sep) if x.strip()]
    return items[0] if items else ""


def host_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def parse_windy_webcam_id(url: str) -> str:
    m = re.search(r"windy\.com/webcams/(\d+)", url, flags=re.I)
    return m.group(1) if m else ""


def fetch_windy_webcam_detail(webcam_id: str) -> dict | None:
    if not webcam_id:
        return None
    req = urllib.request.Request(
        f"{WINDY_DETAIL_ENDPOINT}{webcam_id}?lang=en",
        headers={"User-Agent": GEOCODER_UA},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def resolve_windy_root_source(url: str) -> tuple[str, dict | None]:
    webcam_id = parse_windy_webcam_id(url)
    if not webcam_id:
        return (url, None)
    try:
        detail = fetch_windy_webcam_detail(webcam_id)
    except Exception:
        return (url, None)

    if not detail:
        return (url, None)

    page_url = (detail.get("pageUrl") or "").strip()
    if page_url:
        host = host_of(page_url)
        if host and not host.endswith("windy.com") and host != "webcams.windy.com":
            return (page_url, detail)

    return (url, detail)


def stable_jitter_lat_lng(base_lat: float, base_lng: float, key: str, spread: float) -> tuple[float, float]:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    angle = (int(digest[:8], 16) / 0xFFFFFFFF) * 2 * math.pi
    radius = (0.25 + 0.75 * (int(digest[8:16], 16) / 0xFFFFFFFF)) * spread

    lat = base_lat + math.sin(angle) * radius
    cos_lat = max(math.cos(math.radians(base_lat)), 0.35)
    lng = base_lng + (math.cos(angle) * radius) / cos_lat
    return (round(lat, 6), round(lng, 6))


def coord_distance_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    dx = lat1 - lat2
    dy = (lng1 - lng2) * max(math.cos(math.radians((lat1 + lat2) / 2)), 0.35)
    return math.sqrt(dx * dx + dy * dy)


def is_reasonable_for_area(entry: dict, coord: tuple[float, float]) -> bool:
    region = entry.get("region", "Spain")
    area = entry.get("area", "Other")
    if area == "Other":
        return True

    center = AREA_CENTROIDS.get((region, area))
    if not center:
        return True

    max_deg = 1.6
    if area in {"Canary Islands", "Balearic Islands", "Galicia", "Andalusia", "Lisbon Area", "Algarve"}:
        max_deg = 2.3
    if area in {"Madeira", "Barcelona Coast", "Costa Brava (Girona)", "Costa Daurada (Tarragona)", "Terres de l'Ebre"}:
        max_deg = 1.0

    return coord_distance_deg(coord, center) <= max_deg


def camera_coordinates(entry: dict, base: tuple[float, float]) -> tuple[float, float]:
    base_lat, base_lng = base
    if entry.get("originSite") == "windy-root":
        return (round(base_lat, 6), round(base_lng, 6))

    spread = 0.022
    if entry.get("originSite") == "ports-catalonia":
        spread = 0.008
    elif entry.get("originSite") == "camaramar":
        spread = 0.014
    elif entry.get("originSite") == "skylinewebcams":
        spread = 0.02

    # Keep tight placement in islands/coastal micro-areas.
    if entry.get("area") in {"Balearic Islands", "Madeira", "Canary Islands"}:
        spread = min(spread, 0.012)

    key = "|".join([entry.get("originSite", ""), entry.get("path", ""), entry.get("title", "")])
    return stable_jitter_lat_lng(base_lat, base_lng, key, spread)


def fallback_base_coordinates(entry: dict) -> tuple[float, float]:
    region = entry.get("region", "Spain")
    area = entry.get("area", "Other")
    base = AREA_CENTROIDS.get((region, area)) or REGION_CENTROIDS.get(region) or REGION_CENTROIDS["Spain"]
    return base


def infer_primary_place(entry: dict) -> str:
    title = re.sub(r"\bcam\s*\d+\b", "", entry.get("title", ""), flags=re.I).strip(" -")
    path_slug = entry.get("path", "").strip("/").split("/")[-1].replace("-", " ").strip()

    if entry.get("originSite") == "ports-catalonia":
        base = re.sub(r"\s+Cam\s+\d+$", "", title, flags=re.I).strip()
        base = re.sub(r"\(.*?\)", "", base).strip()
        cand = re.sub(r"^Port\s+(de|d['’]|del|de les)\s+", "", base, flags=re.I).strip()
        cand = re.sub(r"^Marina\s+(de|d['’]|dels|del)\s+", "", cand, flags=re.I).strip()
        cand = re.sub(r"^Embarcador\s+de\s+", "", cand, flags=re.I).strip()
        if not cand:
            cand = base
    else:
        cand = title
        if "," in title:
            parts = [p.strip() for p in title.split(",") if p.strip()]
            if parts:
                pick = parts[-1] if len(parts[-1]) >= 3 else parts[0]
                if normalize_text(pick) in {"portugal", "spain", "espana", "catalonia", "cataluna"}:
                    pick = parts[0]
                cand = pick
        elif " - " in title:
            parts = [p.strip() for p in title.split(" - ") if p.strip()]
            if parts:
                generic_terms = {"portugal", "spain", "espana", "catalonia", "cataluna"}

                def part_score(part: str) -> int:
                    norm = normalize_text(part)
                    score = 0
                    if norm in generic_terms:
                        score -= 5
                    if any(k in norm for k in ["beach", "playa", "view", "panorama", "webcam", "camera"]):
                        score -= 2
                    score += min(len(norm.split()), 4)
                    return score

                cand = sorted(parts, key=part_score, reverse=True)[0]

    if path_slug and (not cand or len(cand) < 3):
        cand = path_slug

    cand = re.sub(r"https?://\S+", " ", cand, flags=re.I)
    cand = re.sub(r"\b(webcam|camera|cam|playa|beach|vista|view)\b", " ", cand, flags=re.I)
    cand = re.sub(r"\s+", " ", cand).strip(" -_,.;")
    return cand


def canonical_port_title(title: str) -> str:
    base = re.sub(r"\s+Cam\s+\d+$", "", title, flags=re.I).strip()
    return normalize_text(base)


def geocode_open_meteo(query: str, country_code: str) -> tuple[float, float] | None:
    params = urllib.parse.urlencode(
        {
            "name": query,
            "count": 5,
            "language": "en",
            "format": "json",
        }
    )
    url = f"{GEOCODER_ENDPOINT}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": GEOCODER_UA})
    with urllib.request.urlopen(req, timeout=3) as r:
        data = json.loads(r.read().decode("utf-8", errors="replace"))

    results = data.get("results") or []
    if not results:
        return None

    for item in results:
        cc = (item.get("country_code") or "").lower()
        if cc and cc != country_code.lower():
            continue
        lat = item.get("latitude")
        lng = item.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return (float(lat), float(lng))
    return None


def resolve_base_coordinate(
    entry: dict,
    geocode_cache: dict,
    place_cache: dict[str, tuple[float, float] | None],
    stats: dict[str, int],
) -> tuple[float, float]:
    fixed_lat = entry.get("fixedLat")
    fixed_lng = entry.get("fixedLng")
    if isinstance(fixed_lat, (int, float)) and isinstance(fixed_lng, (int, float)):
        return (float(fixed_lat), float(fixed_lng))

    if entry.get("originSite") == "ports-catalonia":
        port_key = canonical_port_title(entry.get("title", ""))
        if port_key in PORT_BASE_COORDS:
            return PORT_BASE_COORDS[port_key]

    country_code = "pt" if entry.get("region") == "Portugal" else "es"
    country_name = "Portugal" if country_code == "pt" else "Spain"
    fallback = fallback_base_coordinates(entry)
    place = infer_primary_place(entry)
    if not place or len(place) < 3:
        return fallback

    query = f"{place}, {country_name}"
    norm_key = f"{country_code}|{normalize_text(place)}"
    if norm_key in place_cache:
        resolved = place_cache[norm_key]
        if resolved:
            return resolved
        return fallback

    if norm_key in geocode_cache:
        cached = geocode_cache[norm_key]
        if cached:
            resolved = (float(cached["lat"]), float(cached["lng"]))
            if is_reasonable_for_area(entry, resolved):
                place_cache[norm_key] = resolved
                stats["cache_hits"] += 1
                return resolved
            place_cache[norm_key] = None
            return fallback
        place_cache[norm_key] = None
        return fallback

    if stats["new_geocodes"] >= MAX_NEW_GEOCODES:
        return fallback

    try:
        resolved = geocode_open_meteo(query, country_code)
    except Exception:
        resolved = None
    stats["new_geocodes"] += 1
    time.sleep(0.02)

    if resolved:
        if is_reasonable_for_area(entry, resolved):
            geocode_cache[norm_key] = {"lat": resolved[0], "lng": resolved[1], "q": query}
            place_cache[norm_key] = resolved
            stats["resolved_now"] += 1
            return resolved
        place_cache[norm_key] = None
    place_cache[norm_key] = None

    stats["fallback"] += 1
    return fallback


def detect_source_type(url: str, default: str = "external-page") -> str:
    low = url.lower()
    if low.endswith(".m3u8") or ".m3u8?" in low:
        return "hls"
    if low.endswith(".mpd") or ".mpd?" in low:
        return "dash"
    if any(
        key in low
        for key in [
            "youtube.com/embed/",
            "youtu.be/",
            "ccma.cat/el-temps/embed",
            "feratel.com/webtv",
            "player.twitch.tv",
            "camstreamer.com/embed/",
            "camstreamer.com/yt-embed/",
            "v.angelcam.com/iframe",
        ]
    ):
        return "iframe"
    if default and default != "none":
        return default
    return "external-page"


def has_embedded_credentials(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    return bool(parsed.username or parsed.password)


def extract_17nudos_cam_links(page_url: str) -> list[str]:
    if not page_url:
        return []
    req = urllib.request.Request(page_url, headers={"User-Agent": GEOCODER_UA})
    with urllib.request.urlopen(req, timeout=5) as r:
        doc = r.read().decode("utf-8", errors="ignore")

    links = []
    for m in re.finditer(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", doc, flags=re.I):
        src = html.unescape(m.group(1)).strip()
        if "camstreamer.com/" not in src.lower():
            continue
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("/"):
            src = urllib.parse.urljoin(page_url, src)
        links.append(src)

    out = []
    seen = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        out.append(link)
    return out


def normalize_angelcam_iframe(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "angelcam.com" not in parsed.netloc.lower() or "/iframe" not in parsed.path.lower():
        return url
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    q.pop("token", None)
    clean_query = urllib.parse.urlencode([(k, v) for k, vals in q.items() for v in vals], doseq=True)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", clean_query, ""))


def extract_port_ginesta_cam_links(page_url: str) -> list[str]:
    if not page_url:
        return []
    req = urllib.request.Request(page_url, headers={"User-Agent": GEOCODER_UA})
    with urllib.request.urlopen(req, timeout=5) as r:
        doc = r.read().decode("utf-8", errors="ignore")

    links = []
    for m in re.finditer(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", doc, flags=re.I):
        src = html.unescape(m.group(1)).strip()
        if "angelcam.com/iframe" not in src.lower():
            continue
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("/"):
            src = urllib.parse.urljoin(page_url, src)
        src = normalize_angelcam_iframe(src)
        links.append(src)

    out = []
    seen = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        out.append(link)
    return out


def classify_region_area(path: str, title: str) -> tuple[str, str]:
    text = normalize_text(f"{path} {title}")
    padded = f" {text} "

    def has_keyword(key: str) -> bool:
        return f" {normalize_text(key)} " in padded

    # Conservative Portugal detection to avoid Spain false positives (e.g. \"Faro\" lighthouse).
    if any(
        has_keyword(k)
        for k in [
            "portugal",
            "lisboa",
            "lisbon",
            "algarve",
            "madeira",
            "setubal",
            "cascais",
            "nazare",
            "albufeira",
            "portimao",
            "aveiro",
            "coimbra",
            "figueira",
        ]
    ):
        for area, keys in PORTUGAL_AREA_KEYWORDS:
            if any(has_keyword(k) for k in keys):
                return ("Portugal", area)
        return ("Portugal", "Other")

    for area, keys in SPAIN_AREA_KEYWORDS:
        if any(has_keyword(k) for k in keys):
            return ("Spain", area)

    return ("Spain", "Other")


def load_camaramar_entries() -> list[dict]:
    rows = []
    with (ROOT / "camaramar_all_camera_sources.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out = []
    for row in rows:
        page_url = row.get("url", "").strip()
        path = row.get("path", "").strip()
        if not page_url or not path:
            continue

        title = row.get("title", "").replace("Webcam ", "").strip() or path.split("/")[-1]
        extracted_url = split_first(row.get("source_urls", ""))
        source_type_raw = (row.get("source_type", "") or "").strip().lower()

        if row.get("status") == "live" and extracted_url:
            source_url = extracted_url
            source_type = detect_source_type(source_url, source_type_raw)
            status = "live"
            subtitle = "Direct playable source extracted from Camaramar"
        else:
            source_url = page_url
            source_type = "external-page"
            status = "external"
            subtitle = "Open camera on Camaramar"

        region, area = classify_region_area(path, title)
        provider = split_first(row.get("providers", "")) or host_of(source_url) or "camaramar.com"

        out.append(
            {
                "title": title,
                "subtitle": subtitle,
                "path": path,
                "status": status,
                "sourceType": source_type,
                "sourceUrl": source_url,
                "provider": provider,
                "region": region,
                "area": area,
                "originSite": "camaramar",
            }
        )
    return out


def skyline_region_area(country_slug: str, area_slug: str) -> tuple[str, str]:
    area = SKYLINE_AREA_MAP.get(area_slug, area_slug.replace("-", " ").title())
    region = "Spain" if country_slug == "espana" else "Portugal"
    return (region, area)


def load_skyline_entries(country_slug: str) -> list[dict]:
    fpath = ROOT / f"skyline_{country_slug}.html"
    if not fpath.exists():
        return []
    doc = fpath.read_text(encoding="utf-8", errors="ignore")

    out = []
    pattern = re.compile(
        rf'<a href="(en/webcam/{country_slug}/[^"]+\.html)"[^>]*>\s*<div class="cam-light">.*?<p class="tcam">(.*?)</p><p class="subt">(.*?)</p>',
        re.I,
    )
    for m in pattern.finditer(doc):
        rel = m.group(1)
        title = html.unescape(m.group(2)).strip()
        subtitle = html.unescape(m.group(3)).strip()
        full = "https://www.skylinewebcams.com/" + rel.lstrip("/")
        parts = rel.split("/")
        area_slug = parts[3] if len(parts) > 3 else country_slug
        region, area = skyline_region_area(country_slug, area_slug)

        out.append(
            {
                "title": title,
                "subtitle": subtitle,
                "path": "/" + rel,
                "status": "external",
                "sourceType": "external-page",
                "sourceUrl": full,
                "provider": "skylinewebcams.com",
                "region": region,
                "area": area,
                "originSite": "skylinewebcams",
            }
        )
    return out


def load_windy_root_entries() -> list[dict]:
    fpath = ROOT / "windy_coast_root_sources.csv"
    if not fpath.exists():
        return []

    rows = list(csv.DictReader(fpath.open(newline="", encoding="utf-8")))
    out = []

    for row in rows:
        source_url = row.get("root_source_url", "").strip()
        if not source_url:
            continue
        if has_embedded_credentials(source_url):
            continue

        source_type = detect_source_type(source_url)
        status = "live" if source_type in {"hls", "dash", "iframe", "embed"} else "external"

        title = row.get("title", "").strip() or f"Windy Coast Cam {row.get('windy_id', '').strip()}"
        windy_url = row.get("windy_url", "").strip()
        city = row.get("city", "").strip()
        subcountry = row.get("subcountry", "").strip()
        country = row.get("country", "").strip()

        region, area = classify_region_area(
            f"{source_url} {country} {subcountry} {city}",
            title,
        )

        lat = row.get("lat", "").strip()
        lng = row.get("lng", "").strip()
        fixed_lat = None
        fixed_lng = None
        try:
            fixed_lat = float(lat)
            fixed_lng = float(lng)
        except Exception:
            fixed_lat = None
            fixed_lng = None

        entry = {
            "title": title,
            "subtitle": "Root source discovered from Windy coastal webcam index",
            "path": windy_url or source_url,
            "status": status,
            "sourceType": source_type,
            "sourceUrl": source_url,
            "provider": host_of(source_url) or "unknown",
            "region": region,
            "area": area,
            "originSite": "windy-root",
        }

        if isinstance(fixed_lat, float) and isinstance(fixed_lng, float):
            entry["fixedLat"] = fixed_lat
            entry["fixedLng"] = fixed_lng

        out.append(entry)

    return out


def load_catalonia_ports_audit_entries() -> list[dict]:
    fpath = ROOT / "catalonia_ports_cameras.csv"
    if not fpath.exists():
        return []

    rows = list(csv.DictReader(fpath.open(newline="", encoding="utf-8")))
    out = []

    for row in rows:
        port_name = row.get("port_name", "").strip()
        port_key = normalize_text(port_name).replace("  ", " ").strip()

        if port_key in PORTS_EXCLUDED_BY_REQUEST:
            continue

        if port_key in BADALONA_PORT_NAME_KEYS:
            raw_links = BADALONA_INLINE_SOURCES[:]
        elif port_key in CASTELLDEFELS_17NUDOS_KEYS:
            extracted = []
            try:
                extracted = extract_17nudos_cam_links(row.get("official_port_url", "").strip())
            except Exception:
                extracted = []
            fallback_links = [x.strip() for x in row.get("camera_links", "").split(" | ") if x.strip()]
            raw_links = extracted or fallback_links
        elif port_key in PORT_GINESTA_NAME_KEYS:
            extracted = []
            try:
                extracted = extract_port_ginesta_cam_links(row.get("official_port_url", "").strip())
            except Exception:
                extracted = []
            fallback_links = [x.strip() for x in row.get("camera_links", "").split(" | ") if x.strip()]
            raw_links = extracted or fallback_links
        else:
            raw_links = [x.strip() for x in row.get("camera_links", "").split(" | ") if x.strip()]

        if not raw_links:
            continue

        area = row.get("area", "Catalonia Ports").strip()
        official_url = row.get("official_port_url", "").strip()

        for idx, link in enumerate(raw_links, start=1):
            resolved_link = link
            if parse_windy_webcam_id(link):
                resolved, _detail = resolve_windy_root_source(link)
                resolved_link = resolved or link

            if port_key in BADALONA_PORT_NAME_KEYS:
                source_type = "iframe"
                status = "live"
            else:
                source_type = detect_source_type(resolved_link)
                status = "live" if source_type in {"hls", "dash", "iframe", "embed"} else "external"
            title = port_name if len(raw_links) == 1 else f"{port_name} Cam {idx}"

            out.append(
                {
                    "title": title,
                    "subtitle": "Catalonia ports audit source",
                    "path": official_url or f"/ports/{normalize_text(port_name).replace(' ', '-')}",
                    "status": status,
                    "sourceType": source_type,
                    "sourceUrl": resolved_link,
                    "provider": host_of(resolved_link) or "unknown",
                    "region": "Catalonia",
                    "area": area,
                    "originSite": "ports-catalonia",
                }
            )

    return out


def dedupe_entries(entries: list[dict]) -> list[dict]:
    out = []
    seen = set()

    for e in entries:
        blob = normalize_text(
            " ".join(
                [
                    e.get("title", ""),
                    e.get("path", ""),
                    e.get("sourceUrl", ""),
                    e.get("subtitle", ""),
                ]
            )
        )
        if any(normalize_text(term) in blob for term in GLOBAL_BLOCK_TERMS):
            continue

        key = (e.get("originSite"), e.get("path"), e.get("sourceUrl"), e.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)

    return out


def main() -> None:
    entries = []
    entries.extend(load_camaramar_entries())
    entries.extend(load_skyline_entries("espana"))
    entries.extend(load_skyline_entries("portugal"))
    entries.extend(load_catalonia_ports_audit_entries())
    entries.extend(load_windy_root_entries())

    merged = dedupe_entries(entries)
    geocode_cache = load_geocode_cache()
    place_cache: dict[str, tuple[float, float] | None] = {}
    stats = {"new_geocodes": 0, "cache_hits": 0, "resolved_now": 0, "fallback": 0}

    for idx, item in enumerate(merged, start=1):
        base = resolve_base_coordinate(item, geocode_cache, place_cache, stats)
        lat, lng = camera_coordinates(item, base)
        item["lat"] = lat
        item["lng"] = lng
        item.pop("fixedLat", None)
        item.pop("fixedLng", None)
        if idx % 100 == 0:
            print(
                f"Placed {idx}/{len(merged)} cameras (new: {stats['new_geocodes']}, cache: {stats['cache_hits']}, fallback: {stats['fallback']})",
                flush=True,
            )

    save_geocode_cache(geocode_cache)

    merged.sort(key=lambda x: (x.get("region", ""), x.get("area", ""), x.get("title", "")))

    (ROOT / "merged_cameras.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "cameras.js").write_text(
        "export const CAMERAS = " + json.dumps(merged, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )

    print("Merged cameras:", len(merged))
    print("Regions:", Counter(e.get("region", "") for e in merged))
    print("Areas:", len({e.get("area", "") for e in merged}))
    print("Status:", Counter(e.get("status", "") for e in merged))
    print("Origin:", Counter(e.get("originSite", "") for e in merged))
    print("Geocoder cache size:", len(geocode_cache))
    print("New geocodes this run:", stats["new_geocodes"])
    print("Resolved from cache:", stats["cache_hits"])
    print("Resolved from new geocodes:", stats["resolved_now"])
    print("Fallback centroid count:", stats["fallback"])


if __name__ == "__main__":
    main()
