// Job Search app: the window into the job search system.
// Jobs (the report), Documents (resume drafts), Profile (your files), Activity (everything the
// system saw and decided), Setup (what's done, what's next). Data comes from app/server.py.

// ---------- helpers ----------
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const k = n => "$" + Math.round(n / 1000) + "K";
const getJSON = async url => (await fetch(url)).json();
const post = (url, body) => fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) })
  .then(async r => { if (!r.ok) throw new Error((await r.json()).error || r.statusText); return r.json(); });
const store = {
  get(key, d) { try { const v = localStorage.getItem("jr." + key); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(key, v) { try { localStorage.setItem("jr." + key, JSON.stringify(v)); } catch (e) {} },
};
const when = iso => new Date(iso).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
function soon(iso) {  // "today 2:00 PM", "tomorrow 6:00 AM", "Thu 12:09 PM"
  if (!iso) return "not scheduled";
  const d = new Date(iso), now = new Date(), t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const days = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 864e5);
  return days === 0 ? `today ${t}` : days === 1 ? `tomorrow ${t}` : `${d.toLocaleDateString([], { weekday: "short" })} ${t}`;
}
const linkOut = (url, label, cls = "src") => url
  ? `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>` : "";
const ask = text => `<button class="ask" data-ask="${esc(text)}" title="Copy, then paste into Claude">“${esc(text)}”</button>`;
document.addEventListener("click", e => {
  const b = e.target.closest("[data-ask]");
  if (!b) return;
  navigator.clipboard?.writeText(b.dataset.ask).catch(() => {});
  b.classList.add("copied"); setTimeout(() => b.classList.remove("copied"), 1500);
});

// Minimal Markdown: headings, lists (nested), tables, code, quotes, links, bold/italic.
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => /^(https?:|#)/.test(u) ? `<a href="${u}" target="_blank" rel="noopener">${t}</a>` : `<span title="${u}">${t}</span>`)
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(])[*_]([^*_\s][^*_]*?)[*_](?=[\s).,;:!?]|$)/g, "$1<i>$2</i>");
}
function md(src) {
  const lines = String(src || "").replace(/\r/g, "").split("\n"), out = [];
  let i = 0;
  const listRe = /^(\s*)([-*+]|\d+\.)\s+(.*)$/;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`); continue;
    }
    if (/^#{1,6}\s/.test(line)) { const n = line.match(/^#+/)[0].length; out.push(`<h${n}>${inline(line.slice(n).trim())}</h${n}>`); i++; continue; }
    if (/^(-{3,}|\*{3,})\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
    if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const body = rows.filter((r, n) => !(n === 1 && /^[\s|:-]+$/.test(r)));
      out.push(`<table><thead><tr>${cells(body[0]).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${
        body.slice(1).map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${md(buf.join("\n"))}</blockquote>`); continue;
    }
    if (listRe.test(line)) {
      const items = [];
      while (i < lines.length && (listRe.test(lines[i]) || (/^\s+\S/.test(lines[i]) && items.length))) {
        const m = lines[i].match(listRe);
        if (m) items.push({ ind: m[1].length, ordered: /\d/.test(m[2]), text: m[3] });
        else items[items.length - 1].text += " " + lines[i].trim();
        i++;
      }
      const build = (j, ind) => {
        const tag = items[j].ordered ? "ol" : "ul"; let h = `<${tag}>`;
        while (j < items.length && items[j].ind >= ind) {
          if (items[j].ind > ind) { const [sub, next] = build(j, items[j].ind); h = h.replace(/<\/li>$/, sub + "</li>"); j = next; continue; }
          h += `<li>${inline(items[j].text)}</li>`; j++;
        }
        return [h + `</${tag}>`, j];
      };
      out.push(build(0, items[0].ind)[0]); continue;
    }
    if (!line.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*\||>|(-{3,})\s*$)/.test(lines[i]) && !listRe.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join(" "))}</p>`);
  }
  return out.join("\n");
}

// ---------- data ----------
let FLOOR = null, TARGET_LO = null, TARGET_HI = null, STALE_DAYS = 45, PROFILE_MIN_SCORE = 60, STYLE = "modern", TEST_MODE = false;
let SCALE_LO = 0, SCALE_HI = 1;
let jobs = [], companies = {}, overview = null, runs = { runs: [], unreviewed: 0 }, docs = null;
const MARKED = ["interested", "applying", "applied", "interviewing", "offer"];
const CLOSED = ["dismissed", "rejected", "ghosted"];

function applySettings(s) {
  ({ floor: FLOOR, target_low: TARGET_LO, target_high: TARGET_HI } = s.pay || {});
  STALE_DAYS = s.stale_days ?? 45;
  PROFILE_MIN_SCORE = s.profile_min_score ?? 60;
  STYLE = s.resume_style || "modern";
  TEST_MODE = !!s.test_mode;
  const band = FLOOR && TARGET_LO && TARGET_HI;
  if (band) {
    SCALE_LO = Math.floor(FLOOR * 0.75 / 10000) * 10000;
    SCALE_HI = Math.ceil(TARGET_HI * 1.6 / 10000) * 10000;
  }
  const dot = c => `<i style="background:var(--${c})"></i>`;
  $("legend").innerHTML = (band
    ? `<span>${dot("good")}Pay in or above target (${k(TARGET_LO)}–${k(TARGET_HI)})</span>
       <span>${dot("warn")}At the floor (${k(FLOOR)}–${k(TARGET_LO)}): needs a great fit</span>
       <span>${dot("bad")}Tops out below ${k(FLOOR)}</span>`
    : `<span>No pay band set: add one to profile/settings.json</span>`)
    + `<span>${dot("none")}Not listed</span><span>Stale = posted ${STALE_DAYS}+ days ago</span>`;
}

async function loadAll() {
  const [s, o, r, j, c] = await Promise.all(["/api/settings", "/api/overview", "/api/runs", "/api/jobs", "/api/companies"].map(getJSON));
  applySettings(s);
  overview = o; runs = r; jobs = j.jobs; companies = c.companies;
  renderChrome();
  route();
}
async function refreshJobs() {
  const [o, j] = await Promise.all([getJSON("/api/overview"), getJSON("/api/jobs")]);
  overview = o; jobs = j.jobs; docs = null; dash = null;
  renderChrome();
  route();
}

// ---------- chrome: stats, nav badges, status line ----------
const schedule = id => (overview?.setup.schedules || []).find(s => s.id === id);

