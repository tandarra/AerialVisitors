#!/usr/bin/env python3
"""
Aircraft illustrations in the Avian Visitors / kachō-e woodblock style, for the Aerial Atlas and the live
"Overhead" page. The plane twin of bird_illustrations.py.

Species list = ICAO aircraft type designators (A20N, B789, AT76, C172...). Every country's register
(what flies under its flag) is the "checklist". Build the lists first:  python tools/build_reference.py

Asks Gemini to paint each type as a woodblock print on cream paper, then cuts the background away.

Keys: put them in bird_keys.txt (or plane_keys.txt) next to this script, or set environment variables:
    GEMINI_API_KEY=...        (Google AI Studio, billing enabled; ~US$0.034 per image)
Install once:
    pip install requests pillow "rembg[cpu]"

Typical runs:
    python plane_illustrations.py --country NZ --top 50 --list-only     # what's on the NZ checklist + cost
    python plane_illustrations.py --country NZ --airliners --list-only  # just the airliners and turboprops
    python plane_illustrations.py --sightings --list-only               # everything logged overhead at home
    python plane_illustrations.py --types A20N B789 AT76 --limit 3      # test: a few types
    python plane_illustrations.py --country NZ --top 50 --style-ref planes/raw/a20n.png
    python plane_illustrations.py --list paint_next.txt                 # list exported from the atlas ("Paint next")
    python plane_illustrations.py --livery A320:ANZ --livery AT76:ANZ   # an operator's colours on a type
    python plane_illustrations.py --cutout-only                         # cut out images you made by hand
    python plane_illustrations.py --progress --country NZ --top 100     # master index for a country

To redo a bad image: delete it from planes/raw/ and run again for that type.

Output:
    planes/raw/<type>.png / <type>-2.png     originals (side profile / from below)
    planes/<type>.webp / <type>-2.webp       cut-outs used by the pages     (type slug = ICAO code, lower case)
    planes/<type>-<opr>.webp / -<opr>-2.webp operator liveries (opr = ICAO airline code, e.g. a320-anz)
"""
import argparse, base64, io, json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
COST_PER_IMAGE = 0.034
PAINTABLE = set("LSAHGT")      # ICAO description class: Land, Sea, Amphibian, Helicopter, Gyro, Tilt-rotor

# Prompt adapted from Avian Visitors by Teddy Warner (CC-BY-NC-SA-4.0), same house style as the birds.
PROMPT = (
    "Generate a {pose} {name} (ICAO type {code}) in the style of an Edo-period Japanese woodblock print, "
    "painted as carefully as a kacho-e bird. "
    "Render with VERY FEW MARKS: the aircraft is 2-4 flat colour zones with sharp boundaries, no rivets, no panel lines, "
    "no windows drawn one by one. Confident sumi-e ink linework, soft watercolour washes. "
    "Earthy palette: burnt umber, ochre, indigo, vermillion, muted greens. "
    "{livery}\n\n"
    "The aircraft sits on a CONSISTENT WARM CREAM ground (aged mulberry paper), filling the frame, identical across "
    "every print. This is the only background: NO sky, NO clouds, NO runway, NO ground, NO scenery, NO text, "
    "NO lettering, NO logos, NO registration marks.\n\n"
    "- Correct anatomy for a {name}: the right number and position of engines, wings, tail surfaces and landing gear "
    "(or rotors and skids) as the real type has them.\n"
    "- {rule}"
)
LIVERY_GENERIC = "Plain neutral livery: bare white and grey with one indigo stripe. No airline colours."
LIVERY_OPR = ("Painted in the colour scheme of {opr} as 2-3 simple flat colour blocks (fuselage, tail, engines). "
              "Colour only: NO logos, NO lettering, NO emblems.")
POSES = {
    "": dict(pose="side-profile view of a", rule="Side profile, level flight, undercarriage retracted (skids or wheels "
                                                  "tucked for a helicopter: show it in a steady hover). Nose to the right."),
    "-2": dict(pose="three-quarter front view from slightly below, banking and climbing, of a",
               rule="Seen from below and ahead, climbing away over the viewer, one wing lower than the other, "
                    "as you would see it passing overhead."),
}
STYLE_NOTE = ("\n\nReference images are attached. {notes}"
              "Produce ONE new image of ONE aircraft on its own 1:1 canvas.")


def slug(code):
    return re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")


def load_types():
    p = ROOT / "planes" / "types.json"
    if not p.exists():
        sys.exit("planes/types.json is missing: run  python tools/build_reference.py  first.")
    return json.loads(p.read_text(encoding="utf-8"))


