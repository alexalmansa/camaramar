# Webmar Source Map

Checked on: **2026-03-03**
Seed page: <https://www.camaramar.com/webcam/sitges>

Method used:
1. Collected nearby camera links from the Sitges page (`data-href="/webcam/..."`).
2. Opened each page and inspected the main `#webcam` block.
3. Extracted actual stream origin by pattern:
   - `iframe src="..."`
   - `source src="..."`
   - `player.src({ src: '...' })`
   - `const url = "..."` (dash.js embeds)

| Camera | Path | Status on source site | Type | Provider | Stream/Embed |
|---|---|---|---|---|---|
| Playa de Sitges | `/webcam/sitges` | live | iframe | `ipcamlive.com` | `https://ipcamlive.com/player/player.php?alias=65d33d2760353` |
| Punta Prima, Salou | `/webcam/punta-prima-salou` | live | hls | `5940924978228.streamlock.net` | `https://5940924978228.streamlock.net:443/8115/8115/playlist.m3u8` |
| Playa de Alboraya | `/webcam/alboraya-port-saplaya` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/AlborayaPortSaplaya/manifest.mpd` |
| Playa de la Patacona | `/webcam/comunidad-valenciana_valencia_patacona` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/AlborayaPatacona/manifest.mpd` |
| Port Andratx | `/webcam/illes-balears_portandratx` | live | hls | `wow.camaramar.com` | `https://wow.camaramar.com/camaramar/66_andratx.stream/playlist.m3u8` |
| Playa de Benicarlo | `/webcam/playa-de-benicarlo` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/Benicarlo/manifest.mpd` |
| Playa de Canet d'En Berenguer | `/webcam/playa-de-canet` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/CanetdeBerenguer/manifest.mpd` |
| Playa de Pobla de Farnals | `/webcam/playa-de-pobla-de-farnals` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/PobladeFarnals/manifest.mpd` |
| Playa del Forti | `/webcam/playa-del-forti` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/Vinaros/manifest.mpd` |
| Playa Voramar | `/webcam/playa-voramar` | live | dash | `streaming.comunitatvalenciana.com` | `https://streaming.comunitatvalenciana.com/webcam/BenicassimPalasiet/manifest.mpd` |
| Playa el Masnou | `/webcam/cataluna_barcelona_masnou` | locked | none | subscription | n/a |
| Playa del Gurugu | `/webcam/comunidad-valenciana_castellon_gurugu` | locked | none | subscription | n/a |
| Playa del Alguer | `/webcam/playa-del-alguer` | locked | none | subscription | n/a |
| Cala dels Llenguadets, Salou | `/webcam/cala-dels-llenguadets-salou` | offline | none | out-of-service | n/a |
| Platja de Llevant - Els Pilons | `/webcam/platja-de-llevant-els-pilons` | offline | none | out-of-service | n/a |
| Platja Llarga, Salou | `/webcam/platja-llarga-salou` | offline | none | out-of-service | n/a |
| Playa de la Peniscola | `/webcam/playa-de-la-peniscola` | offline | none | out-of-service | n/a |
