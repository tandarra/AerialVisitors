// Live aircraft near home from the free adsb.lol API, trimmed to what the page needs.
// Used by both the Pages Function (functions/api/overhead.js) and the Worker (worker.js).
export async function overhead(env, ctx) {
  const lat = Number(env.HOME_LAT), lng = Number(env.HOME_LNG);
  const r = Math.min(Math.max(Number(env.RADIUS_NM) || 25, 1), 250);
  const api = (env.ADSB_API || "https://api.adsb.lol").replace(/\/$/, "");
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return json({ error: "HOME_LAT / HOME_LNG not set" }, 500);
  const res = await fetch(`${api}/v2/point/${lat}/${lng}/${r}`, {
    headers: { "User-Agent": "aerialvisitors/1.0" },
    cf: { cacheTtl: 8, cacheEverything: true },
  });
  if (!res.ok) return json({ error: `ADS-B source answered ${res.status}` }, 502);
  const data = await res.json();
  const ac = (data.ac || [])
    .filter((p) => p.t && p.hex && p.alt_baro !== "ground")
    .map((p) => ({
      hex: p.hex, type: String(p.t).toUpperCase(), reg: p.r || "", call: (p.flight || "").trim(),
      alt: typeof p.alt_baro === "number" ? p.alt_baro : null, gs: p.gs ?? null, track: p.track ?? null,
      dist: p.dst ?? null, dir: p.dir ?? null,
    }))
    .sort((a, b) => (a.dist ?? 1e9) - (b.dist ?? 1e9));
  return json({ updated: new Date().toISOString(), home: [lat, lng], radius_nm: r, aircraft: ac });
}

export function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=8" },
  });
}
