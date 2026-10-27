#!/usr/bin/env python3
"""
Log what flies overhead: the plane twin of BirdNET-Go's detection log.

Polls live ADS-B for aircraft near home and keeps a running life list in planes/sightings.json:
which ICAO types you've seen, how many different airframes of each, and which airlines flew them.
`plane_illustrations.py --sightings` then paints exactly the types you've actually seen.

Data sources (pick one):
  * adsb.lol public API (default, free, no key):   python tools/log_sightings.py --home -37.25,175.02
  * your own receiver (readsb / dump1090 / tar1090): python tools/log_sightings.py --url http://pi.local/tar1090/data/aircraft.json
  * a saved aircraft.json file:                    python tools/log_sightings.py --file aircraft.json

Run once from cron, or keep it going:  python tools/log_sightings.py --loop 30
Home comes from --home, or HOME_LATLNG=lat,lng in plane_keys.txt / the environment.

Writes two files:
  planes/sightings.json  the full log (airframes, your home position). Private: it is in .gitignore.
  planes/seen.json       the shareable summary the website shows: types and counts only, no airframes, no position.
"""
import argparse, datetime, json, os, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "planes" / "sightings.json"
SEEN = ROOT / "planes" / "seen.json"
DEFAULT_HOME = (-37.25, 175.02)       # Pokeno, NZ (same default as the bird scripts)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aerialvisitors/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def home_from_env():
    for k in ("plane_keys.txt", "bird_keys.txt"):
        f = ROOT / k
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                a, sep, b = line.partition("=")
                if sep and a.strip() in ("HOME", "HOME_LATLNG") and b.strip():
                    os.environ.setdefault("HOME_LATLNG", b.strip())
    v = os.environ.get("HOME_LATLNG")
    return tuple(float(x) for x in v.split(",")) if v else DEFAULT_HOME


def operator_from_callsign(callsign, operators):
    m = re.match(r"([A-Z]{3})\d", (callsign or "").strip().upper())
    return m.group(1) if m and m.group(1) in operators and m.group(1) != "ZZZ" else None


def fetch_aircraft(a, home):
    if a.file:
        data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    elif a.url:
        data = get_json(a.url)
    else:
        data = get_json(f"https://api.adsb.lol/v2/point/{home[0]}/{home[1]}/{a.radius}")
    return data.get("ac") or data.get("aircraft") or []


def record(db, ac, operators, types, today):
    """Merge one poll into the life list. Returns the number of NEW airframes."""
    new = 0
    for p in ac:
        code, hexid = (p.get("t") or "").upper(), (p.get("hex") or "").lower()
        if not code or not hexid or p.get("alt_baro") == "ground":
            continue
        if types and code not in types:                     # unknown / placeholder type codes
            continue
        opr = operator_from_callsign(p.get("flight"), operators)
        t = db["types"].setdefault(code, {"n": 0, "first": today, "last": today, "operators": {}})
        frame = db["airframes"].get(hexid)
        if frame is None:
            db["airframes"][hexid] = {"t": code, "r": p.get("r") or "", "o": opr or "", "first": today, "last": today}
            t["n"] += 1
            if opr:
                t["operators"][opr] = t["operators"].get(opr, 0) + 1
            new += 1
        else:
            frame["last"] = today
            if opr and not frame["o"]:
                frame["o"] = opr
                t["operators"][opr] = t["operators"].get(opr, 0) + 1
        t["last"] = today
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", help="lat,lng of your station")
    ap.add_argument("--radius", type=int, default=25, help="nautical miles around home (adsb.lol, max 250)")
    ap.add_argument("--url", help="your receiver's aircraft.json URL instead of adsb.lol")
    ap.add_argument("--file", help="read a saved aircraft.json instead")
    ap.add_argument("--loop", type=int, metavar="SECONDS", help="keep polling every N seconds")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    home = tuple(float(x) for x in a.home.split(",")) if a.home else home_from_env()
    out = Path(a.out)

    types_p, ops_p = ROOT / "planes" / "types.json", ROOT / "planes" / "operators.json"
    types = json.loads(types_p.read_text(encoding="utf-8")) if types_p.exists() else {}
    operators = json.loads(ops_p.read_text(encoding="utf-8")) if ops_p.exists() else {}
    if not types:
        print("(planes/types.json not found: run tools/build_reference.py; logging every type code unchecked)")

    while True:
        db = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"types": {}, "airframes": {}}
        today = datetime.date.today().isoformat()
        try:
            ac = fetch_aircraft(a, home)
        except Exception as e:
            if not a.loop:
                sys.exit(f"Couldn't read aircraft data: {e}")
            print(f"  fetch failed ({e}); trying again next round")
            time.sleep(a.loop)
            continue
        new = record(db, ac, operators, types, today)
        db["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        db["home"] = list(home)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if out == OUT:
            SEEN.write_text(json.dumps({"updated": db["updated"], "types": db["types"]}, ensure_ascii=False,
                                       separators=(",", ":")), encoding="utf-8")
        print(f"{len(ac)} aircraft in range, {new} new airframe(s); life list: "
              f"{len(db['types'])} types, {len(db['airframes'])} airframes")
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
