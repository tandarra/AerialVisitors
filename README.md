# Aerial Visitors

Woodblock-style illustrations of every kind of aircraft, built the same way as
[Avian Visitors — New Zealand](https://github.com/tandarra/avianvisitors-NewZealand), but for planes.
The style follows the [Avian Visitors](https://theodore.net/projects/AvianVisitors/) guidelines by Teddy Warner:
very few marks, flat colour zones, sumi-e ink linework, cream mulberry-paper ground.

| Bird project | Aerial Visitors |
|---|---|
| eBird species | **ICAO aircraft type** (`A20N`, `B789`, `AT76`, `C172`, ...): 2,779 of them |
| a country's eBird list | a country's **register**: what flies under its flag (185 registers, from ICAO address blocks) |
| BirdNET-Go detections | **ADS-B sightings** of what actually passes overhead |
| perched / in flight | **side profile** / **from below, climbing** |
| a bird's plumage | an **airline's colours** on a type (`a320-anz`), colour blocks only |
| Bird Atlas | **Aerial Atlas** ([`atlas.html`](atlas.html)): world map shaded by how much of each register is painted |
| "Birds heard today" | **Overhead Now** ([`index.html`](index.html)): what's in the sky over your station right now |

**Status:** the tooling and both pages are built and tested; no paintings have been generated yet.
The first run of `plane_illustrations.py` (needs a Gemini key) fills the atlas in.

## What's in here

| Path | What it is |
|---|---|
| `tools/build_reference.py` | Downloads the type list, airline list and every country's register, writes the three files below (runs daily on GitHub) |
| `planes/types.json` | ICAO type designators: name, class (`L2J` = landplane, 2 jet engines), wake category |
| `planes/operators.json` | ICAO airline designators: name, country, radio callsign (maps `ANZ452` to Air New Zealand) |
| `planes/world.json` | Every register as type indexes with airframe counts: powers the atlas |
| `plane_illustrations.py` | Generator: paints types with Gemini, cuts out the background, builds progress lists |
| `planes/raw/` | Paintings as generated (keep these; delete a dud and re-run to repaint it) |
| `planes/<type>.webp`, `<type>-2.webp` | Cut-outs: side profile and from below. Slug = ICAO code, lower case |
| `planes/<type>-<opr>.webp` | An operator's colours on a type, e.g. `a320-anz.webp` |
| `planes/painted.json` | Index of cut-outs, written by the generator |
| `tools/log_sightings.py` | Logs aircraft near home into a life list; writes `planes/seen.json` for the site |
| `atlas.html`, `vendor/`, `planes/world-110m.json` | The world map and checklists (d3-geo + Natural Earth 110m) |
| `index.html`, `functions/api/overhead.js`, `lib/adsb.js` | The live page and its API (adsb.lol, cached 8 s) |
| `worker.js`, `wrangler.jsonc` | The same site as a Cloudflare Worker instead of Pages |

## Workflow

Needs Python 3 with `pip install requests pillow "rembg[cpu]"`. Put your key in `plane_keys.txt` (git-ignored):

```
GEMINI_API_KEY=...
HOME_LATLNG=-37.25,175.02
```

```powershell
# 1. Reference data (a few seconds, ~10 MB). Also runs daily on GitHub.
python tools/build_reference.py

# 2. See what's on a checklist, and what it will cost
python plane_illustrations.py --country NZ --airliners --list-only
python plane_illustrations.py --country NZ --top 50 --list-only

# 3. Paint. Start with one to set the style, then use it as the reference for the rest
python plane_illustrations.py --types A20N --limit 2
python plane_illustrations.py --country NZ --airliners --style-ref planes/raw/a20n.png

# 4. Log what actually flies over your house, then paint exactly those types
python tools/log_sightings.py --loop 30            # leave running on the homelab
python plane_illustrations.py --sightings --style-ref planes/raw/a20n.png

# 5. An airline's colours on a type
python plane_illustrations.py --livery A320:ANZ --livery AT76:ANZ

# 6. Paint a list downloaded from the atlas ("Paint next")
python plane_illustrations.py --list paint_next_NZ_2026-10-28.txt --style-ref planes/raw/a20n.png

# Made images by hand (Gemini app)? Save as planes\raw\<type>.png / <type>-2.png, then
python plane_illustrations.py --cutout-only

# Rebuild a country's progress checklist
python plane_illustrations.py --progress --country NZ --top 100
```

Then commit and push. To look at it locally: `python -m http.server`, then open `atlas.html`
(`index.html` needs the Cloudflare Function for live data; without it the page says so and still shows the life list).

## Notes

* **Registers are mostly light aircraft.** New Zealand's top types by airframe count are ultralights, Cessna 172s and
  gliders; the A21N and AT76 you hear overhead rank lower. Use `--airliners` for what passes by, and `--sightings`
  for what actually did.
* **No logos.** Liveries are colour blocks only; the prompt forbids lettering, emblems and registration marks.
  Airline names and colours are their owners' trademarks: non-commercial use only.
* **Privacy.** `planes/sightings.json` (every airframe plus your home position) is git-ignored. Only
  `planes/seen.json` (types and counts) is meant to be published. Home coordinates in `wrangler.jsonc` are public
  if you push the repo: change them to somewhere nearby if you'd rather not publish your exact patch of sky.
* **Cost:** about US$0.034 per image on Nano Banana 2.1, two images per type.

## Licence

Illustrations and code are shared under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), matching Avian Visitors, whose prompt template
and style guidelines this project adapts. Non-commercial use only, with attribution. Images are generated with Google Gemini.