function renderChrome() {
  const sources = [...new Set(jobs.flatMap(j => j.sources.filter(s => s.source !== "company").map(s => s.source.replace("ats:", ""))))];
  $("sub").textContent = jobs.length ? `${jobs.length} jobs tracked · ${sources.join(" · ")}` : "";
  const todo = overview.setup.steps.filter(s => s.state !== "done").length;
  $("nav-setup").hidden = !todo; $("nav-setup").textContent = todo;
  $("nav-docs").hidden = !overview.drafts.ready; $("nav-docs").textContent = overview.drafts.ready;
}

// ---------- routing ----------
const VIEWS_ALL = ["home", "jobs", "documents", "profile", "activity", "setup"];
function route() {
  let v = location.hash.slice(1).split("/")[0];
  if (!VIEWS_ALL.includes(v)) v = overview.setup.ready ? "home" : "setup";
  document.querySelectorAll("#nav a").forEach(a => a.setAttribute("aria-current", a.dataset.view === v ? "page" : "false"));
  VIEWS_ALL.forEach(x => $("view-" + x).hidden = x !== v);
  ({ home: renderHome, jobs: renderJobs, documents: renderDocuments, profile: renderProfile, activity: renderActivity, setup: renderSetup })[v]();
}

// ---------- Home ----------
let dash = null;
const fmtDay = d => new Date(d + "T12:00").toLocaleDateString([], { month: "short", day: "numeric" });
const SERIES = [["kept", "Kept", "var(--series-1)"], ["filtered", "Filtered out", "var(--series-2)"], ["waiting", "Waiting for review", "var(--series-3)"]];

