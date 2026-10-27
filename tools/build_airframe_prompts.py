#!/usr/bin/env python3
"""
Build the base-airframe prompt pack: ONE plain, anatomically checked illustration per physical aircraft type.

Approve these first, then repaint each into airline liveries (tools/build_livery_prompts.py) using the approved image
as the reference, so the geometry never drifts.

Reads liveries/nz_airframes.json and writes liveries/NZ-airframes_prompts.json / .md / _checklist.html.
Files are named like the atlas expects (planes/raw/<type>.png side profile, <type>-2.png from below), so an approved
airframe also fills the plain-type slot in the atlas.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import plane_illustrations as pi

STYLE = ("Edo-period Japanese woodblock print, painted as carefully as a kacho-e bird. VERY FEW MARKS: the aircraft is 2-4 flat "
         "colour zones with sharp boundaries, no rivets, no panel lines, no individual windows. Confident sumi-e ink linework, "
         "soft watercolour washes. Earthy palette: burnt umber, ochre, indigo, vermillion, muted greens. "
         "Plain neutral livery: bare white and grey with one indigo stripe. No airline colours. "
         "The aircraft sits on a CONSISTENT WARM CREAM ground (aged mulberry paper), filling the frame. "
         "NO sky, NO clouds, NO runway, NO scenery. NO text, NO lettering, NO logos, NO registration marks.")

POSE = {
    "side": "Pure SIDE PROFILE, level flight, nose pointing to the RIGHT of the frame, true side-on (no perspective), "
            "the whole aircraft from nose to tail fully inside the frame.",
    "below": "Seen from BELOW and AHEAD at a three-quarter angle, climbing away over the viewer, banking slightly so "
             "one wing is lower than the other, as you would see it passing overhead. The whole aircraft is inside the frame.",
}


def gear_line(a, pose):
    if a["gear"] == "fixed":
        return "Landing gear is FIXED (it never retracts): draw it, with the correct wheel layout, in both views."
    return "Landing gear is RETRACTED: no wheels or legs visible, clean belly and nacelles."


def prompt(a, pose):
    anat = "\n".join(f"- {x}" for x in a["anatomy"])
    return (f"Generate ONE image of ONE {a['name']} (ICAO type {a['type']}). {POSE[pose]}\n\n"
            f"STYLE: {STYLE}\n\n"
            f"ANATOMY: this must be an exact, recognisable {a['name']} with correct proportions. Anything not listed "
            f"below must match the real aircraft.\n{anat}\n- {gear_line(a, pose)}\n\n"
            f"HARD RULES: exactly ONE aircraft; exactly ONE fuselage; exactly TWO wings (a left and a right); exactly ONE "
            f"vertical tail fin unless stated otherwise; the engine and propeller counts above are exact, not approximate; no "
            f"duplicated or fused parts, no extra engines, no extra wings or tail surfaces, no biplane wings, no floating or "
            f"detached parts. Wings, tail and engines must be attached where the real aircraft has them.\n\n"
            f"BEFORE YOU FINISH, check silently: count the engines, propeller blades, wings, fins and landing-gear legs "
            f"against the list above, check the length-to-wingspan proportion, and fix any error. Output only the final image "
            f"on a 1:1 canvas.")


def main():
    src = ROOT / "liveries" / "nz_airframes.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    types = pi.load_types()
    fleet, md = [], [f"# {data['region']}: base airframe prompts", "", data["about"], "",
                     "Paste into the Gemini app, one image per prompt. Check the result against the **Check** line before approving.", ""]
    for a in data["types"]:
        if a["type"] not in types:
            sys.exit(f"unknown ICAO type {a['type']}")
        base = pi.slug(a["type"])
        files = {"side": f"{base}.png", "below": f"{base}-2.png"}
        prompts = {k: prompt(a, k) for k in files}
        fleet.append({"type": a["type"], "label": a["name"], "count": None,
                      "note": f"CHECK: {a['check']} · used by {a['airlines']}",
                      "slug": base, "files": files, "have": {k: (ROOT / "planes" / "raw" / v).exists() for k, v in files.items()},
                      "prompts": prompts})
        md += [f"## {a['name']} ({a['type']})", f"**Check:** {a['check']}  ", f"Used by: {a['airlines']}", "",
               f"**Side profile**, save as `{files['side']}`", "", "```", prompts["side"], "```", "",
               f"**From below**, save as `{files['below']}`", "", "```", prompts["below"], "```", ""]
    pack = {"region": data["region"], "airlines": [{"key": "base", "name": "Base airframes", "kind": "One plain airframe per physical type",
                                                      "base": "", "fleet": fleet}],
            "style_ref_line": "Image 1 is the STYLE reference: match its style, line weight, palette and cream ground, but do NOT copy its aircraft type.",
            "not_included": data.get("not_included", "")}
    out = ROOT / "liveries"
    (out / f"{data['region']}_prompts.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{data['region']}_prompts.md").write_text("\n".join(md), encoding="utf-8")
    tpl = (ROOT / "tools" / "livery_checklist_template.html").read_text(encoding="utf-8")
    blob = json.dumps(pack, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    html = (tpl.replace("__TITLE__", "NZ Airframe Checklist").replace("__STORE__", "nz-airframe-done")
               .replace("__HOW__", "Approve each plain airframe first: paste the prompt into Gemini, check the image against the CHECK line "
                        "(engines, blades, wings, tail, proportions), regenerate if wrong, then save it under the file name shown in "
                        "<code>planes/raw/</code> and tick it. Then paint liveries from the approved image.")
               .replace("__DATA__", blob))
    (out / f"{data['region']}_checklist.html").write_text(html, encoding="utf-8")
    n = len(fleet)
    print(f"{n} airframes, {n * 2} images. Wrote liveries/{data['region']}_prompts.json / .md / _checklist.html")


if __name__ == "__main__":
    main()