def load_operators():
    p = ROOT / "planes" / "operators.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def paintable(info):
    return bool(info[0]) and info[1][:1] in PAINTABLE


def is_airliner(info):
    """Medium/heavy multi-engine jets and turboprops (A320, B789, AT76...): what you see passing overhead."""
    d = info[1]
    return len(d) == 3 and d[0] == "L" and d[1] in "234" and d[2] in "JT" and info[2] in ("M", "H")


def country_types(code, top, types, airliners=False):
    """Types on a country's register, most numerous first, limited to paintable kinds."""
    wp = ROOT / "planes" / "world.json"
    if not wp.exists():
        sys.exit("planes/world.json is missing: run  python tools/build_reference.py  first.")
    w = json.loads(wp.read_text(encoding="utf-8"))
    c = next((c for c in w["countries"] if c["code"] == code.upper()), None)
    if not c:
        sys.exit(f"No register for '{code}'. Codes are ISO 2-letter, e.g. NZ, AU, US, GB.")
    out = []
    for i in c["sp"]:
        t = w["types"][i]
        if t[0] in types and paintable(types[t[0]]) and (not airliners or is_airliner(types[t[0]])):
            out.append(t[0])
    return out[:top] if top else out


def img_part(path):
    data = Path(path).read_bytes()
    mime = {".png": "image/png", ".webp": "image/webp"}.get(Path(path).suffix.lower(), "image/jpeg")
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}


class OutOfCredit(Exception):
    pass


def paint(gkey, model, code, name, pose_kw, livery, style_ref=None, photo_ref=None, tries=4):
    import requests
    text = PROMPT.format(code=code, name=name, livery=livery, **pose_kw)
    parts, notes, n = [], "", 1
    if style_ref:
        parts.append(img_part(style_ref))
        notes += (f"Image {n} is the STYLE reference: match its style, line weight, palette, level of detail "
                  f"and cream ground exactly, but do NOT copy its aircraft type. ")
        n += 1
    if photo_ref:
        parts.append(img_part(photo_ref))
        notes += f"Image {n} is a photo of a real {name}: use it ONLY for the aircraft's shape and proportions. "
    if parts:
        text += STYLE_NOTE.format(notes=notes)
    body = {"contents": [{"parts": [{"text": text}] + parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}}
    for attempt in range(1, tries + 1):
        r = requests.post(GEMINI.format(model=model), headers={"x-goog-api-key": gkey}, json=body, timeout=120)
        if r.status_code == 402:
            raise OutOfCredit(r.text[:300])
        if r.status_code == 429 or r.status_code >= 500:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except Exception:
                msg = r.text[:300]
            if r.status_code == 429 and ("limit: 0" in msg or "billing" in msg.lower()):
                sys.exit(f"\nGemini says this key has no image quota:\n  {msg[:400]}\n"
                         "Enable billing for this key's project in AI Studio, then run again.")
            wait = 30 * attempt
            print(f"    server busy ({r.status_code}): {msg[:160]}\n    retrying in {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        for cand in r.json().get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                data = part.get("inlineData") or part.get("inline_data")
                if data and data.get("data"):
                    return base64.b64decode(data["data"])
        print("    no image returned, retrying")
    return None


def cutout(png_bytes, remover):
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    cut = remover(img)
    box = cut.getbbox()
    if box:
        pad = 12
        cut = cut.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                        min(box[2] + pad, cut.width), min(box[3] + pad, cut.height)))
    cut.thumbnail((512, 512))
    return cut