function intakeChart(perDay) {
  // Days from the first day with data (or 14 days back, whichever is later) to today, zeros filled in.
  const today = new Date(), start = new Date(today); start.setDate(start.getDate() - 13);
  const first = perDay[0] ? new Date(perDay[0].day + "T12:00") : today;
  const from = first > start ? first : start, byDay = Object.fromEntries(perDay.map(d => [d.day, d])), days = [];
  for (const d = new Date(from); d <= today; d.setDate(d.getDate() + 1)) {
    const key = d.toLocaleDateString("en-CA");
    days.push({ day: key, found: 0, kept: 0, filtered: 0, waiting: 0, ...byDay[key] });
  }
  const W = 640, H = 210, L = 30, R = 6, T = 16, B = 24, iw = W - L - R, ih = H - T - B;
  const max = Math.max(5, ...days.map(d => d.found));
  const step = Math.pow(10, Math.floor(Math.log10(max))) * (max / Math.pow(10, Math.floor(Math.log10(max))) > 5 ? 2 : 1);
  const top = Math.ceil(max / step) * step, y = v => T + ih - v / top * ih;
  const band = iw / days.length, bw = Math.min(34, band * 0.62);
  const grid = [];
  for (let v = 0; v <= top; v += step) grid.push(`<line class="gridline" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  const every = Math.ceil(days.length / 8);
  const bars = days.map((d, i) => {
    const x = L + band * i + (band - bw) / 2, segs = [];
    let base = 0;
    const parts = SERIES.filter(([k]) => d[k] > 0);
    parts.forEach(([k, , color], n) => {
      const y0 = y(base), y1 = y(base + d[k]) + (n < parts.length - 1 ? 0 : 0), h = y0 - y1 - (n > 0 ? 2 : 0);
      const yb = y0 - (n > 0 ? 2 : 0);  // 2px surface gap between stacked segments
      if (h > 0) segs.push(n === parts.length - 1
        ? `<path d="M${x},${yb} V${yb - h + 4} Q${x},${yb - h} ${x + 4},${yb - h} H${x + bw - 4} Q${x + bw},${yb - h} ${x + bw},${yb - h + 4} V${yb} Z" fill="${color}"/>`
        : `<rect x="${x}" y="${yb - h}" width="${bw}" height="${h}" fill="${color}"/>`);
      base += d[k];
    });
    const label = i % every === 0 || i === days.length - 1 ? `<text class="axis" x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${fmtDay(d.day)}</text>` : "";
    const total = d.found ? `<text class="total" x="${x + bw / 2}" y="${y(d.found) - 5}" text-anchor="middle">${d.found}</text>` : "";
    return segs.join("") + total + label + `<rect class="hit" data-i="${i}" x="${L + band * i}" y="${T}" width="${band}" height="${ih}"/>`;
  }).join("");
  return { days, html: `
    <div class="legend-row">${SERIES.map(([, label, c]) => `<span><i style="background:${c}"></i>${label}</span>`).join("")}</div>
    <div class="chart" id="intake"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="New listings per day, split into kept, filtered out, and waiting">${grid.join("")}${bars}</svg></div>
    <details class="table-view small"><summary>Show as table</summary><table class="grid"><thead><tr><th>Day</th><th class="n">Found</th>${SERIES.map(([, l]) => `<th class="n">${l}</th>`).join("")}</tr></thead>
      <tbody>${days.map(d => `<tr><td>${fmtDay(d.day)}</td><td class="n">${d.found}</td>${SERIES.map(([k]) => `<td class="n">${d[k]}</td>`).join("")}</tr>`).join("")}</tbody></table></details>` };
}

function hbars(rows) {
  const max = Math.max(1, ...rows.map(r => r.v));
  return `<div class="hbars">${rows.map(r => `<div class="hbar"><div class="l">${esc(r.l)}${r.s ? `<small>${esc(r.s)}</small>` : ""}</div>
    <div class="track"><div class="fill" style="width:${r.v / max * 100}%"></div></div><div class="v">${r.v.toLocaleString()}</div></div>`).join("")}</div>`;
}

async function renderHome() {
  const v = $("view-home");
  if (!dash) dash = await getJSON("/api/dashboard");
  const st = overview.setup, d = overview.drafts, s = dash.status;
  const count = (...ks) => ks.reduce((n, k2) => n + (s[k2] || 0), 0);
  const hour = new Date().getHours(), hi = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const review = runs.runs.find(r => r.kind === "review"), collect = runs.runs.find(r => r.kind === "collect");
  const kpi = (n, label, view) => `<button class="kpi" data-jobs="${view}"><b>${n}</b><span>${label}</span></button>`;
  const next = [["collector_schedule", "Collection", " (+ up to 2 h)"], ["review_schedule", "Review", ""], ["drafts_schedule", "Resume drafts", ""]]
    .map(([id, label, extra]) => { const x = schedule(id); return `<li><span>${label}</span><span>${x ? soon(x.next) + extra : `<a href="#setup">not scheduled</a>`}</span></li>`; });
  const chart = intakeChart(dash.per_day);
  const w = dash.work, t = dash.totals;
  const srcLabel = { linkedin: "LinkedIn", indeed: "Indeed", ziprecruiter: "ZipRecruiter", dice: "Dice", "company job boards": "Company job boards" };
  v.innerHTML = `
    <div class="hello"><h2>${hi}${overview.name ? ", " + esc(overview.name) : ""}</h2>
      <p>${st.ready ? `Here's where your search stands${review ? ` · last review ${when(review.started)}` : ""}.` : "Let's finish setting things up first."}</p></div>
    ${!st.ready ? `<div class="panel"><div class="body"><div class="callout warn">Setup isn't finished: ${st.steps.filter(x => x.state === "done").length} of ${st.steps.length} steps done.
      Open Claude in this folder and say “Set this up for me.” <a href="#setup">See setup →</a></div></div></div>` : ""}
    <div class="kpis">
      ${kpi(count("new"), "new jobs to review", "new")}${kpi(dash.strong, "strong fits (70+)", "new")}
      ${kpi(count("interested", "applying"), "interested", "interested")}${kpi(count("applied", "interviewing", "offer"), "applied", "applied")}
    </div>
    <div class="cols">
      <div class="panel"><div class="panel-head"><h2>Latest review</h2>${review ? `<span class="small muted">${when(review.started)}</span>` : ""}</div>
        <div class="body">${review ? `<p style="margin-top:0">${esc(review.summary || "")}</p>` : `<p class="muted">No review yet.</p>`}
        ${collect ? `<p class="small muted" style="margin-bottom:0">Last collection ${when(collect.started)}: ${esc(collect.summary || "")}${runs.unreviewed ? ` ${runs.unreviewed} listings are waiting for the next review.` : ""}</p>` : ""}</div></div>
      <div class="panel"><div class="panel-head"><h2>Up next</h2></div><div class="body">
        <ul class="upnext">${next.join("")}</ul>
        ${d.ready || d.pending ? `<div class="callout">${d.ready ? `<b>${d.ready} resume draft${d.ready > 1 ? "s" : ""} ready</b> for your review. ` : ""}${
          d.pending ? `${d.pending} more queued for jobs you marked Interested.` : ""} <a href="#documents">Open documents →</a></div>` : ""}
        ${st.ready && !st.complete ? `<div class="callout warn">Optional setup left: ${esc(st.steps.filter(x => x.state !== "done").map(x => x.title.toLowerCase()).join(", "))}. <a href="#setup">Setup →</a></div>` : ""}
        ${TEST_MODE ? `<p class="small muted" style="margin:10px 0 0">Test mode is on: LinkedIn is capped at 6 requests a day.</p>` : ""}
      </div></div>
    </div>
    <div class="panel"><div class="panel-head"><h2>New listings per day</h2><span class="small muted">every listing the searches turned up, and what happened to it</span></div>
      <div class="body">${chart.html}</div></div>
    <div class="cols">
      <div class="panel"><div class="panel-head"><h2>From listings to applications</h2><span class="small muted">all time</span></div><div class="body">
        ${hbars([{ l: "Listings found", v: t.found }, { l: "Kept after review", v: t.kept }, { l: "Jobs in your report", s: "duplicates across sites merged", v: t.jobs },
                 { l: "Interested", v: count("interested", "applying", "applied", "interviewing", "offer") }, { l: "Applied", v: count("applied", "interviewing", "offer") }])}
        <p class="small muted" style="margin:10px 0 0">${t.filtered.toLocaleString()} listings were filtered out with a reason. <a href="#activity">See what didn't make the cut →</a></p></div></div>
      <div class="panel"><div class="panel-head"><h2>Where listings come from</h2><span class="small muted">all time</span></div><div class="body">
        ${hbars(Object.entries(dash.sources).sort((a, b) => b[1] - a[1]).map(([k2, n]) => ({ l: srcLabel[k2] || k2, v: n })))}</div></div>
    </div>
    <div class="panel"><div class="panel-head"><h2>What the system has done for you</h2>${w.since ? `<span class="small muted">since ${fmtDay(w.since)}</span>` : ""}</div>
      <div class="work">
        <div><b>${t.found.toLocaleString()}</b><span>listings looked at</span></div>
        <div><b>${t.filtered.toLocaleString()}</b><span>filtered out for you</span></div>
        <div><b>${t.jobs}</b><span>jobs researched and scored</span></div>
        <div><b>${w.companies_researched}</b><span>companies researched</span></div>
        <div><b>${w.linkedin_searches + w.connector_searches}</b><span>searches run</span></div>
        <div><b>${w.boards}</b><span>company job boards checked</span></div>
        <div><b>${w.one_pagers}</b><span>company one-pagers written</span></div>
        <div><b>${w.drafts}</b><span>tailored resume drafts</span></div>
      </div></div>`;
  v.querySelectorAll("[data-jobs]").forEach(b => b.onclick = () => { state.view = b.dataset.jobs; store.set("view", state.view); location.hash = "jobs"; });
  // hover tooltip on each day's column
  const box = $("intake"), tip = document.createElement("div");
  tip.className = "tip"; tip.hidden = true; box.appendChild(tip);
  box.querySelectorAll(".hit").forEach(h => {
    h.onmouseenter = () => {
      const dd = chart.days[+h.dataset.i];
      tip.innerHTML = `<b>${fmtDay(dd.day)} · ${dd.found} found</b>${SERIES.map(([k2, l, c]) => `<div><span><i style="background:${c}"></i>${l}</span><span>${dd[k2]}</span></div>`).join("")}`;
      tip.hidden = false;
      const r = h.getBoundingClientRect(), b = box.getBoundingClientRect();
      tip.style.left = Math.min(Math.max(0, r.left - b.left + r.width / 2 - 80), b.width - 170) + "px";
      tip.style.top = "0px";
    };
    h.onmouseleave = () => { tip.hidden = true; };
  });
}
window.addEventListener("hashchange", route);

// ---------- Jobs ----------
const JOB_VIEWS = [
  ["new", "New", j => j.status === "new"],
  ["interested", "Interested", j => ["interested", "applying"].includes(j.status)],
  ["applied", "Applied", j => ["applied", "interviewing", "offer"].includes(j.status)],
  ["closed", "Closed", j => ["rejected", "ghosted"].includes(j.status)],
  ["dismissed", "Dismissed", j => j.status === "dismissed"],
  ["all", "All", () => true],
];
let state = { view: store.get("view", "new"), sort: store.get("sort", "score"), q: "",
              filters: store.get("filters", { remote: false, payok: false, fresh: false, ai: false }) };
if (!JOB_VIEWS.some(v => v[0] === state.view)) state.view = "new";

function payFit(j) {
  const hi = j.salary_max || j.salary_min;
  if (!hi) return { cls: "none", label: "Pay not listed" };
  if (!FLOOR || !TARGET_LO || !TARGET_HI) return { cls: "none", label: "No pay band set" };
  if (hi < FLOOR) return { cls: "bad", label: "Below your floor" };
  if (hi < TARGET_LO) return { cls: "warn", label: "At your floor" };
  if (j.salary_min && j.salary_min < FLOOR * 0.97) return { cls: "warn", label: "Reaches target; low end under floor" };
  return { cls: "good", label: (j.salary_min || 0) > TARGET_HI ? "Above target" : "In target range" };
}
const mid = j => ((j.salary_min || j.salary_max || 0) + (j.salary_max || j.salary_min || 0)) / 2;
const isStale = j => j.age_days != null && j.age_days >= STALE_DAYS;
const isRemote = j => /remote/i.test(`${j.workplace} ${j.location}`);
const isFresh = j => { const r = runs.runs.find(x => x.kind === "review"); return r && j.first_seen.slice(0, 10) >= r.started.slice(0, 10); };
const wantsProfile = j => MARKED.includes(j.status) || (j.analysis?.score ?? 0) >= PROFILE_MIN_SCORE;
const GAP_LABELS = { description: "Full job description", employer_posting: "Employer's own posting",
  salary: "Pay", sentiment: "Employee sentiment", news: "Recent news", company_profile: "Company one-pager" };
const gapLabel = g => GAP_LABELS[g.what] || g.what;
const resumeDoc = j => (j.documents || []).find(d => d.kind === "resume");
const shortTitle = j => `${j.company} – ${j.title.trim()}`;

async function setStatus(id, status) {
  let note = "";
  if (status === "dismissed") {
    const reason = prompt("Why dismiss? (this helps tune future reports)");
    if (reason === null) return;
    note = reason;
  }
  await post(`/api/jobs/${id}/status`, { status, note });
  await refreshJobs();
}

function filtered() {
  const f = state.filters, q = state.q.toLowerCase();
  let list = jobs.filter(JOB_VIEWS.find(v => v[0] === state.view)[2]);
  if (f.remote) list = list.filter(isRemote);
  if (f.payok) list = list.filter(j => payFit(j).cls !== "bad");
  if (f.fresh) list = list.filter(j => !isStale(j));
  if (f.ai) list = list.filter(j => j.analysis?.ai_forward);
  if (q) list = list.filter(j => `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q));
  const by = {
    score: (a, b) => (b.analysis?.score ?? -1) - (a.analysis?.score ?? -1),
    pay: (a, b) => mid(b) - mid(a),
    newest: (a, b) => (a.age_days ?? 1e9) - (b.age_days ?? 1e9),
    company: (a, b) => a.company.localeCompare(b.company),
  }[state.sort];
  return list.sort(by);
}

