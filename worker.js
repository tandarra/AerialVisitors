// Cloudflare Worker entry (Workers + static assets). Same route as the Pages Function.
import { overhead } from "./lib/adsb.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/api/overhead") return overhead(env, ctx);
    return env.ASSETS.fetch(request);
  },
};
