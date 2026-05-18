import { CAMERAS } from "./cameras.js";

const regionStep = document.getElementById("region-step");
const compareStep = document.getElementById("compare-step");
const regionGrid = document.getElementById("region-grid");
const backRegionsBtn = document.getElementById("back-regions");
const compareRegionName = document.getElementById("compare-region-name");
const compareMeta = document.getElementById("compare-meta");
const mapMeta = document.getElementById("map-meta");
const areaFilters = document.getElementById("area-filters");
const statusFilters = document.getElementById("status-filters");
const originFilters = document.getElementById("origin-filters");
const compareSearch = document.getElementById("compare-search");
const cameraGrid = document.getElementById("camera-grid");
const cameraEmpty = document.getElementById("camera-empty");

const cameraCount = document.getElementById("camera-count");
const liveCount = document.getElementById("live-count");
const externalCount = document.getElementById("external-count");
const areaCount = document.getElementById("area-count");
const regionCount = document.getElementById("region-count");

const players = [];
const markersByCameraId = new Map();

function playableHost(camera) {
  try {
    return new URL(camera.sourceUrl || "").hostname.toLowerCase();
  } catch {
    return "";
  }
}

function isVerifiedPlayableCamera(camera) {
  const type = String(camera.sourceType || "").toLowerCase();
  const host = playableHost(camera);

  if (type === "hls" || type === "dash") return true;
  if (type !== "iframe" && type !== "embed") return false;

  return (
    host === "www.youtube.com" ||
    host === "youtube.com" ||
    host === "camstreamer.com" ||
    host === "player.twitch.tv"
  );
}

const PLAYABLE_CAMERAS = CAMERAS.filter(isVerifiedPlayableCamera);

const CAMERAS_WITH_ID = PLAYABLE_CAMERAS.map((camera, index) => ({
  ...camera,
  id: index,
  status: "live"
}));

let selectedRegion = null;
let selectedArea = "all";
let selectedStatus = "all";
let selectedOrigin = "all";
let query = "";

let map = null;
let markerLayer = null;

function regionName(camera) {
  return camera.region || "Unsorted";
}

function areaName(camera) {
  return camera.area || "Unsorted";
}

function providerName(camera) {
  return camera.provider || "unknown";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function destroyPlayers() {
  for (const item of players) {
    if (item.type === "hls" && item.player) item.player.destroy();
    if (item.type === "dash" && item.player) item.player.reset();
  }
  players.length = 0;
}

function buildOriginUrl(camera) {
  if (camera.originSite === "camaramar" && String(camera.path || "").startsWith("/")) {
    return `https://www.camaramar.com${camera.path}`;
  }
  return camera.sourceUrl;
}

function buildPlayableUrl(camera) {
  const type = String(camera.sourceType || "").toLowerCase();
  const host = playableHost(camera);

  if ((type === "iframe" || type === "embed") && host === "player.twitch.tv") {
    const url = new URL(camera.sourceUrl);
    url.searchParams.set("parent", window.location.hostname);
    return url.toString();
  }

  return camera.sourceUrl;
}

function isImageUrl(url) {
  return /\.(png|jpe?g|webp|gif)(\?|$)/i.test(url);
}

function mountMedia(camera, mount) {
  const type = (camera.sourceType || "").toLowerCase();
  const url = buildPlayableUrl(camera);

  if (type === "iframe" || type === "embed") {
    const frame = document.createElement("iframe");
    frame.src = url;
    frame.loading = "lazy";
    frame.allow = "autoplay; fullscreen";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.title = camera.title;
    mount.appendChild(frame);
    return;
  }

  if (type === "hls") {
    const video = document.createElement("video");
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = "none";
    mount.appendChild(video);

    if (window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        liveSyncDurationCount: 3,
        maxLiveSyncPlaybackRate: 1.2
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      players.push({ type: "hls", player: hls });
      return;
    }

    video.src = url;
    return;
  }

  if (type === "dash") {
    const video = document.createElement("video");
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = "none";
    mount.appendChild(video);

    if (window.dashjs) {
      const dash = window.dashjs.MediaPlayer().create();
      dash.initialize(video, url, false);
      players.push({ type: "dash", player: dash });
      return;
    }

    video.src = url;
    return;
  }

  if (isImageUrl(url)) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = camera.title;
    img.loading = "lazy";
    img.referrerPolicy = "strict-origin-when-cross-origin";
    mount.appendChild(img);
    return;
  }

  const frame = document.createElement("iframe");
  frame.src = url;
  frame.loading = "lazy";
  frame.allow = "autoplay; fullscreen";
  frame.referrerPolicy = "strict-origin-when-cross-origin";
  frame.title = camera.title;
  mount.appendChild(frame);
}

function getCoordinates(camera) {
  const lat = Number(camera.lat);
  const lng = Number(camera.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return [lat, lng];
}

function cameraIcon(isActive) {
  return window.L.divIcon({
    className: `camera-pin ${isActive ? "is-active" : "is-muted"}`,
    html: "<span aria-hidden='true'>📷</span>",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -12]
  });
}

