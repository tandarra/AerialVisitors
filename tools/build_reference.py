#!/usr/bin/env python3
"""
Build the reference lists the rest of the project runs on (the planes' answer to eBird's taxonomy).

Downloads (all from GitHub, no keys needed):
  * wiedehopf/tar1090-db   aircraft.csv.gz            every known airframe: hex, registration, ICAO type, flags
                           db/icao_aircraft_types2.js ICAO Doc 8643 type designators -> name, description, wake class
                           db/operators.js            ICAO airline designators -> name, country, radio callsign
  * wiedehopf/tar1090      html/flags.js              ICAO 24-bit address blocks -> country of registration

Writes:
  planes/types.json       {"A20N": ["AIRBUS A-320neo", "L2J", "M"], ...}           (the "species list")
  planes/operators.json   {"ANZ": ["Air New Zealand", "New Zealand", "NEW ZEALAND"], ...}  (liveries)
  planes/world.json       every type + every country's register, as type indexes with airframe counts
                          (powers atlas.html: map shading, search, checklists)

Run:  python tools/build_reference.py           (about 10 MB download, a few seconds to process)
The daily GitHub Action runs it, so the lists stay current.
"""
import csv, datetime, gzip, io, json, re, sys, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "planes"
RAW = "https://raw.githubusercontent.com"
SRC = {
    "aircraft": f"{RAW}/wiedehopf/tar1090-db/csv/aircraft.csv.gz",
    "types": f"{RAW}/wiedehopf/tar1090-db/master/db/icao_aircraft_types2.js",
    "operators": f"{RAW}/wiedehopf/tar1090-db/master/db/operators.js",
    "flags": f"{RAW}/wiedehopf/tar1090/master/html/flags.js",
}

# ISO 3166-1 alpha-2 -> numeric (map shape ids in world-110m.json)
ISO_NUM = {"AF":"004","AL":"008","DZ":"012","AS":"016","AD":"020","AO":"024","AI":"660","AQ":"010","AG":"028","AR":"032","AM":"051","AW":"533","AU":"036","AT":"040","AZ":"031","BS":"044","BH":"048","BD":"050","BB":"052","BY":"112","BE":"056","BZ":"084","BJ":"204","BM":"060","BT":"064","BO":"068","BA":"070","BW":"072","BV":"074","BR":"076","IO":"086","BN":"096","BG":"100","BF":"854","BI":"108","KH":"116","CM":"120","CA":"124","CV":"132","KY":"136","CF":"140","TD":"148","CL":"152","CN":"156","CX":"162","CC":"166","CO":"170","KM":"174","CG":"178","CD":"180","CK":"184","CR":"188","CI":"384","HR":"191","CU":"192","CY":"196","CZ":"203","DK":"208","DJ":"262","DM":"212","DO":"214","EC":"218","EG":"818","SV":"222","GQ":"226","ER":"232","EE":"233","ET":"231","FK":"238","FO":"234","FJ":"242","FI":"246","FR":"250","GF":"254","PF":"258","TF":"260","GA":"266","GM":"270","GE":"268","DE":"276","GH":"288","GI":"292","GR":"300","GL":"304","GD":"308","GP":"312","GU":"316","GT":"320","GN":"324","GW":"624","GY":"328","HT":"332","HM":"334","VA":"336","HN":"340","HK":"344","HU":"348","IS":"352","IN":"356","ID":"360","IR":"364","IQ":"368","IE":"372","IL":"376","IT":"380","JM":"388","JP":"392","JO":"400","KZ":"398","KE":"404","KI":"296","KP":"408","KR":"410","KW":"414","KG":"417","LA":"418","LV":"428","LB":"422","LS":"426","LR":"430","LY":"434","LI":"438","LT":"440","LU":"442","MO":"446","MG":"450","MW":"454","MY":"458","MV":"462","ML":"466","MT":"470","MH":"584","MQ":"474","MR":"478","MU":"480","YT":"175","MX":"484","FM":"583","MD":"498","MC":"492","MN":"496","MS":"500","MA":"504","MZ":"508","MM":"104","NA":"516","NR":"520","NP":"524","NL":"528","NC":"540","NZ":"554","NI":"558","NE":"562","NG":"566","NU":"570","NF":"574","MP":"580","MK":"807","NO":"578","OM":"512","PK":"586","PW":"585","PS":"275","PA":"591","PG":"598","PY":"600","PE":"604","PH":"608","PN":"612","PL":"616","PT":"620","PR":"630","QA":"634","RE":"638","RO":"642","RU":"643","RW":"646","SH":"654","KN":"659","LC":"662","PM":"666","VC":"670","WS":"882","SM":"674","ST":"678","SA":"682","SN":"686","SC":"690","SL":"694","SG":"702","SK":"703","SI":"705","SB":"090","SO":"706","ZA":"710","GS":"239","ES":"724","LK":"144","SD":"729","SR":"740","SJ":"744","SZ":"748","SE":"752","CH":"756","SY":"760","TW":"158","TJ":"762","TZ":"834","TH":"764","TL":"626","TG":"768","TK":"772","TO":"776","TT":"780","TN":"788","TR":"792","TM":"795","TC":"796","TV":"798","UG":"800","UA":"804","AE":"784","GB":"826","US":"840","UM":"581","UY":"858","UZ":"860","VU":"548","VE":"862","VN":"704","VG":"092","VI":"850","WF":"876","EH":"732","YE":"887","ZM":"894","ZW":"716","AX":"248","BQ":"535","CW":"531","GG":"831","IM":"833","JE":"832","ME":"499","BL":"652","MF":"663","RS":"688","SX":"534","SS":"728","XK":"983"}


