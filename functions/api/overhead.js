// Cloudflare Pages Function: GET /api/overhead  ->  aircraft near home right now.
import { overhead } from "../../lib/adsb.js";
export async function onRequestGet({ env, waitUntil }) {
  return overhead(env, { waitUntil });
}