function ensureMap() {
  if (map || !window.L) return;

  map = window.L.map("region-map", {
    zoomControl: true,
    preferCanvas: true,
    minZoom: 2
  });

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  markerLayer = window.L.layerGroup().addTo(map);
}

function highlightCard(cameraId, shouldScroll = true) {
  const card = document.getElementById(`camera-card-${cameraId}`);
  if (!card) return;

  card.classList.add("is-focused");
  if (card._focusTimeout) clearTimeout(card._focusTimeout);
  card._focusTimeout = setTimeout(() => card.classList.remove("is-focused"), 1400);

  if (shouldScroll) {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function focusMarker(cameraId) {
  if (!map) return;
  const marker = markersByCameraId.get(cameraId);
  if (!marker) return;

  const center = marker.getLatLng();
  map.flyTo(center, Math.max(map.getZoom(), 12), { duration: 0.5 });
  marker.openPopup();
}

function updateMap(regionCameras, visibleCameras) {
  ensureMap();
  if (!map || !markerLayer) return;

  markerLayer.clearLayers();
  markersByCameraId.clear();

  const visibleIds = new Set(visibleCameras.map((camera) => camera.id));
  const visibleCoords = [];
  const regionCoords = [];

  for (const camera of regionCameras) {
    const coords = getCoordinates(camera);
    if (!coords) continue;

    const isActive = visibleIds.has(camera.id);
    const marker = window.L.marker(coords, {
      icon: cameraIcon(isActive),
      opacity: isActive ? 1 : 0.55,
      keyboard: false,
      zIndexOffset: isActive ? 120 : 0
    });

    const popupHtml =
      `<div class="map-popup">` +
      `<strong>${escapeHtml(camera.title || "Camera")}</strong>` +
      `<p>${escapeHtml(areaName(camera))}</p>` +
      `<p>${escapeHtml(`${camera.status || "unknown"} · ${providerName(camera)}`)}</p>` +
      `<a href="#camera-card-${camera.id}">Open card</a>` +
      `</div>`;

    marker.bindPopup(popupHtml);
    marker.on("click", () => highlightCard(camera.id, true));
    marker.addTo(markerLayer);

    markersByCameraId.set(camera.id, marker);
    regionCoords.push(coords);
    if (isActive) visibleCoords.push(coords);
  }

  if (visibleCoords.length > 0) {
    map.fitBounds(window.L.latLngBounds(visibleCoords), { padding: [26, 26], maxZoom: 13 });
  } else if (regionCoords.length > 0) {
    map.fitBounds(window.L.latLngBounds(regionCoords), { padding: [26, 26], maxZoom: 10 });
  } else {
    map.setView([41.6, 2.2], 6);
  }

  mapMeta.textContent = `${visibleCoords.length} shown · ${regionCoords.length} with coordinates`;
  setTimeout(() => map.invalidateSize(), 0);
}

function getRegionCameras(region) {
  return CAMERAS_WITH_ID.filter((camera) => regionName(camera) === region);
}

function passesFilters(camera) {
  if (selectedArea !== "all" && areaName(camera) !== selectedArea) return false;
  if (selectedStatus !== "all" && camera.status !== selectedStatus) return false;
  if (selectedOrigin !== "all" && camera.originSite !== selectedOrigin) return false;
  if (!query) return true;

  const haystack = [
    camera.title,
    areaName(camera),
    regionName(camera),
    providerName(camera),
    camera.path || "",
    camera.sourceUrl || "",
    camera.originSite || ""
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(query);
}

function renderRegionCards() {
  const grouped = new Map();

  for (const camera of CAMERAS_WITH_ID) {
    const region = regionName(camera);
    if (!grouped.has(region)) {
      grouped.set(region, {
        cameras: 0,
        live: 0,
        areas: new Set()
      });
    }

    const item = grouped.get(region);
    item.cameras += 1;
    if (camera.status === "live") item.live += 1;
    item.areas.add(areaName(camera));
  }

  const rows = Array.from(grouped.entries())
    .map(([region, data]) => ({
      region,
      cameras: data.cameras,
      live: data.live,
      areas: data.areas.size
    }))
    .sort((a, b) => b.cameras - a.cameras || a.region.localeCompare(b.region));

  regionGrid.innerHTML = "";
  for (const row of rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "region-card";
    button.dataset.region = row.region;
    button.innerHTML =
      `<h3>${escapeHtml(row.region)}</h3>` +
      `<p>${row.cameras} cameras · ${row.live} playable · ${row.areas} areas</p>`;
    button.addEventListener("click", () => openRegion(row.region));
    regionGrid.appendChild(button);
  }
}

function renderAreaFilters(regionCameras) {
  const areas = new Map();

  for (const camera of regionCameras) {
    const area = areaName(camera);
    areas.set(area, (areas.get(area) || 0) + 1);
  }

  const sorted = Array.from(areas.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  areaFilters.innerHTML = "";

  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.dataset.area = "all";
  allBtn.className = selectedArea === "all" ? "is-active" : "";
  allBtn.textContent = `All areas (${regionCameras.length})`;
  areaFilters.appendChild(allBtn);

  for (const [area, count] of sorted) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.area = area;
    if (selectedArea === area) btn.className = "is-active";
    btn.textContent = `${area} (${count})`;
    areaFilters.appendChild(btn);
  }
}

function renderCompare() {
  if (!selectedRegion) return;

  destroyPlayers();

  const regionCameras = getRegionCameras(selectedRegion);
  renderAreaFilters(regionCameras);

  const visible = regionCameras
    .filter(passesFilters)
    .sort((a, b) => areaName(a).localeCompare(areaName(b)) || (a.title || "").localeCompare(b.title || ""));

  compareRegionName.textContent = selectedRegion;
  compareMeta.textContent = `${visible.length} shown of ${regionCameras.length} cameras`;

  cameraGrid.innerHTML = "";
  cameraEmpty.hidden = visible.length > 0;

  for (const camera of visible) {
    const card = document.createElement("article");
    card.className = "camera-card";
    card.id = `camera-card-${camera.id}`;

    const head = document.createElement("header");
    head.className = "card-head";
    head.innerHTML =
      `<h3>${escapeHtml(camera.title || "Camera")}</h3>` +
      `<p>${escapeHtml(`${areaName(camera)} · ${providerName(camera)}`)}</p>` +
      `<div class="badges">` +
      `<span class="badge ${camera.status === "live" ? "live" : "external"}">${escapeHtml(camera.status || "unknown")}</span>` +
      `<span class="badge">${escapeHtml(camera.originSite || "unknown")}</span>` +
      `</div>`;

    const media = document.createElement("div");
    media.className = "media";
    mountMedia(camera, media);

    const foot = document.createElement("footer");
    foot.className = "card-foot";

    const sourceCode = document.createElement("code");
    sourceCode.textContent = camera.sourceUrl || "";

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const locateBtn = document.createElement("button");
    locateBtn.type = "button";
    locateBtn.className = "locate-btn";
    locateBtn.dataset.focus = String(camera.id);
    locateBtn.textContent = "Locate on map";

    const sourceLink = document.createElement("a");
    sourceLink.href = buildOriginUrl(camera) || "#";
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    sourceLink.textContent = "Open source page";

    actions.appendChild(locateBtn);
    actions.appendChild(sourceLink);

    foot.appendChild(sourceCode);
    foot.appendChild(actions);

    card.appendChild(head);
    card.appendChild(media);
    card.appendChild(foot);

    cameraGrid.appendChild(card);
  }

  updateMap(regionCameras, visible);
}

function openRegion(region) {
  selectedRegion = region;
  selectedArea = "all";
  selectedStatus = "all";
  selectedOrigin = "all";
  query = "";
  compareSearch.value = "";

  statusFilters.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.filter === "all");
  });

  originFilters.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.origin === "all");
  });

  regionStep.classList.remove("is-active");
  compareStep.classList.add("is-active");

  renderCompare();
}

