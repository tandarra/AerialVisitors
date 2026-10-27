#!/usr/bin/env python3
"""
Aerial Visitors, one command: paint -> cut out -> catalogue -> git push.

  stage 1  airframes  one plain, anatomy-checked airframe per physical type, 2 poses   (liveries/nz_airframes.json)
  stage 2  liveries   every airline's real livery on each type it flies, 2 poses, each repainted FROM the approved
                      airframe image so the shape never drifts                          (liveries/nz.json)
  then     rembg cut-outs, planes/catalogue.json + painted.json, git commit and push (atlas updates)

Originals (PNG) are saved to  <out>/_airframes/<type>.png  and  <out>/<Country>/<Airline>/<type>.png
(default out: ~/Downloads/AerialVisitors). Cut-outs go into the repo:
  planes/<type>.webp                                   (generic airframes, the species checklist)
  planes/liveries/<country>/<airline>/<type>.webp      (liveries, e.g. new-zealand/air-new-zealand/a320.webp)
Side profile = <type>.*, from below = <type>-2.*

Safe to stop and re-run: anything already painted is skipped. Failed images are listed at the end; just run again.

  python tools/aerial_run.py                       # everything for New Zealand
  python tools/aerial_run.py --stage airframes     # review the plain airframes first
  python tools/aerial_run.py --list-only           # what would be painted, and the cost
  python tools/aerial_run.py --no-push             # do not touch GitHub
  python tools/aerial_run.py --fake                # test the plumbing with placeholder images (no API, no cost)
"""
import argparse, io, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import plane_illustrations as pi
import build_airframe_prompts as bap
import build_livery_prompts as blp
import catalogue

ALIAS = {"AT75": "AT76"}                        # near-identical exterior: reuse the approved airframe
POSES = {"side": "", "below": "-2"}


class Tee:
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8")
        self.o = sys.__stdout__

    def write(self, s):
        self.o.write(s); self.f.write(s); self.f.flush()

    def flush(self):
        self.o.flush()


def find_key():
    for k in ("plane_keys.txt", "bird_keys.txt"):
        f = ROOT / k
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                a, sep, v = line.partition("=")
                if sep and a.strip() == "GEMINI_API_KEY" and v.strip() and "paste-your" not in v:
                    os.environ.setdefault("GEMINI_API_KEY", v.strip().strip('"').strip("'"))
    return os.environ.get("GEMINI_API_KEY")


def fake_png(label, hue):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (512, 512), (240, 232, 214))
    d = ImageDraw.Draw(im)
    d.ellipse((60, 200, 450, 300), fill=(hue, 90, 160), outline=(20, 20, 20), width=4)
    d.text((80, 240), label, fill=(255, 255, 255))
    b = io.BytesIO(); im.save(b, "PNG")
    return b.getvalue()


