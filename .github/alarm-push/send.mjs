// Sends lock-screen alarms for Daxton's Life.
// Runs on GitHub (public repo), so it never prints alarm names or phone addresses.
// Reads alarms + phone addresses from the private data repo checked out at $DATA_DIR.
import fs from "node:fs";
import { execSync } from "node:child_process";
import webpush from "web-push";

const DIR = process.env.DATA_DIR || "data";
const RUN_MS = (Number(process.env.RUN_MINUTES) || 55) * 60000;
const STATE = "push-state.json", SUBS = "push-subs.json";
const REPEAT_MS = 60000, MAX_PUSHES = 6, TOO_LATE_MS = 20 * 60000;
const SITE = "https://daxtontessmer-ai.github.io/Daxtons-Life";

const git = cmd => execSync(`git -C ${DIR} ${cmd}`, { stdio: "pipe" }).toString();
const read = (f, d) => { try { return JSON.parse(fs.readFileSync(`${DIR}/${f}`, "utf8")); } catch { return d; } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

git(`config user.name "Daxton's Life alarms"`);
git(`config user.email "alarms@users.noreply.github.com"`);
const keys = read("push-keys.json", null);
if (!keys) { console.log("No push keys in data repo yet."); process.exit(0); }
webpush.setVapidDetails(SITE + "/", keys.publicKey, keys.privateKey);

function save(files, msg) {
  for (let i = 0; i < 4; i++) {
    try { git(`add ${files.join(" ")}`); git(`commit -q -m "${msg}"`); } catch { return; } // nothing to commit
    try { git("push -q"); return; } catch { try { git("pull -q --rebase"); } catch {} }
  }
}

const start = Date.now(); let lastPull = 0, sent = 0;
while (Date.now() - start < RUN_MS) {
  if (Date.now() - lastPull > 20000) { try { git("pull -q --rebase"); } catch {} lastPull = Date.now(); }
  const data = read("data.json", {}), subs = read(SUBS, {}), state = read(STATE, {});
  const alarms = ((data.sections || {}).alarms || []).filter(a => a && a.id && a.at && !a.deleted && !a.stoppedAt);
  let changed = false; const dead = [];
  for (const a of alarms) {
    const due = Date.parse(a.at), now = Date.now(), st = state[a.id] || { n: 0, last: 0 };
    if (now < due || now - due > TOO_LATE_MS || st.n >= MAX_PUSHES || now - st.last < REPEAT_MS) continue;
    st.n++; st.last = now; state[a.id] = st; changed = true;
    const late = Math.round((now - due) / 60000);
    const body = st.n === 1
      ? (late >= 2 ? `Daxton's Life alarm · ${late} min late` : "Daxton's Life alarm · tap for Snooze or Turn off")
      : `Still going (${st.n}/${MAX_PUSHES}) · tap to turn off`;
    for (const [key, s] of Object.entries(subs)) {
      const url = SITE + (s.scope || "/main/") + "?alarm=" + encodeURIComponent(a.id);
      const payload = JSON.stringify({ title: "⏰ " + a.name, body, tag: a.id + "-" + st.n, url });
      try { await webpush.sendNotification(s.sub, payload, { TTL: 600, urgency: "high" }); sent++; }
      catch (e) { if (e.statusCode === 404 || e.statusCode === 410) dead.push(key); else console.log("send failed:", e.statusCode || e.message); }
    }
  }
  if (changed) {
    for (const [id, st] of Object.entries(state)) if (Date.now() - st.last > 3 * 864e5) delete state[id];
    fs.writeFileSync(`${DIR}/${STATE}`, JSON.stringify(state, null, 1));
    const files = [STATE];
    if (dead.length) { const fresh = read(SUBS, {}); dead.forEach(k => delete fresh[k]); fs.writeFileSync(`${DIR}/${SUBS}`, JSON.stringify(fresh, null, 1)); files.push(SUBS); }
    save(files, "Alarm notifications sent");
  }
  await sleep(10000);
}
console.log(`Done. Notifications sent this run: ${sent}`);
