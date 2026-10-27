#!/usr/bin/env python3
"""
Build AIRLINES.md: every airline catalogued so far, by country and by alliance, with livery progress.
Reads planes/catalogue.json (tools/catalogue.py) and liveries/alliances.json. The pipeline runs this for you.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://tandarra.github.io/AerialVisitors"


def bar(done, total, width=40):
    n = round(width * done / total) if total else 0
    return "█" * n + "░" * (width - n)


def build():
    cat = json.loads((ROOT / "planes" / "catalogue.json").read_text(encoding="utf-8"))["countries"]
    ally = json.loads((ROOT / "liveries" / "alliances.json").read_text(encoding="utf-8"))
    by = {}
    for a in ally["alliances"]:
        for m in a["members"] + a["affiliates"]:
            by.setdefault(m[0], []).append(a["short"])

    def score(al):
        return sum(len(f["files"]) for f in al["fleet"]), 2 * len(al["fleet"])

    def icaos(al):
        return al.get("icao") or ([al["key"].upper()] if len(al["key"]) == 3 else [])

    airlines = [(cc, c, al) for cc, c in cat.items() for al in c["airlines"]]
    done = sum(score(al)[0] for _, _, al in airlines)
    total = sum(score(al)[1] for _, _, al in airlines)
    masters = {f["type"] for _, _, al in airlines for f in al["fleet"] if f["master"]}
    types = {f["type"] for _, _, al in airlines for f in al["fleet"]}
    L = ["# Airlines by country", "",
         f"## ✈️ World: {done / total * 100:.1f}% of catalogued liveries painted" if total else "## ✈️ World", "",
         f"`{bar(done, total)}` **{done:,} / {total:,}** livery images (side profile + from below)", "",
         f"**{len(airlines)} airlines** in **{len(cat)} countries** · master airframes for {len(masters)} of {len(types)} aircraft types flown by them", "",
         "Each airline's fleet is listed once, then every type it flies is painted in its real livery on top of a master airframe "
         "(one plain, anatomy-checked airframe per aircraft type). Until a livery exists the atlas shows the master. "
         "Images live in `planes/liveries/<country>/<airline>/<type>.webp`; masters in `planes/<type>.webp`. "
         "Alliance membership is in `liveries/alliances.json`.", "",
         "## By country", "", "| Country | Livery images | Airlines |", "|---|---|---|"]
    for cc, c in sorted(cat.items(), key=lambda kv: kv[1]["name"]):
        d = sum(score(al)[0] for al in c["airlines"]); t = sum(score(al)[1] for al in c["airlines"])
        rows = []
        for al in c["airlines"]:
            a, b = score(al)
            tags = sorted({x for i in icaos(al) for x in by.get(i, [])})
            rows.append(f"{al['name']}{' (' + ', '.join(tags) + ')' if tags else ''}: {a}/{b}")
        L.append(f"| [{c['name']}]({SITE}/atlas.html#{cc}) | {d} / {t} ({d / t * 100 if t else 0:.0f}%) | " + "<br>".join(rows) + " |")
    L += ["", "## By alliance", "",
          "Members with a fleet list in this repo are marked; the rest are next. ", "",
          "| Alliance | Members | With a fleet list | Fully painted |", "|---|---|---|---|"]
    listed = {i: al for _, _, al in airlines for i in icaos(al)}
    for a in ally["alliances"]:
        codes = [m[0] for m in a["members"]]
        have = [c for c in codes if c in listed]
        full = [c for c in have if score(listed[c])[1] and score(listed[c])[0] == score(listed[c])[1]]
        L.append(f"| {a['name']} | {len(codes)} | {len(have)} | {len(full)} |")
    L += ["", "Membership checked " + ally["checked"] + ". " + " ".join(ally.get("notes", [])), ""]
    (ROOT / "AIRLINES.md").write_text("\n".join(L), encoding="utf-8")
    print(f"AIRLINES.md: {len(airlines)} airlines, {done}/{total} livery images")


if __name__ == "__main__":
    build()
