#!/usr/bin/env python3
"""
Build planes/catalogue.json: the airline-livery layer of the atlas.

Livery art lives at   planes/liveries/<country>/<airline>/<type>.webp  (+ <type>-2.webp from below),
e.g.                  planes/liveries/new-zealand/air-new-zealand/a320.webp
Fleet lists (liveries/*.json, region = ISO country code) say what each airline flies, so the atlas can show what is
painted and what is still missing. Folders with no fleet entry (e.g. painted from sightings) are listed too.

Run:  python tools/catalogue.py        (the pipeline calls this for you)
"""
import datetime, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def country_names():
    w = json.loads((ROOT / "planes" / "world.json").read_text(encoding="utf-8"))
    return {c["code"]: c["name"] for c in w["countries"]}


def livery_dir(country_name, airline_name):
    return ROOT / "planes" / "liveries" / slug(country_name) / slug(airline_name)


def build():
    names = country_names()
    base = ROOT / "planes" / "liveries"
    countries = {}

    def country(code):
        name = names.get(code, code)
        return countries.setdefault(code, {"name": name, "slug": slug(name), "airlines": []})

    for fp in sorted(p for p in (ROOT / "liveries").glob("*.json") if "_prompts" not in p.name):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        code = str(data.get("region", ""))
        if "airlines" not in data or len(code) != 2 or code.upper() not in names:
            continue
        c = country(code.upper())
        for al in data["airlines"]:
            if "fleet" not in al:
                continue
            d = livery_dir(c["name"], al["name"])
            fleet = []
            for f in al["fleet"]:
                s = slug(f["type"])
                files = [f"{s}{suf}.webp" for suf in ("", "-2") if (d / f"{s}{suf}.webp").exists()]
                master = [f"{s}{suf}.webp" for suf in ("", "-2") if (ROOT / "planes" / f"{s}{suf}.webp").exists()]
                fleet.append({"type": f["type"], "label": f.get("label", ""), "count": f.get("count"),
                              "note": f.get("note", ""), "files": files, "master": master})
            c["airlines"].append({"key": al["key"], "icao": al.get("icao", []), "name": al["name"], "slug": slug(al["name"]),
                                  "kind": al.get("kind", ""), "base": al.get("base", ""), "fleet": fleet})

    # painted folders that no fleet list mentions
    if base.exists():
        for cdir in sorted(p for p in base.iterdir() if p.is_dir()):
            code = next((k for k, v in names.items() if slug(v) == cdir.name), None)
            if not code:
                continue
            c = country(code)
            known = {a["slug"] for a in c["airlines"]}
            for adir in sorted(p for p in cdir.iterdir() if p.is_dir() and p.name not in known):
                stems = sorted({re.sub(r"-2$", "", p.stem) for p in adir.glob("*.webp")})
                fleet = [{"type": s.upper(), "label": "", "count": None, "note": "",
                          "files": [f"{s}{suf}.webp" for suf in ("", "-2") if (adir / f"{s}{suf}.webp").exists()],
                          "master": [f"{s}{suf}.webp" for suf in ("", "-2") if (ROOT / "planes" / f"{s}{suf}.webp").exists()]} for s in stems]
                c["airlines"].append({"key": adir.name, "icao": [], "name": adir.name.replace("-", " ").title(), "slug": adir.name,
                                      "kind": "", "base": "", "fleet": fleet})

    cat = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"), "countries": countries}
    out = ROOT / "planes" / "catalogue.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    if {k: v for k, v in old.items() if k != "updated"} != {k: v for k, v in cat.items() if k != "updated"}:
        out.write_text(json.dumps(cat, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(f["files"]) for c in countries.values() for a in c["airlines"] for f in a["fleet"])
    t = sum(2 * len(a["fleet"]) for c in countries.values() for a in c["airlines"])
    print(f"catalogue: {sum(len(c['airlines']) for c in countries.values())} airlines in {len(countries)} countries, {n}/{t} livery images painted")


if __name__ == "__main__":
    build()