function renderJobs() {
  if (!overview.setup.ready) {
    const left = overview.setup.steps.filter(s => s.required && s.state !== "done");
    $("jobs-toolbar").hidden = true; $("legend").hidden = true;
    $("list").innerHTML = `<div class="panel gate"><h2>Your job list opens once setup is done</h2>
      <p class="muted">Still to do: ${esc(left.map(s => s.title).join(" · "))}.</p>
      <p><a class="btn primary" href="#setup">Go to setup</a></p></div>`;
    return;
  }
  $("jobs-toolbar").hidden = false; $("legend").hidden = false;
  const tabs = $("tabs");
  tabs.innerHTML = JOB_VIEWS.map(([key, label, f]) =>
    `<button class="tab" role="tab" aria-selected="${key === state.view}" data-v="${key}">${label}<span class="n">${jobs.filter(f).length}</span></button>`).join("");
  tabs.querySelectorAll(".tab").forEach(b => b.onclick = () => { state.view = b.dataset.v; store.set("view", state.view); renderJobs(); });
  document.querySelectorAll(".toggle").forEach(b => b.setAttribute("aria-pressed", state.filters[b.dataset.f]));
  $("sort").value = state.sort;
  const list = filtered();
  $("list").innerHTML = list.length ? list.map(card).join("")
    : `<p class="empty">Nothing matches. Try another tab or clear the filters.</p>`;
  document.querySelectorAll("[data-act]").forEach(b => b.onclick = () => setStatus(+b.dataset.id, b.dataset.act));
  document.querySelectorAll("[data-co]").forEach(b => b.onclick = () => openCompany(b.dataset.co));
  document.querySelectorAll("[data-doc]").forEach(b => b.onclick = () => openResume(+b.dataset.doc, b.dataset.tab));
}
$("sort").onchange = e => { state.sort = e.target.value; store.set("sort", state.sort); renderJobs(); };
$("q").oninput = e => { state.q = e.target.value; renderJobs(); };
document.querySelectorAll(".toggle").forEach(b => b.onclick = () => {
  state.filters[b.dataset.f] = !state.filters[b.dataset.f]; store.set("filters", state.filters); renderJobs(); });

function payBlock(j) {
  const pf = payFit(j);
  const lo = j.salary_min || j.salary_max, hi = j.salary_max || j.salary_min;
  const pct = v => Math.max(0, Math.min(100, (v - SCALE_LO) / (SCALE_HI - SCALE_LO) * 100));
  const amt = j.salary_text && !j.salary_min ? esc(j.salary_text) : hi ? (lo === hi ? k(hi) : `${k(lo)}–${k(hi)}`) : "—";
  return `<div class="pay" style="--pc:var(--${pf.cls})">
    <div class="amt">${amt}</div>
    <div class="lbl">${pf.label}</div>
    ${FLOOR && TARGET_LO && TARGET_HI ? `<div class="paybar" title="Green band = your ${k(TARGET_LO)}–${k(TARGET_HI)} target; amber tick = ${k(FLOOR)} floor">
      <div class="tgt" style="left:${pct(TARGET_LO)}%;width:${pct(TARGET_HI) - pct(TARGET_LO)}%"></div>
      <div class="floor" style="left:${pct(FLOOR)}%"></div>
      ${hi ? `<div class="rng" style="left:${pct(lo)}%;width:${Math.max(pct(hi) - pct(lo), 1.5)}%"></div>` : ""}
    </div>
    <div class="scale"><span>${k(SCALE_LO)}</span><span>${k(SCALE_HI)}+</span></div>` : ""}
    <div class="facts">
      <span>${esc(j.workplace || "workplace ?")}${j.employment_type ? " · " + esc(j.employment_type) : ""}</span>
      <span class="${isStale(j) ? "warn" : ""}">${j.age_days == null ? "Posting date unknown" : j.age_days === 0 ? "Posted today" : `Posted ${j.age_days}d ago`}${isStale(j) ? " · stale" : ""}</span>
      ${j.applicants ? `<span>${esc(j.applicants)}</span>` : ""}
    </div>
  </div>`;
}

