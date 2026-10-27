#!/usr/bin/env python3
"""
Build the prompt pack and checklist for painting airline liveries by hand in the Gemini app.

Reads a fleet file (default liveries/nz.json: each airline, the types it flies) and writes:
  liveries/NZ_prompts.json    every prompt (side profile + from below) for every airline + type, plus file names
  liveries/NZ_checklist.md    a checklist that ticks itself: a box is checked when planes/raw/<file>.png exists
  liveries/NZ_prompts.md      the same prompts as plain text, grouped by airline, to copy from

The prompts are exactly the ones plane_illustrations.py sends to Gemini (same house style), asking for the
airline's real livery and logo.

Run:   python tools/build_livery_prompts.py                       # liveries/nz.json
       python tools/build_livery_prompts.py liveries/other.json   # another country or list
Re-run after painting to refresh the ticks.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import plane_illustrations as pi            # same prompt text as the generator

REPAINT_LINE = ("Image 1 is the APPROVED AIRFRAME for this aircraft. Keep its shape, proportions, number of wings, engines and "
                "tail surfaces, pose, framing and woodblock line style EXACTLY as drawn. Change ONLY the paint scheme. Do NOT carry "
                "over the brown or ochre washes from image 1 onto the belly, engines or tail cone: repaint them in the airline's real "
                "colours. The airline name and logo go only where the real aircraft carries them (fuselage sides and tail), never as "
                "title text on top of the fuselage or wings. Produce ONE image of ONE aircraft only, on the same cream ground: no "
                "other views, no other aircraft, no sheet layout.")
STYLE_REF_LINE = ("Image 1 is the STYLE reference: match its style, line weight, palette, level of detail and cream "
                  "ground exactly, but do NOT copy its aircraft type or livery.")


def prompt(code, label, airline, suffix):
    text = pi.make_prompt(code, label, pi.POSES[suffix], pi.LIVERY_REAL.format(opr=airline))
    return text + "\n\nProduce ONE new image of ONE aircraft on its own 1:1 canvas."


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "liveries" / "nz.json"
    src = src if src.is_absolute() else ROOT / src
    data = json.loads(src.read_text(encoding="utf-8"))
    region = data.get("region", src.stem.upper())
    raw = ROOT / "planes" / "raw"
    types = pi.load_types()

    out_airlines, done_n, total_n = [], 0, 0
    for al in data["airlines"]:
        entry = {k: al[k] for k in ("key", "name", "kind", "base", "source") if k in al}
        for group in ("fleet", "pending"):
            rows = []
            for f in al.get(group, []):
                if f["type"] not in types:
                    sys.exit(f"{al['name']}: unknown ICAO type {f['type']}")
                base = f"{pi.slug(f['type'])}-{pi.slug(al['key'])}"
                label = f.get("label") or types[f["type"]][0]
                files = {"side": f"{base}.png", "below": f"{base}-2.png"}
                have = {k: (raw / v).exists() for k, v in files.items()}
                if group == "fleet":
                    done_n += sum(have.values()); total_n += 2
                rows.append({"type": f["type"], "label": label, "count": f.get("count"), "note": f.get("note", ""),
                             "slug": base, "files": files, "have": have,
                             "prompts": {"side": prompt(f["type"], label, al["name"], ""),
                                         "below": prompt(f["type"], label, al["name"], "-2")}})
            if rows:
                entry[group] = rows
        out_airlines.append(entry)

    pack = {"region": region, "checked": data.get("checked", ""), "about": data.get("about", ""),
            "style_ref_line": STYLE_REF_LINE, "repaint_line": REPAINT_LINE, "not_included": data.get("not_included", ""), "airlines": out_airlines}
    out = ROOT / "liveries"
    out.mkdir(exist_ok=True)
    (out / f"{region}_prompts.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    tpl = ROOT / "tools" / "livery_checklist_template.html"
    if tpl.exists():        # interactive checklist page: the pack embedded as JSON
        blob = json.dumps(pack, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
        (out / f"{region}_checklist.html").write_text(tpl.read_text(encoding="utf-8").replace("__TITLE__", f"{region} Livery Checklist").replace("__STORE__", "nz-livery-done").replace("__HOW__", "Copy a prompt, paste it into Gemini (attach the approved base airframe and switch on repaint mode), save the image under the file name shown in <code>planes/raw/</code>, tick the box. When you have a batch, run <code>python plane_illustrations.py --cutout-only</code>.").replace("__DATA__", blob),
                                                      encoding="utf-8")

    cl = [f"# {region} airline liveries: checklist", "",
          f"{done_n} of {total_n} images found in `planes/raw/`. Ticks refresh when you run "
          f"`python tools/build_livery_prompts.py`. Save each image under the file name shown, then run "
          f"`python plane_illustrations.py --cutout-only`.", ""]
    md = [f"# {region} airline liveries: prompts", "",
          f"Paste into the Gemini app, one image per prompt. For a consistent look, attach your best finished image "
          f"and add this line to the prompt:", "", f"> {STYLE_REF_LINE}", ""]
    for al in out_airlines:
        cl += [f"## {al['name']}", f"_{al.get('kind', '')}, based {al.get('base', '')}_", ""]
        md += [f"## {al['name']}", ""]
        for f in al.get("fleet", []):
            n = f"{f['count']} x " if f["count"] else ""
            cl += [f"- [{'x' if f['have']['side'] else ' '}] `{f['files']['side']}` {n}{f['label']}, side profile",
                   f"- [{'x' if f['have']['below'] else ' '}] `{f['files']['below']}` {n}{f['label']}, from below"]
            md += [f"### {f['label']} ({f['type']})", f"_{f['note']}_" if f["note"] else "", "",
                   f"**Side profile**, save as `{f['files']['side']}`", "", "```", f["prompts"]["side"], "```", "",
                   f"**From below**, save as `{f['files']['below']}`", "", "```", f["prompts"]["below"], "```", ""]
        for f in al.get("pending", []):
            cl += [f"- (on order, not flying yet) {f['label']}: {f['note']}"]
        cl.append("")
    if pack["not_included"]:
        cl += ["## Not included", "", pack["not_included"], ""]
    (out / f"{region}_checklist.md").write_text("\n".join(cl), encoding="utf-8")
    (out / f"{region}_prompts.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(out_airlines)} airlines, {total_n // 2} airline+type combinations, {total_n} images; {done_n} done.")
    print(f"Wrote liveries/{region}_prompts.json, {region}_checklist.md, {region}_prompts.md")


if __name__ == "__main__":
    main()