def write_painted(out):
    """planes/painted.json: every cut-out by base slug (type or type-operator), for the atlas and the live page."""
    pics = {}
    for p in sorted(out.glob("*.webp"), key=lambda p: (p.stem.endswith("-2"), p.stem)):   # side profile first
        m = re.fullmatch(r"(.+?)(-2)?", p.stem)
        pics.setdefault(m.group(1), []).append(p.name)
    (out / "painted.json").write_text(json.dumps(pics, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------- PROGRESS
def build_progress(codes, types, out, region):
    import csv, datetime
    rows = []
    for code in codes:
        s = slug(code)
        side, below = (out / f"{s}.webp").exists(), (out / f"{s}-2.webp").exists()
        rows.append(dict(code=code, name=types[code][0], slug=s, side=side, below=below,
                         status="ok" if side and below else ("part" if side or below else "miss"),
                         webp=[p.name for p in (out / f"{s}.webp", out / f"{s}-2.webp") if p.exists()]))
    with open(out / f"master_index_{region}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ICAO type", "Name", "File name", "Side profile", "From below", "Status"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["slug"], "yes" if r["side"] else "", "yes" if r["below"] else "",
                        {"ok": "Complete", "part": "Partial", "miss": "Missing"}[r["status"]]])
    n = len(rows); done = sum(r["status"] == "ok" for r in rows); part = sum(r["status"] == "part" for r in rows)
    (out / f"progress_{region}.json").write_text(json.dumps({
        "region": region, "updated": datetime.datetime.now().isoformat(timespec="minutes"),
        "total": n, "done": done, "part": part, "miss": n - done - part, "types": rows},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n{region}: {done}/{n} complete, {part} partial, {n - done - part} not started.")
    print(f"Wrote {out / f'master_index_{region}.csv'} and {out / f'progress_{region}.json'}")


def sighted_types(types):
    p = ROOT / "planes" / "sightings.json"
    if not p.exists():
        sys.exit("planes/sightings.json is missing: run  python tools/log_sightings.py  first.")
    seen = json.loads(p.read_text(encoding="utf-8")).get("types", {})
    return [c for c, _ in sorted(seen.items(), key=lambda kv: -kv[1].get("n", 0)) if c in types and paintable(types[c])]


def parse_list(path, types):
    """Lines like 'AIRBUS A-320neo (A20N)', or just 'A20N'."""
    codes = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        m = re.search(r"\(([A-Z0-9]{2,4})\)\s*$", line) or re.fullmatch(r"\s*([A-Z0-9]{2,4})\s*", line)
        if m and m.group(1) in types:
            codes.append(m.group(1))
    if not codes:
        sys.exit(f"No 'Name (ICAO)' lines matching known types found in {path}")
    return codes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", help="ISO 2-letter register to paint, e.g. NZ (types flying under that flag)")
    ap.add_argument("--top", type=int, default=0, help="only the N most numerous types on that register")
    ap.add_argument("--airliners", action="store_true", help="with --country: only airliners/turboprops/bizjets (what flies overhead)")
    ap.add_argument("--sightings", action="store_true", help="paint every type logged overhead in planes/sightings.json")
    ap.add_argument("--types", nargs="+", help="ICAO type codes to paint, e.g. A20N B789")
    ap.add_argument("--list", help="paint the types in this file ('Name (ICAO)' per line, e.g. paint_next.txt from the atlas)")
    ap.add_argument("--livery", action="append", help="TYPE:OPR, an operator's colours on a type, e.g. A320:ANZ (repeatable)")
    ap.add_argument("--limit", type=int, help="stop after this many new paintings")
    ap.add_argument("--force", action="store_true", help="repaint even if a file exists")
    ap.add_argument("--model", default="gemini-nano-banana-2.1")
    ap.add_argument("--style-ref", help="image whose style every aircraft should match (your best one)")
    ap.add_argument("--refs", default=None, help="folder of photos named <type>.jpg/png (default: planes/refs)")
    ap.add_argument("--out", default="planes")
    ap.add_argument("--list-only", action="store_true", help="just print the list and the cost estimate")
    ap.add_argument("--progress", action="store_true", help="write planes/master_index_<country>.csv + progress_<country>.json")
    ap.add_argument("--cutout-only", action="store_true", help="no API calls: cut out every image already in planes/raw/")
    a = ap.parse_args()
    out, raw = ROOT / a.out, ROOT / a.out / "raw"

    if a.cutout_only:
        from rembg import remove, new_session
        session = new_session("u2net")
        files = [p for p in sorted(raw.glob("*")) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        if not files:
            sys.exit(f"No images found in {raw}")
        n = 0
        for p in files:
            m = re.fullmatch(r"(.*?)[-_]?([2-9])", p.stem)          # "a20n2.png" / "a20n_2.png" -> "a20n-2.webp"
            target = out / f"{(m.group(1) + '-' + m.group(2)) if m else p.stem}.webp"
            if target.exists() and not a.force and target.stat().st_mtime >= p.stat().st_mtime:
                continue
            print(f"  cutting out {p.name} -> {target.name}")
            cutout(p.read_bytes(), lambda im: remove(im, session=session)).save(target, "WEBP", quality=88)
            n += 1
        write_painted(out)
        print(f"\nCut out {n} image(s).")
        return

    keyfile = next((ROOT / k for k in ("plane_keys.txt", "bird_keys.txt") if (ROOT / k).exists()), None)
    if keyfile:
        for line in keyfile.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == "GEMINI_API_KEY" and v.strip() and "paste-your" not in v:
                os.environ.setdefault("GEMINI_API_KEY", v.strip().strip('"').strip("'"))
    gkey = os.environ.get("GEMINI_API_KEY")

    types, operators = load_types(), load_operators()
    if a.progress:
        if not a.country:
            sys.exit("--progress needs --country, e.g. --progress --country NZ --top 100")
        out.mkdir(parents=True, exist_ok=True)
        build_progress(country_types(a.country, a.top, types, a.airliners), types, out, a.country.upper())
        write_painted(out)
        return

    jobs = []                                    # (file slug, code, display name, livery text)
    if a.types:
        bad = [t for t in a.types if t.upper() not in types]
        if bad:
            sys.exit(f"Unknown ICAO type(s): {', '.join(bad)}")
    codes = ([t.upper() for t in a.types] if a.types else parse_list(a.list, types) if a.list
             else sighted_types(types) if a.sightings
             else country_types(a.country, a.top, types, a.airliners) if a.country else [])
    for c in codes:
        jobs.append((slug(c), c, types[c][0], LIVERY_GENERIC))
    for spec in a.livery or []:
        c, _, o = spec.upper().partition(":")
        if c not in types or o not in operators or o == "ZZZ":
            sys.exit(f"--livery {spec}: need a known ICAO type and a known ICAO airline code (e.g. A320:ANZ)")
        jobs.append((f"{slug(c)}-{slug(o)}", c, types[c][0], LIVERY_OPR.format(opr=operators[o][0])))
    if not jobs:
        sys.exit("Nothing to paint: give --country (with --top), --types, --list or --livery. See --help.")
    jobs.sort(key=lambda j: j[2])
    print(f"{len(jobs)} aircraft")
    if a.list_only:
        for s, c, n, _ in jobs:
            print(f"  {s:9s} {n}")
    todo = sum(1 for s, *_ in jobs for suf in POSES if a.force or not (raw / f"{s}{suf}.png").exists())
    print(f"{todo} new image(s) to paint, about US${todo * COST_PER_IMAGE:.2f} on Nano Banana 2.1")
    if a.list_only:
        return
    if not gkey:
        sys.exit("No Gemini key: add GEMINI_API_KEY=... to plane_keys.txt next to this script.")

    from rembg import remove, new_session
    session = new_session("u2net")
    remover = lambda im: remove(im, session=session)
    raw.mkdir(parents=True, exist_ok=True)
    refs_dir = Path(a.refs) if a.refs else out / "refs"
    failed, done = [], 0
    for s, code, name, livery in jobs:
        photo = next((p for p in [refs_dir / f"{s}{e}" for e in (".jpg", ".jpeg", ".png", ".webp")] if p.exists()), None)
        for suffix, kw in POSES.items():
            target, have = out / f"{s}{suffix}.webp", raw / f"{s}{suffix}.png"
            if have.exists() and not a.force:           # planes/raw/ is the source of truth
                if not target.exists():
                    print(f"  cutting out {have.name} (no repaint needed)")
                    cutout(have.read_bytes(), remover).save(target, "WEBP", quality=88)
                continue
            if a.limit and done >= a.limit:
                break
            print(f"  painting {name} ({'from below' if suffix else 'side'}){' + photo ref' if photo else ''}")
            try:
                png = paint(gkey, a.model, code, name, kw, livery, a.style_ref, photo)
            except OutOfCredit:
                sys.exit(f"\nOut of Gemini credit (402) after {done} new image(s). Top up in AI Studio and run the "
                         "same command again: everything already painted is skipped.")
            if not png:
                print("    FAILED, will retry at the end")
                failed.append((s, code, name, livery, suffix, kw, photo))
                continue
            have.write_bytes(png)
            cutout(png, remover).save(target, "WEBP", quality=88)
            done += 1
            time.sleep(2)
    if failed:
        print(f"\n{len(failed)} image(s) failed; waiting 2 minutes, then one more try each")
        time.sleep(120)
        for s, code, name, livery, suffix, kw, photo in failed:
            png = paint(gkey, a.model, code, name, kw, livery, a.style_ref, photo)
            if png:
                (raw / f"{s}{suffix}.png").write_bytes(png)
                cutout(png, remover).save(out / f"{s}{suffix}.webp", "WEBP", quality=88)
                done += 1
            else:
                print(f"  still missing: {name} ({s}{suffix})")
    write_painted(out)
    print(f"\nPainted {done} new. Review planes/raw/, delete any duds and run again to redo them.")


if __name__ == "__main__":
    main()