function docLine(j) {
  const d = resumeDoc(j);
  if (d) return `<div class="docline"><b>Resume draft ${d.status === "draft" ? "ready" : esc(d.status)}</b>
      <span class="muted">${esc(d.summary || "")}</span>
      <button class="btn" data-doc="${j.id}" data-tab="resume">View</button><button class="btn" data-doc="${j.id}" data-tab="notes">What changed</button>
      ${ask(`Revise my resume draft for ${shortTitle(j)}`)}</div>`;
  if (["interested", "applying"].includes(j.status)) {
    const s = schedule("drafts_schedule");
    return `<div class="docline queued">Resume draft queued${s ? ` · next drafts run ${soon(s.next)}` : ""}. Or now: ${ask(`Draft a resume for ${shortTitle(j)}`)}</div>`;
  }
  return "";
}

function card(j) {
  const a = j.analysis || {}, c = j.company_info || {};
  const s = a.score;
  const sc = s == null ? "none" : s >= 70 ? "good" : s >= 45 ? "warn" : "bad";
  const li = xs => (xs || []).map(x => `<li>${esc(x)}</li>`).join("");
  const flags = (j.flags || []).map(f => `<span class="chip ${f.level === "red" ? "bad" : "warn"}">${esc(f.text)}</span>`).join("");
  // Employer's own posting first; then job boards, one link per URL (a search page is labeled as one).
  const own = j.sources.find(x => x.source === "company" && x.url);
  const seenUrls = new Set(own ? [own.url] : []);
  const boards = j.sources.filter(x => x.source !== "company" && x.url && !seenUrls.has(x.url) && seenUrls.add(x.url));
  const srcs = (own ? linkOut(own.url, "Company posting ↗", "src primary")
      : linkOut(`https://www.google.com/search?q=${encodeURIComponent(`${j.company} careers "${j.title.trim()}"`)}`,
                "Find on company site", "src search"))
    + boards.map(x => /[?&](search|keywords|q)=/.test(x.url)
      ? linkOut(x.url, `${x.source.replace("ats:", "")} (search results)`, "src search")
      : linkOut(x.url, x.source.replace("ats:", ""))).join("");
  const gaps = j.gaps || [];
  const profile = companies[j.company_key];
  const profilePending = !profile && wantsProfile(j) && !CLOSED.includes(j.status);
  const allGaps = profilePending && !gaps.some(g => g.what === "company_profile")
    ? [...gaps, { what: "company_profile", why: MARKED.includes(j.status) ? "you marked this job" : "strong enough score" }] : gaps;
  const hist = (j.events || []).map(e => `<li>${esc(e.at.slice(0, 16).replace("T", " "))} · ${esc(e.kind)}: ${esc(e.detail)}</li>`).join("");
  const act = (st, label, primary) => j.status === st ? "" :
    `<button class="btn${primary ? " primary" : ""}" data-act="${st}" data-id="${j.id}">${label}</button>`;
  return `<article class="card${CLOSED.includes(j.status) ? " dim" : ""}">
    <div class="main">
      <div style="--c:var(--${sc})">
        <div class="score" style="--p:${s ?? 0}" title="Fit score (0–100)"><b>${s ?? "–"}</b></div>
        <div class="fit">${esc(a.fit || "")}</div>
      </div>
      <div>
        <h2 class="title">${esc(j.title.trim())}</h2>
        <div class="co">${esc(j.company)} · ${esc(j.location || "")}</div>
        <div class="chips">
          ${isFresh(j) ? `<span class="chip new">New</span>` : ""}
          ${a.lean ? `<span class="chip">${esc(a.lean)}</span>` : ""}
          ${a.ai_forward ? `<span class="chip ai">AI-forward</span>` : ""}
          ${allGaps.length ? `<span class="chip todo" title="Still to research: ${esc(allGaps.map(gapLabel).join(", "))}. The next review fills these in.">Research in progress · ${allGaps.length}</span>` : ""}
          ${flags}
        </div>
        ${a.summary ? `<p class="summary">${esc(a.summary)}</p>` : ""}
      </div>
      ${payBlock(j)}
    </div>
    ${(a.why?.length || a.concerns?.length) ? `<div class="detail">
      <div class="col pros"><h4>Why it fits</h4><ul>${li(a.why)}</ul></div>
      <div class="col cons"><h4>Concerns</h4><ul>${li(a.concerns)}</ul></div>
    </div>` : ""}
    <details>
      <summary style="padding:10px 18px">Resume, level, company &amp; history</summary>
      <div class="more">
        <div>
          ${a.resume ? `<p><b>Resume:</b> ${esc(a.resume)}</p>` : ""}
          ${a.level ? `<p><b>Level fit:</b> ${esc(a.level)}</p>` : ""}
          <p><b>History</b></p><ul class="history">${hist}</ul>
        </div>
        <div>
          ${c.what ? `<p><b>What they do:</b> ${esc(c.what)}</p>` : ""}
          ${c.size ? `<p><b>Size / stage:</b> ${esc(c.size)}</p>` : ""}
          ${c.funding ? `<p><b>Funding:</b> ${esc(c.funding)}</p>` : ""}
          ${c.sentiment ? `<p><b>Employees say:</b> ${esc(c.sentiment)}</p>` : ""}
          ${c.news ? `<p><b>Recent:</b> ${esc(c.news)}</p>` : ""}
          ${c.website ? `<p><a href="${esc(c.website)}" target="_blank" rel="noopener">${esc(c.website.replace(/^https?:\/\//, ""))}</a></p>` : ""}
          ${c.data_notes ? `<p class="sub">${esc(c.data_notes)}</p>` : ""}
          ${allGaps.length ? `<p><b>Still to research</b> (the next review fills these in)</p><ul class="gaps">${allGaps.map(g =>
            `<li>${esc(gapLabel(g))}${g.why ? ` <span>· ${esc(g.why)}</span>` : ""}</li>`).join("")}</ul>` : ""}
        </div>
      </div>
    </details>
    ${docLine(j)}
    <div class="foot">
      <div class="links">${srcs} ${j.status !== "new" ? `<span class="status-pill">${esc(j.status)}</span>` : ""}</div>
      <div class="actions">
        ${profile ? `<button class="btn" data-co="${esc(j.company_key)}">Company one-pager</button>` : ""}
        ${act("interested", "Interested", true)}${act("applied", "Mark applied")}${act("dismissed", "Dismiss")}${j.status !== "new" ? act("new", "Reset") : ""}
      </div>
    </div>
  </article>`;
}

// ---------- company one-pager ----------
function openCompany(key) {
  const p = companies[key];
  if (!p) return;
  const li = xs => (xs || []).map(x => `<li>${esc(x)}</li>`).join("");
  const open = jobs.filter(j => j.company_key === key && !CLOSED.includes(j.status));
  const dlg = $("co-page");
  dlg.innerHTML = `<div class="co-head">
      <div>
        <h2>${esc(p.name)}</h2>
        ${p.tagline ? `<div class="tag">${esc(p.tagline)}</div>` : ""}
        <div class="co-links">${linkOut(p.website, "Website")}${linkOut(p.careers, "Careers")}
          <span class="sub">Updated ${esc(p.updated.slice(0, 10))}</span></div>
      </div>
      <button class="btn" data-close>Close</button>
    </div>
    <div class="co-body">
      ${p.overview ? `<h3>Overview</h3><p>${esc(p.overview)}</p>` : ""}
      ${(p.sections || []).map(s => `<h3>${esc(s.heading)}</h3>${s.text ? `<p>${esc(s.text)}</p>` : ""}${s.bullets?.length ? `<ul>${li(s.bullets)}</ul>` : ""}`).join("")}
      ${p.news?.length ? `<h3>Recent news</h3><ul class="news">${p.news.map(n =>
        `<li><span>${esc(n.date || "")}</span> ${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.text)}</a>` : esc(n.text)}</li>`).join("")}</ul>` : ""}
      ${p.for_you?.length ? `<h3>What it means for you</h3><ul>${li(p.for_you)}</ul>` : ""}
      ${p.questions?.length ? `<h3>Questions worth asking</h3><ul>${li(p.questions)}</ul>` : ""}
      ${open.length ? `<h3>Jobs here in your tracker</h3><ul>${open.map(j =>
        `<li>${esc(j.title)} · ${j.analysis?.score ?? "–"} · ${esc(j.status)}</li>`).join("")}</ul>` : ""}
      ${p.sources?.length ? `<h3>Sources</h3><div class="co-src">${p.sources.map(s =>
        `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a>`).join(" · ")}</div>` : ""}
    </div>`;
  showDialog(dlg);
}
function showDialog(dlg) {
  dlg.querySelector("[data-close]").onclick = () => dlg.close();
  dlg.onclick = e => { if (e.target === dlg) dlg.close(); };
  dlg.showModal();
  dlg.scrollTop = 0;
}

// ---------- resume draft viewer ----------
const docFile = (d, ext) => `/files/${d.path}/${STYLE}.${ext}`;
async function openResume(jobId, tab = "resume") {
  const j = jobs.find(x => x.id === jobId), d = resumeDoc(j);
  const dlg = $("sheet");
  const show = async t => {
    dlg.querySelectorAll("[data-t]").forEach(b => b.classList.toggle("primary", b.dataset.t === t));
    const body = dlg.querySelector(".sheet-body");
    if (t === "resume") body.innerHTML = `<iframe src="${docFile(d, "html")}" title="Resume draft"></iframe>`;
    else {
      const r = await getJSON(`/api/file?path=${encodeURIComponent(d.path + "/notes.md")}`);
      body.innerHTML = `<div class="md">${md(r.content || "_No notes yet._")}</div>`;
    }
  };
  dlg.innerHTML = `<div class="sheet-head"><div>
      <h2>Resume draft · ${esc(j.title)} @ ${esc(j.company)}</h2>
      <div class="sheet-tabs">
        <button class="btn" data-t="resume">Resume</button><button class="btn" data-t="notes">What changed</button>
        <a class="btn" href="${docFile(d, "pdf")}" target="_blank" rel="noopener">PDF ↗</a>
        ${d.status === "draft" ? `<button class="btn" data-final>Mark as final</button>` : `<span class="status-pill">${esc(d.status)}</span>`}
      </div>
      <p class="small muted" style="margin:8px 0 0">To change it, tell Claude what you want: ${ask(`Revise my resume draft for ${shortTitle(j)}: `)}
        Files: <code>${esc(d.path)}/</code></p>
    </div><button class="btn" data-close>Close</button></div>
    <div class="sheet-body"></div>`;
  dlg.querySelectorAll("[data-t]").forEach(b => b.onclick = () => show(b.dataset.t));
  const fin = dlg.querySelector("[data-final]");
  if (fin) fin.onclick = async () => { await post("/api/documents/status", { job_id: jobId, kind: "resume", status: "final" }); dlg.close(); refreshJobs(); };
  showDialog(dlg);
  show(tab);
}

// ---------- Documents ----------
async function renderDocuments() {
  const v = $("view-documents");
  if (!docs) docs = await getJSON("/api/documents");
  const byJob = id => jobs.find(j => j.id === id);
  const pending = jobs.filter(j => ["interested", "applying"].includes(j.status) && !resumeDoc(j));
  const s = schedule("drafts_schedule");
  const row = d => {
    const j = byJob(d.job_id);
    return `<div class="doc"><div><div class="t">${esc(d.title)} · ${esc(d.company)}</div>
      <div class="s">${d.status === "draft" ? "Draft, waiting for your review" : esc(d.status)} · updated ${when(d.updated)}${d.summary ? ` · ${esc(d.summary)}` : ""}</div></div>
      <div class="btns">${j ? `<button class="btn primary" data-doc="${j.id}" data-tab="resume">View</button><button class="btn" data-doc="${j.id}" data-tab="notes">What changed</button>` : ""}
      <a class="btn" href="/files/${esc(d.path)}/${STYLE}.pdf" target="_blank" rel="noopener">PDF</a></div></div>`;
  };
  const resumes = docs.documents.filter(d => d.kind === "resume");
  v.innerHTML = `
    <div class="panel"><div class="panel-head"><h2>How drafts work</h2></div><div class="body small">
      <p>Mark a job <b>Interested</b> and the resume-drafts task tailors your base resume to it${s ? ` (next run ${soon(s.next)})` : " (not scheduled yet: see Setup)"}.
      Each draft comes with notes on what was emphasized, what was cut, and gaps to address. Drafts are a starting point: to change one,
      tell Claude what you want in any session, for example ${ask("Revise my resume draft for <company>: lead with platform work")}.
      Drafts never go anywhere by themselves. You review, download the PDF, and apply yourself.</p></div></div>
    <div class="panel"><div class="panel-head"><h2>Base resume</h2><span class="small muted">Source of truth · style: ${esc(docs.style)}</span></div>
      <div class="doc"><div><div class="t">profile/resume.json</div><div class="s">Every tailored draft starts here. Decisions about wording and framing live in resume-notes.md.</div></div>
      <div class="btns"><a class="btn primary" href="/files/${esc(docs.base.html)}" target="_blank" rel="noopener">View</a>
        <a class="btn" href="/files/${esc(docs.base.pdf)}" target="_blank" rel="noopener">PDF</a>
        <a class="btn" href="#profile/profile/resume-notes.md">Resume notes</a><a class="btn" href="#profile/profile/resume.json">Edit content</a></div></div></div>
    <div class="panel"><div class="panel-head"><h2>Tailored drafts</h2><span class="small muted">${resumes.length}</span></div>
      ${resumes.length ? resumes.map(row).join("") : `<div class="body muted small">None yet.</div>`}</div>
    ${pending.length ? `<div class="panel"><div class="panel-head"><h2>Queued</h2><span class="small muted">${s ? `next run ${soon(s.next)}` : ""}</span></div>
      ${pending.map(j => `<div class="doc"><div><div class="t">${esc(j.title)} · ${esc(j.company)}</div>
        <div class="s">Marked ${esc(j.status)}${j.status_changed ? " " + when(j.status_changed) : ""}</div></div>
        <div class="btns">${ask(`Draft a resume for ${shortTitle(j)}`)}</div></div>`).join("")}</div>` : ""}`;
  v.querySelectorAll("[data-doc]").forEach(b => b.onclick = () => openResume(+b.dataset.doc, b.dataset.tab));
}

// ---------- Profile (your files) ----------
let files = null, openFile = null, editing = false;
async function renderProfile() {
  const v = $("view-profile");
  if (!files) files = (await getJSON("/api/files")).files;
  const want = location.hash.split("/").slice(1).join("/");
  if (want && want !== openFile?.path) { openFile = await getJSON(`/api/file?path=${encodeURIComponent(want)}`); editing = false; }
  const groups = {};
  files.forEach(f => (groups[f.group] ||= []).push(f));
  const order = Object.keys(groups).sort((a, b) => (a === "profile" ? -1 : b === "profile" ? 1 : a.localeCompare(b)));
  v.innerHTML = `<div class="files">
    <nav class="panel filelist">${order.map(g => `<h4>${esc(g)}</h4>${groups[g].map(f =>
      `<button data-file="${esc(f.path)}" aria-current="${openFile?.path === f.path}">${esc(f.name)}</button>`).join("")}`).join("")}</nav>
    <div class="panel viewer">${openFile ? `
      <div class="panel-head"><h2>${esc(openFile.path)}</h2><div class="actions">${editing
        ? `<button class="btn primary" id="f-save">Save</button><button class="btn" id="f-cancel">Cancel</button>`
        : `<button class="btn" id="f-edit">Edit</button>`}</div></div>
      <div class="body">${editing ? `<textarea class="editor" id="f-text" spellcheck="true">${esc(openFile.content)}</textarea>
          <p class="small muted">Saved straight to the file. Or ask Claude to make the change for you.</p>`
        : openFile.path.endsWith(".md") ? `<div class="md">${md(openFile.content)}</div>`
        : `<pre class="md"><code>${esc(openFile.content)}</code></pre>`}</div>`
      : `<div class="body"><p class="muted">Your profile is the experience bank everything draws on: what you want (targets.md, search.md),
        your history (roles, bullet bank), and the decisions you've made (resume-notes.md). Pick a file to read it, or edit it here.
        You can also just ask Claude to update any of it.</p></div>`}</div></div>`;
  v.querySelectorAll("[data-file]").forEach(b => b.onclick = () => { location.hash = "profile/" + b.dataset.file; });
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on("f-edit", () => { editing = true; renderProfile(); });
  on("f-cancel", () => { editing = false; renderProfile(); });
  on("f-save", async () => {
    const content = $("f-text").value;
    try { await post("/api/file", { path: openFile.path, content }); openFile.content = content; editing = false; renderProfile(); }
    catch (e) { alert("Not saved: " + e.message); }
  });
}

// ---------- Activity (audit) ----------
let audit = { days: store.get("audit.days", 7), fate: store.get("audit.fate", "skipped"), q: "" }, auditData = null;
async function renderActivity() {
  const v = $("view-activity");
  auditData = await getJSON(`/api/audit?days=${audit.days}&decision=${audit.fate === "all" ? "" : audit.fate}`);
  const q = audit.q.toLowerCase();
  const items = auditData.items.filter(i => !q || `${i.title} ${i.company} ${i.reason || ""}`.toLowerCase().includes(q));
  const tot = auditData.per_day.reduce((t, d) => ({ seen: t.seen + d.seen, saved: t.saved + (d.saved || 0), skipped: t.skipped + (d.skipped || 0),
    rescued: t.rescued + (d.rescued || 0), waiting: t.waiting + (d.waiting || 0) }), { seen: 0, saved: 0, skipped: 0, rescued: 0, waiting: 0 });
  const fate = i => { const d = i.decision || "waiting"; return `<span class="fate ${d}">${{ saved: "kept", skipped: "filtered out", rescue: "rescued", waiting: "waiting" }[d] || d}</span>`; };
  const opt = (val, label, cur) => `<option value="${val}"${val == cur ? " selected" : ""}>${label}</option>`;
  v.innerHTML = `
    <div class="panel"><div class="panel-head"><h2>What the system looked at</h2><span class="small muted">last ${audit.days} days · new listings by the day they first appeared</span></div>
      <div class="body scroll"><table class="grid"><thead><tr><th>Day</th><th class="n">Found</th><th class="n">Kept</th><th class="n">Filtered out</th><th class="n">Rescued</th><th class="n">Waiting</th></tr></thead>
      <tbody>${auditData.per_day.map(d => `<tr><td>${esc(d.day)}</td><td class="n">${d.seen}</td><td class="n">${d.saved || 0}</td><td class="n">${d.skipped || 0}</td><td class="n">${d.rescued || 0}</td><td class="n">${d.waiting || 0}</td></tr>`).join("")}
      <tr><td><b>Total</b></td><td class="n"><b>${tot.seen}</b></td><td class="n"><b>${tot.saved}</b></td><td class="n"><b>${tot.skipped}</b></td><td class="n"><b>${tot.rescued}</b></td><td class="n"><b>${tot.waiting}</b></td></tr></tbody></table>
      <p class="small muted">Kept listings become jobs in your report (several listings can be the same job on different sites). Filtered-out ones were skipped by
      Claude with a reason. If one should have made it, <b>Rescue</b> it: the next review scores it and uses your note to tune what it keeps.</p></div></div>
    <div class="panel"><div class="panel-head"><h2>Listings</h2>
      <div class="controls"><select id="a-fate">${opt("skipped", "Filtered out", audit.fate)}${opt("saved", "Kept", audit.fate)}${opt("waiting", "Waiting for review", audit.fate)}${opt("rescue", "Rescued", audit.fate)}${opt("all", "All", audit.fate)}</select>
        <select id="a-days">${[7, 14, 30, 90].map(d => opt(d, `Last ${d} days`, audit.days)).join("")}</select>
        <input type="search" id="a-q" placeholder="Search…" value="${esc(audit.q)}"></div></div>
      <div class="body scroll"><table class="grid"><thead><tr><th>First seen</th><th>Listing</th><th>Found by</th><th>Outcome</th><th></th></tr></thead><tbody>
      ${items.map(i => `<tr><td>${esc(i.first_seen)}</td>
        <td>${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title || "?")}</a>` : esc(i.title || "?")}<div class="small muted">${esc(i.company || "")}${i.location ? " · " + esc(i.location) : ""}${i.salary_text ? " · " + esc(i.salary_text) : ""}</div></td>
        <td class="small muted">${esc(i.source)}${i.query ? `<div>${esc(i.query.replace(/^\w+: /, ""))}</div>` : ""}</td>
        <td>${fate(i)}${i.reason ? `<div class="small muted">${esc(i.reason)}</div>` : ""}${i.job_id ? `<div class="small"><a href="#jobs" data-jump="${i.job_id}">in your report</a></div>` : ""}</td>
        <td>${i.decision === "skipped" ? `<button class="btn" data-rescue="${esc(i.source)}|${esc(i.source_id)}">Rescue</button>` : ""}</td></tr>`).join("")
        || `<tr><td colspan="5" class="muted">Nothing here.</td></tr>`}
      </tbody></table></div></div>
    <div class="panel"><div class="panel-head"><h2>Runs</h2><span class="small muted">background collection and Claude's reviews</span></div>
      <div class="body scroll"><table class="grid"><thead><tr><th>Started</th><th>Kind</th><th>Status</th><th>Summary</th></tr></thead><tbody>
      ${runs.runs.map(r => `<tr><td>${when(r.started)}</td><td>${esc(r.kind)}</td><td>${esc(r.status)}</td><td class="small">${esc(r.summary || "")}</td></tr>`).join("")}
      </tbody></table></div></div>`;
  $("a-fate").onchange = e => { audit.fate = e.target.value; store.set("audit.fate", audit.fate); renderActivity(); };
  $("a-days").onchange = e => { audit.days = +e.target.value; store.set("audit.days", audit.days); renderActivity(); };
  $("a-q").oninput = e => { audit.q = e.target.value; clearTimeout(renderActivity.t); renderActivity.t = setTimeout(renderActivity, 250); };
  v.querySelectorAll("[data-rescue]").forEach(b => b.onclick = async () => {
    const note = prompt("Why should this have made the cut? (the next review uses this to tune what it keeps)");
    if (note === null) return;
    const [source, source_id] = b.dataset.rescue.split("|");
    await post("/api/seen/rescue", { source, source_id, note });
    renderActivity();
  });
}

// ---------- Setup ----------
function renderSetup() {
  const st = overview.setup, done = st.steps.filter(s => s.state === "done").length;
  const icon = { done: "✓", check: "!", todo: "" };
  const step = (s, n) => `<li class="step ${s.state}"><div class="dot">${icon[s.state] || n}</div><div>
      <h3>${esc(s.title)}${s.required ? "" : `<span class="tag">recommended</span>`}</h3>
      <p>${esc(s.what)}</p>
      ${s.state !== "done" ? ask(s.ask) : ""}
      <div class="meta">${[s.state === "check" ? "Marked done, but the check failed: " + s.detail : s.detail, s.note,
        s.at && s.state === "done" ? "checked off " + when(s.at) : ""].filter(Boolean).map(esc).join(" · ")}</div></div></li>`;
  $("view-setup").innerHTML = `
    <div class="panel"><div class="panel-head"><h2>${st.complete ? "Setup is complete" : st.ready ? "Ready to go, with a few optional steps left" : "Let's get you set up"}</h2>
      <span class="small muted">${done} of ${st.steps.length} done</span></div><div class="body">
      <p>This page is your window into a job search system that runs on your computer with Claude. Every day it finds new postings,
      researches and scores them against your background, and drafts tailored resumes for the jobs you mark Interested. It never applies or contacts anyone for you.</p>
      <p><b>Claude does the setup with you.</b> Open Claude (the desktop app's Code tab, or Claude Code) in this folder and say
      ${ask("Set this up for me.")} Claude follows <code>SETUP.md</code>, asks you questions, and checks off each step below only after it has verified it.
      Setup can take a few sessions; Claude picks up where you left off.</p></div></div>
    <div class="panel"><ul class="steps">${st.steps.map((s, n) => step(s, n + 1)).join("")}</ul></div>
    <div class="panel"><div class="panel-head"><h2>Schedules</h2></div><div class="body scroll">
      ${st.schedules.length ? `<table class="grid"><thead><tr><th>What</th><th>Runs</th><th>Next</th><th>Notes</th></tr></thead><tbody>
        ${st.schedules.map(s => `<tr><td>${esc(s.label)}</td><td class="small muted">${s.kind === "windows" ? "Windows Task Scheduler" : "Claude scheduled task"}${s.cron ? ` · <code>${esc(s.cron)}</code>` : ""}</td>
          <td>${s.next ? `${soon(s.next)}` : "—"}</td><td class="small muted">${esc(s.note || "")}</td></tr>`).join("")}</tbody></table>
        <p class="small muted">Claude scheduled tasks run while the Claude app is open (a missed run happens when it next opens), a few minutes after the time shown.</p>`
      : `<p class="muted small">Nothing is scheduled yet. The schedule steps above set these up.</p>`}</div></div>`;
}

loadAll();