def fetch(url):
    print(f"  downloading {url.rsplit('/', 3)[-3]}/{url.rsplit('/', 1)[-1]}")
    req = urllib.request.Request(url, headers={"User-Agent": "aerialvisitors/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def maybe_gunzip(b):
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def load_ranges(js):
    """[(start, end, 'NZ', 'New Zealand'), ...] from tar1090's flags.js, smallest blocks first."""
    out = []
    for m in re.finditer(r"start:\s*0x([0-9A-Fa-f]+),\s*end:\s*0x([0-9A-Fa-f]+),\s*country:\s*\"([^\"]+)\",\s*"
                         r"country_code:\s*\"([a-z]{2})\"", js):
        out.append((int(m[1], 16), int(m[2], 16), m[4].upper(), m[3]))
    out.sort(key=lambda r: r[1] - r[0])     # a few blocks nest inside bigger ones; the specific one wins
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Fetching reference data")
    types_raw = json.loads(maybe_gunzip(fetch(SRC["types"])))
    ops_raw = json.loads(maybe_gunzip(fetch(SRC["operators"])))
    ranges = load_ranges(fetch(SRC["flags"]).decode("utf-8"))
    aircraft = maybe_gunzip(fetch(SRC["aircraft"])).decode("utf-8", "replace")
    if len(types_raw) < 1000 or len(ranges) < 150:
        sys.exit("Reference data looks wrong (too few types or country ranges); not overwriting anything.")

    # ICAO has placeholder codes with no name. Name the real aircraft kinds, drop ground vehicles and "unknown".
    rename = {"BALL": "Hot-air balloon", "GYRO": "Autogyro", "ULAC": "Ultralight aircraft", "DRON": "Drone",
              "PARA": "Powered parachute"}
    drop = {"EMER", "FFLO", "GND", "SERV", "SHIP", "TWR", "UHEL", "VFHC", "ZZZZ"}
    types = {}
    for k, v in sorted(types_raw.items()):
        if not (re.fullmatch(r"[A-Z0-9]{2,4}", k) and isinstance(v, list) and len(v) >= 3) or k in drop:
            continue
        types[k] = [rename.get(k, v[0]), v[1], v[2]]
    operators = {k: [v.get("n", ""), v.get("c", ""), v.get("r", "")] for k, v in sorted(ops_raw.items())
                 if re.fullmatch(r"[A-Z]{3}", k)}

    # airframes per country register, by type
    starts = [(s, e, cc, name) for s, e, cc, name in ranges]
    names = {cc: name for _, _, cc, name in ranges}
    def country(hexid):
        for s, e, cc, _ in starts:
            if s <= hexid <= e:
                return cc
        return None
    reg = defaultdict(Counter)
    total = Counter()
    for row in csv.reader(io.StringIO(aircraft), delimiter=";"):
        if len(row) < 3 or row[2] not in types:
            continue
        try:
            cc = country(int(row[0], 16))
        except ValueError:
            continue
        total[row[2]] += 1
        if cc:
            reg[cc][row[2]] += 1

    codes = list(types)
    idx = {c: i for i, c in enumerate(codes)}
    countries = []
    for cc in sorted(reg, key=lambda c: names.get(c, c)):
        ranked = reg[cc].most_common()
        countries.append({"code": cc, "name": names.get(cc, cc), "iso": ISO_NUM.get(cc, ""),
                          "sp": [idx[t] for t, _ in ranked], "n": [n for _, n in ranked],
                          "airframes": sum(reg[cc].values())})
    world = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
             "source": "ICAO Doc 8643 types and the Mictronics airframe database via wiedehopf/tar1090-db; "
                       "country of registration from ICAO 24-bit address blocks",
             "types": [[c, *types[c], total[c]] for c in codes], "countries": countries}

    # Only touch a file when its data really changed (the timestamp alone isn't a change), so the daily
    # GitHub Action commits nothing on quiet days.
    def save(name, data, **kw):
        path = OUT / name
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                same = {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in data.items() if k != "updated"} \
                    if isinstance(old, dict) and "updated" in old else old == data
                if same:
                    return False
            except ValueError:
                pass
        path.write_text(json.dumps(data, ensure_ascii=False, **kw), encoding="utf-8")
        return True
    changed = [n for n, d, kw in (("types.json", types, {"indent": 0}), ("operators.json", operators, {"indent": 0}),
                                  ("world.json", world, {"separators": (",", ":")})) if save(n, d, **kw)]
    nz = next((c for c in countries if c["code"] == "NZ"), None)
    print(f"\n{len(types)} aircraft types, {len(operators)} operators, {len(countries)} country registers")
    if nz:
        print(f"New Zealand register: {nz['airframes']} airframes of {len(nz['sp'])} types")
    print("Changed: " + ", ".join(changed) if changed else "No changes since last run.")


if __name__ == "__main__":
    main()