function backToRegions() {
  destroyPlayers();
  selectedRegion = null;

  regionStep.classList.add("is-active");
  compareStep.classList.remove("is-active");

  cameraGrid.innerHTML = "";
  cameraEmpty.hidden = true;
  mapMeta.textContent = "0 shown";

  if (markerLayer) {
    markerLayer.clearLayers();
    markersByCameraId.clear();
  }
}

function bindControls() {
  backRegionsBtn.addEventListener("click", backToRegions);

  areaFilters.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-area]");
    if (!btn) return;
    selectedArea = btn.dataset.area;
    renderCompare();
  });

  statusFilters.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-filter]");
    if (!btn) return;

    selectedStatus = btn.dataset.filter;
    statusFilters.querySelectorAll("button").forEach((el) => {
      el.classList.toggle("is-active", el === btn);
    });

    renderCompare();
  });

  originFilters.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-origin]");
    if (!btn) return;

    selectedOrigin = btn.dataset.origin;
    originFilters.querySelectorAll("button").forEach((el) => {
      el.classList.toggle("is-active", el === btn);
    });

    renderCompare();
  });

  compareSearch.addEventListener("input", (event) => {
    query = event.target.value.trim().toLowerCase();
    renderCompare();
  });

  cameraGrid.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-focus]");
    if (!btn) return;

    const cameraId = Number(btn.dataset.focus);
    if (!Number.isFinite(cameraId)) return;

    focusMarker(cameraId);
    highlightCard(cameraId, false);
  });
}

function syncCounters() {
  cameraCount.textContent = `${CAMERAS_WITH_ID.length} verified cameras`;
  liveCount.textContent = `${CAMERAS_WITH_ID.length} playable`;
  externalCount.textContent = `${CAMERAS.length - CAMERAS_WITH_ID.length} excluded`;
  areaCount.textContent = `${new Set(CAMERAS_WITH_ID.map((camera) => areaName(camera))).size} areas`;
  regionCount.textContent = `${new Set(CAMERAS_WITH_ID.map((camera) => regionName(camera))).size} regions`;

  const externalFilterBtn = statusFilters.querySelector('[data-filter="external"]');
  if (externalFilterBtn) externalFilterBtn.hidden = true;
}

window.addEventListener("beforeunload", destroyPlayers);

syncCounters();
renderRegionCards();
bindControls();