def fake_remove(im):
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, _ = px[x, y]
            if abs(r - 240) < 14 and abs(g - 232) < 14 and abs(b - 214) < 14:
                px[x, y] = (0, 0, 0, 0)
    return im


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def sync(message, push):
    catalogue.build()
    pi.write_painted(ROOT / "planes")
    git("add", "planes", "liveries")
    if not git("status", "--porcelain").stdout.strip():
        return
    c = git("commit", "-m", message)
    if c.returncode:
        print("  git commit failed:", (c.stderr or c.stdout).strip()[:300]); return
    print(f"  committed: {message}")
    if not push:
        return
    git("pull", "--rebase", "--autostash")
    p = git("push")
    if p.returncode:
        print("  git push failed (your images are safe and committed locally). Fix the login, then run `git push` in the repo:\n   ",
              (p.stderr or p.stdout).strip()[:400])
    else:
        print("  pushed to GitHub")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", default="liveries/nz.json", help="airline fleet file (default liveries/nz.json)")
    ap.add_argument("--airframes", default="liveries/nz_airframes.json")
    ap.add_argument("--out", default=str(Path.home() / "Downloads" / "AerialVisitors"))
    ap.add_argument("--stage", choices=["all", "airframes", "liveries"], default="all")
    ap.add_argument("--model", default="gemini-nano-banana-2.1")
    ap.add_argument("--limit", type=int, help="stop after this many new images")
    ap.add_argument("--every", type=int, default=10, help="commit and push after this many new images (default 10)")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--fake", action="store_true", help="placeholder images, no API call (plumbing test)")
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    sys.stdout = Tee(out / "run.log")
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')}  Aerial Visitors run ===  output: {out}")

    fleet_path = ROOT / a.fleet
    fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    air = json.loads((ROOT / a.airframes).read_text(encoding="utf-8"))
    names = catalogue.country_names()
    country = names.get(fleet["region"], fleet["region"])
    types = pi.load_types()
    specs = {t["type"]: t for t in air["types"]}

    jobs = []          # (kind, label, png path, webp path, text, base png path or None)
    adir = out / "_airframes"
    for t in air["types"]:
        for pose, suf in POSES.items():
            s = pi.slug(t["type"])
            jobs.append(("airframe", f"{t['name']} ({pose})", adir / f"{s}{suf}.png", ROOT / "planes" / f"{s}{suf}.webp",
                         bap.prompt(t, pose), None))
    for al in fleet["airlines"]:
        ldir = catalogue.livery_dir(country, al["name"])
        for f in al.get("fleet", []):
            code, s = f["type"], pi.slug(f["type"])
            base = ALIAS.get(code, code)
            if base not in specs:
                sys.exit(f"{al['name']}: no base airframe for {code}")
            label = f.get("label") or types[code][0]
            for pose, suf in POSES.items():
                jobs.append(("livery", f"{al['name']}: {label} ({pose})", out / country / al["name"] / f"{s}{suf}.png",
                             ldir / f"{s}{suf}.webp", blp.prompt(code, label, al["name"], suf) + "\n\n" + blp.REPAINT_LINE,
                             adir / f"{pi.slug(base)}{suf}.png"))
    if a.stage != "all":
        jobs = [j for j in jobs if j[0] == ("airframe" if a.stage == "airframes" else "livery")]
    todo = [j for j in jobs if not j[2].exists()]
    print(f"{len(jobs)} images in this plan, {len(todo)} still to paint, about US${len(todo) * pi.COST_PER_IMAGE:.2f}")
    if a.list_only:
        for j in todo:
            print("  ", j[1])
        return

    gkey = None if a.fake else find_key()
    if not a.fake and not gkey:
        sys.exit("No Gemini key. Put  GEMINI_API_KEY=your-key  in plane_keys.txt next to plane_illustrations.py "
                 "(or set the GEMINI_API_KEY environment variable), then run again.")
    if a.fake:
        remover = fake_remove
    else:
        from rembg import remove, new_session
        session = new_session("u2net")
        remover = lambda im: remove(im, session=session)

    done, failed, since, k = 0, [], 0, 0
    # airframes first, so liveries always have their approved base
    for kind, label, png, webp, text, base in sorted(jobs, key=lambda j: j[0] != "airframe"):
        k += 1
        if not png.exists():
            if a.limit and done >= a.limit:
                continue
            if base is not None and not base.exists():
                print(f"  [{k}/{len(jobs)}] SKIP {label}: base airframe {base.name} is missing")
                failed.append(label); continue
            print(f"  [{k}/{len(jobs)}] painting {label}")
            try:
                if a.fake:
                    data = fake_png(label[:22], 40 + 7 * k)
                else:
                    parts = [pi.img_part(base)] if base else []
                    data = pi.gemini_image(gkey, a.model, text, parts)
            except pi.OutOfCredit:
                print("  Out of Gemini credit. Top up in AI Studio and run the same command again.")
                break
            if not data:
                print("    FAILED"); failed.append(label); continue
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(data)
            done += 1; since += 1
            time.sleep(0 if a.fake else 2)
        if png.exists() and not webp.exists():
            webp.parent.mkdir(parents=True, exist_ok=True)
            pi.cutout(png.read_bytes(), remover).save(webp, "WEBP", quality=88)
        if since >= a.every:
            sync(f"Add {since} illustrations ({country})", not a.no_push); since = 0
    # alias airframes (e.g. ATR 72-500 reuses the ATR 72-600) fill their own atlas slot
    for alias, src in ALIAS.items():
        for suf in POSES.values():
            s, d = ROOT / "planes" / f"{pi.slug(src)}{suf}.webp", ROOT / "planes" / f"{pi.slug(alias)}{suf}.webp"
            if s.exists() and not d.exists():
                shutil.copy(s, d)
    sync(f"Add illustrations ({country})", not a.no_push)
    print(f"\nPainted {done} new image(s)." + (f" {len(failed)} missing: run the same command again to retry:\n   " + "\n   ".join(failed) if failed else " Nothing missing."))
    print(f"Originals: {out}\nLog: {out / 'run.log'}")


if __name__ == "__main__":
    main()
