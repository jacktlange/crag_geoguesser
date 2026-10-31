/**
 * Crag Guesser result relay (Cloudflare Worker).
 *
 * The game page can't hold your Discord webhook URL (anyone could read it from
 * the page source and spam the channel), so it sends a player's result here and
 * this Worker posts it to Discord.
 *
 * Settings (Worker -> Settings -> Variables and Secrets):
 *   DISCORD_WEBHOOK_URL   secret, required
 *   ALLOWED_ORIGIN        e.g. https://yourname.github.io   (no path, no trailing slash)
 *   POSTS                 optional KV namespace binding; turns on "one post per name per
 *                         day" and a per-IP daily cap
 *
 * Results are self-reported: the page sends scores and this Worker trusts them
 * after basic sanity checks. Names are whatever the player types.
 */

const MAX_POINTS = 5000;
const MAX_ROUNDS = 10;
const PER_IP_DAILY_LIMIT = 8;
const SQUARES = [[4000, "\uD83D\uDFE9"], [2500, "\uD83D\uDFE8"], [1000, "\uD83D\uDFE7"], [0, "\uD83D\uDFE5"]];

export function cleanName(raw) {
  if (typeof raw !== "string") return "";
  return raw
    .replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202f\u2060\ufeff]/g, "")  // control and invisible characters
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 32)
    .replace(/([\\*_~`|\[\]()>#:@<])/g, "\\$1");   // show markdown, mentions and emoji codes as plain text
}

export function validate(body, now = new Date()) {
  if (!body || typeof body !== "object") return { error: "Bad request" };
  const name = cleanName(body.name);
  if (!name) return { error: "Please enter a name" };

  const date = body.date;
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(date + "T00:00:00Z"))) {
    return { error: "Bad date" };
  }
  const days = (Date.parse(date + "T00:00:00Z") - Date.parse(now.toISOString().slice(0, 10) + "T00:00:00Z")) / 86400000;
  if (days < -3 || days > 1) return { error: "That puzzle is too old to post" };

  const number = body.number;
  if (!Number.isInteger(number) || number < 1 || number > 100000) return { error: "Bad puzzle number" };

  const rounds = body.results;
  if (!Array.isArray(rounds) || rounds.length < 1 || rounds.length > MAX_ROUNDS) return { error: "Bad results" };
  const results = [];
  for (const r of rounds) {
    if (!r || !Number.isInteger(r.pts) || r.pts < 0 || r.pts > MAX_POINTS) return { error: "Bad score" };
    const skipped = r.skipped === true;
    const km = Number.isFinite(r.km) && r.km >= 0 && r.km < 21000 ? r.km : null;
    results.push({ pts: r.pts, skipped, km: skipped ? null : km });
  }
  return { name, date, number, results };
}

function fmtMiles(km) {
  const mi = km * 0.621371;
  return mi < 10 ? mi.toFixed(1) : Math.round(mi).toLocaleString("en-US");
}

export function buildMessage({ name, date, number, results }) {
  const total = results.reduce((a, r) => a + r.pts, 0);
  const max = results.length * MAX_POINTS;
  const [, m, d] = date.split("-").map(Number);
  const squares = results.map(r => (r.skipped ? "\u2B1B" : SQUARES.find(([min]) => r.pts >= min)[1])).join("");
  const miles = results.map(r => (r.skipped || r.km === null ? "skipped" : `${fmtMiles(r.km)} mi`)).join(" \u00B7 ");
  return `**${name}** \u00B7 Crag Guesser #${number} (${m}/${d}) \u00B7 ${total.toLocaleString("en-US")}/${max.toLocaleString("en-US")}\n${squares}\n_${miles}_`;
}

function reply(obj, status, headers) {
  return new Response(JSON.stringify(obj), { status, headers: { ...headers, "Content-Type": "application/json" } });
}

export default {
  async fetch(request, env) {
    const allowed = (env.ALLOWED_ORIGIN || "").replace(/\/+$/, "");
    const cors = {
      "Access-Control-Allow-Origin": allowed || "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return reply({ error: "Use POST" }, 405, cors);
    if (allowed && request.headers.get("Origin") !== allowed) return reply({ error: "Not allowed from this site" }, 403, cors);
    if (!env.DISCORD_WEBHOOK_URL) return reply({ error: "The relay isn't configured yet" }, 500, cors);

    let body;
    try { body = await request.json(); } catch { return reply({ error: "Bad request" }, 400, cors); }
    const v = validate(body);
    if (v.error) return reply({ error: v.error }, 400, cors);

    // Optional limits, if a KV namespace is bound as POSTS.
    const nameKey = `n:${v.date}:${v.name.toLowerCase()}`;
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const ipKey = `ip:${v.date}:${ip}`;
    let ipCount = 0;
    if (env.POSTS) {
      if (await env.POSTS.get(nameKey)) return reply({ error: "That name has already posted for this puzzle" }, 409, cors);
      ipCount = parseInt((await env.POSTS.get(ipKey)) || "0", 10);
      if (ipCount >= PER_IP_DAILY_LIMIT) return reply({ error: "Too many posts from this connection today" }, 429, cors);
    }

    const resp = await fetch(env.DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": "crag-guesser-relay" },
      body: JSON.stringify({ content: buildMessage(v), flags: 4, allowed_mentions: { parse: [] } }),
    });
    if (!resp.ok) return reply({ error: "Discord didn't accept the post" }, 502, cors);

    if (env.POSTS) {
      const ttl = { expirationTtl: 4 * 86400 };
      await env.POSTS.put(nameKey, "1", ttl);
      await env.POSTS.put(ipKey, String(ipCount + 1), ttl);
    }
    return reply({ ok: true }, 200, cors);
  },
};
