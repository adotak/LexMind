const $ = (sel) => document.querySelector(sel);
const EXAMPLES = [
  "Can police hold me without taking me to a magistrate?",
  "Is education free for children?",
  "Do I have a right to information?",
  "Can I be punished twice for the same crime?",
];

const DEBATE_EXAMPLES = [
  ["The police arrested my brother 3 days ago and still haven't taken him to a magistrate. That's illegal.", "He is being held for security reasons."],
  ["My 10-year-old sister's government school is charging fees, but education should be free.", ""],
  ["I have freedom of speech to criticise a minister online.", "Your post spreads hate and harms public order."],
];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Try again.");
  return body;
}

function citeLinks(text) {
  return esc(text).replace(/\[Art\.?\s*(\d{1,3}[A-Za-z]{0,3})\]/gi, (_, a) => `<a class="cite" href="#/article/${a.toUpperCase()}">Art. ${a.toUpperCase()}</a>`);
}

// [button label, search query]. Queries are tuned so each button finds its own articles (see tests/test_library.py).
const TOPICS = [
  ["Arrest", "arrest detention"],
  ["Fair trial", "fair trial"],
  ["Free speech", "speech"],
  ["Education", "education"],
  ["Property", "property"],
  ["Religion", "religion"],
  ["Privacy", "privacy"],
  ["Equality", "equality discrimination"],
  ["Elections", "elections"],
];
const TITLES = { ask: "Ask", debate: "Debate", library: "Constitution", about: "How it works" };
const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function paragraphs(text) {
  return text.split(/\n(?=\(|Provided|Explanation)/)
    .map((p) => `<p${/^(\(\w+\)\s*)?(Provided|Nothing in)/.test(p.trim()) ? ' class="limit"' : ""}>${esc(p)}</p>`).join("");
}

function skeleton(label, lines = 3) {
  const widths = ["w80", "", "w60", "w40"];
  return `<div class="card skel-card" role="status"><p class="status">${esc(label)}<span class="dots"></span></p>
    ${Array.from({ length: lines }, (_, i) => `<div class="skel ${widths[i % widths.length]}"></div>`).join("")}</div>`;
}

function errorCard(message, retryForm) {
  const retry = retryForm ? `<button type="button" class="btn ghost retry" data-form="${retryForm}">Try again</button>` : "";
  return `<div class="card err fade-in" role="alert"><p>${esc(message)}</p>${retry}</div>`;
}

function setBusy(btn, busy, label) {
  btn.disabled = busy;
  btn.setAttribute("aria-busy", String(busy));
  btn.textContent = label;
}

function reveal(el) {
  const top = el.getBoundingClientRect().top;
  if (top > window.innerHeight * 0.6) el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
}

function sourceItem(s, i) {
  return `<details class="fade-in"${i === 0 ? " open" : ""}>
    <summary><span><span class="n">Art. ${esc(s.article)}</span>${esc(s.title)}</span><small>${esc(s.chapter || "")}</small></summary>
    <p class="snippet">${esc(s.snippet)}</p>
    <a href="#/article/${esc(s.article)}">Read full article →</a>
  </details>`;
}

function renderAnswer(a) {
  const verified = a.citations.filter((c) => c.verified).length;
  const failed = a.citations.length - verified;
  const badges = a.mode === "ai"
    ? `<span class="badge ok">✓ ${verified} source${verified === 1 ? "" : "s"} verified</span>` +
      (failed ? `<span class="badge bad">✕ ${failed} citation${failed === 1 ? "" : "s"} rejected</span>` : "")
    : `<span class="badge warn">Search only, AI answers are off</span>`;
  const removed = a.removed.length
    ? `<details><summary><span>Removed by the Citation Checker (${a.removed.length})</span></summary>
         <ul class="removed">${a.removed.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></details>`
    : "";
  $("#answer").innerHTML = `
    <div class="card answer-card fade-in"><div class="meta">${badges}</div><div class="answer-text">${citeLinks(a.answer)}</div></div>
    ${removed}
    <div class="sec"><h2>Sources</h2><small>${a.sources.length} article${a.sources.length === 1 ? "" : "s"}</small></div>
    ${a.sources.map(sourceItem).join("") || '<p class="empty">No matching articles. Try different words, or browse the <a href="#/library">Constitution</a>.</p>'}
    <div class="note">${esc(a.disclaimer)}</div>`;
}

async function onAsk(e) {
  e.preventDefault();
  const question = $("#question").value.trim();
  if (question.length < 3) return;
  const btn = $("#ask-btn");
  setBusy(btn, true, "Thinking…");
  $("#ask-intro").hidden = true;
  $("#answer").innerHTML = skeleton("Reading the Constitution");
  try {
    renderAnswer(await api("/api/ask", { method: "POST", body: JSON.stringify({ question }) }));
  } catch (err) {
    $("#answer").innerHTML = errorCard(err.message, "ask-form");
  } finally {
    setBusy(btn, false, "Ask LexMind");
    reveal($("#answer"));
  }
}

function scorecard(d) {
  if (!d.verdict) {
    return `<div class="card fade-in"><div class="meta"><span class="badge warn">${d.mode === "ai" ? "No debate" : "Search only, AI debate is off"}</span></div><p>${esc(d.note)}</p></div>`;
  }
  const v = d.verdict;
  const lead = v.you > v.opponent ? "You're ahead" : v.you < v.opponent ? "The other side is ahead" : "It's a tie";
  const bar = (n, cls) => `<div class="bar"><span class="${cls}" data-w="${n * 10}"></span></div>`;
  return `<div class="card fade-in score">
    <div class="score-head"><b>${lead}</b><small>AI judge</small></div>
    <div class="score-row"><span>You</span>${bar(v.you, "you")}<b>${v.you}/10</b></div>
    <div class="score-row"><span>Other side</span>${bar(v.opponent, "opp")}<b>${v.opponent}/10</b></div>
    <p>${citeLinks(v.summary)}</p>
    <div class="meta"><span class="badge ok">✓ Your verified citations: ${d.law_backed.you || 0}</span><span class="badge bad">Their verified citations: ${d.law_backed.opponent || 0}</span></div>
  </div>`;
}

function roundItem(r, i) {
  const status = r.rebuttal ? '<small class="ok-text">answered</small>' : '<small class="bad-text">weak spot</small>';
  const removed = r.removed.length
    ? `<p class="removed-title">Removed by the Citation Checker</p><ul class="removed">${r.removed.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : "";
  return `<details class="fade-in"${i === 0 ? " open" : ""}>
    <summary><span><span class="n">Attack ${i + 1}</span>${esc(r.point)}</span>${status}</summary>
    <div class="side opp"><b>Other side</b><p>${citeLinks(r.attack)}</p></div>
    <div class="side you"><b>Your answer</b><p>${r.rebuttal ? citeLinks(r.rebuttal) : "LexMind found no answer to this in the Constitution. Prepare facts or other laws for it."}</p></div>
    ${removed}
  </details>`;
}

function renderDebate(d) {
  const weak = d.verdict && d.verdict.weak_spots.length
    ? `<div class="card weak fade-in"><h3 class="h-small">Prepare for these</h3><ul>${d.verdict.weak_spots.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>`
    : "";
  const limits = d.limits.length
    ? `<details><summary><span>Exceptions the other side can use (${d.limits.length})</span></summary>
        ${d.limits.map((l) => `<p class="snippet"><a class="cite" href="#/article/${esc(l.article)}">Art. ${esc(l.article)}</a> ${esc(l.text)}</p>`).join("")}</details>`
    : "";
  $("#debate").innerHTML = `
    ${scorecard(d)}
    ${d.rounds.length ? `<div class="sec"><h2>Attacks and your answers</h2><small>${d.rounds.filter((r) => r.rebuttal).length} of ${d.rounds.length} answered</small></div>${d.rounds.map(roundItem).join("")}` : ""}
    ${weak}
    ${limits}
    ${d.sources.length ? `<details><summary><span>Articles used (${d.sources.length})</span></summary>${d.sources.map((s) => sourceItem(s, 1)).join("")}</details>` : ""}
    <div class="note">${esc(d.disclaimer)}${d.verdict ? " " + esc(d.verdict.note) : ""}</div>`;
  // CSP blocks inline style attributes, so widths are set through the DOM.
  requestAnimationFrame(() => document.querySelectorAll(".bar span").forEach((b) => { b.style.width = `${b.dataset.w}%`; }));
}

async function onDebate(e) {
  e.preventDefault();
  const position = $("#position").value.trim();
  if (position.length < 10) return;
  const btn = $("#debate-btn");
  setBusy(btn, true, "Debating…");
  $("#debate-intro").hidden = true;
  $("#debate").innerHTML = skeleton("The opponent is preparing attacks", 4);
  try {
    renderDebate(await api("/api/debate", { method: "POST", body: JSON.stringify({ position, opponent: $("#opp").value.trim() }) }));
  } catch (err) {
    $("#debate").innerHTML = errorCard(err.message, "debate-form");
  } finally {
    setBusy(btn, false, "Start debate");
    reveal($("#debate"));
  }
}

let outline = null;
let order = [];
async function loadOutline() {
  if (outline) return outline;
  const lib = await api("/api/library");
  outline = lib.outline;
  order = outline.flatMap((p) => p.chapters.flatMap((c) => c.articles));
  $("#lib-source").innerHTML = `${esc(lib.source_name)}. <a href="${esc(lib.source_url)}" target="_blank" rel="noopener">Official PDF ↗</a>`;
  return outline;
}

let libraryLoading = false;
async function showLibrary() {
  if (libraryLoading || $("#outline details")) return;
  libraryLoading = true;
  $("#outline").innerHTML = skeleton("Loading the Constitution", 4);
  try {
    await loadOutline();
    $("#outline").innerHTML = outline.map((p) => `
      <details><summary><span>${esc(p.part)}</span><small>${p.chapters.reduce((n, c) => n + c.articles.length, 0)} articles</small></summary>
        ${p.chapters.map((c) => `${c.chapter ? `<h4>${esc(c.chapter)}</h4>` : ""}<div class="list">${c.articles.map((a) =>
          `<a href="#/article/${esc(a.article)}"><b>${esc(a.article)}</b>${esc(a.title)}</a>`).join("")}</div>`).join("")}
      </details>`).join("");
  } catch (err) {
    $("#outline").innerHTML = errorCard(err.message);
  } finally {
    libraryLoading = false;
  }
}

let filterTimer;
function onFilter() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(async () => {
    const q = $("#lib-filter").value.trim();
    $("#outline").hidden = q.length >= 2;
    document.querySelectorAll("#topics .chip").forEach((c) => c.classList.toggle("on", c.dataset.q === q.toLowerCase()));
    if (q.length < 2) { $("#lib-results").innerHTML = ""; return; }
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(q)}&limit=10`);
      if (q !== $("#lib-filter").value.trim()) return;
      $("#lib-results").innerHTML = hits.length
        ? `<p class="count">${hits.length === 10 ? "Top 10" : hits.length} matching article${hits.length === 1 ? "" : "s"}</p>${hits.map(sourceItem).join("")}`
        : `<p class="empty">No articles match “${esc(q)}”. Try a simpler word, like “arrest” or “school”.</p>`;
    } catch (err) {
      $("#lib-results").innerHTML = errorCard(err.message);
    }
  }, 250);
}

async function showArticle(num) {
  const view = $("#article-view");
  view.innerHTML = skeleton("Loading the article", 6);
  try {
    const a = await api(`/api/articles/${encodeURIComponent(num)}`);
    document.title = `Article ${a.article}: ${a.title} · LexMind`;
    view.innerHTML = `<h1 class="art-title" tabindex="-1"><span>Article ${esc(a.article)}.</span> ${esc(a.title)}</h1>
      <div class="art-meta">${esc(a.part)}${a.chapter ? " · " + esc(a.chapter) : ""} · page ${a.page} of the official text</div>
      <div class="art-actions"><button type="button" class="btn ghost" id="ask-about" data-article="${esc(a.article)}">Ask about this article</button></div>
      <div class="card art-text">${paragraphs(a.text)}</div>
      <nav class="art-nav" aria-label="Nearby articles"></nav>`;
    await loadOutline().catch(() => null);
    const i = order.findIndex((x) => x.article === a.article);
    const link = (x, cls, label) => x ? `<a class="${cls}" href="#/article/${esc(x.article)}"><small>${label}</small><span>Art. ${esc(x.article)} · ${esc(x.title)}</span></a>` : "";
    if (i >= 0) view.querySelector(".art-nav").innerHTML = link(order[i - 1], "prev", "← Previous") + link(order[i + 1], "next", "Next →");
  } catch (err) {
    document.title = "Article not found · LexMind";
    view.innerHTML = `<h1 class="art-title" tabindex="-1">Article ${esc(num)}</h1>${errorCard(err.message)}<p class="empty">Browse <a href="#/library">all articles</a> or search for a topic.</p>`;
  }
}

function route() {
  const [, page = "ask", arg] = (location.hash || "#/ask").split("/");
  const id = { ask: "ask", debate: "debate", library: "library", article: "article", about: "about" }[page] || "ask";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `page-${id}`; });
  const current = id === "article" ? "library" : id;
  document.querySelectorAll(".top nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === current);
    if (a.dataset.route === current) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  if (id !== "article") document.title = id === "ask" ? "LexMind — Know your rights under the Constitution of Pakistan" : `${TITLES[id]} · LexMind`;
  if (id === "library") showLibrary();
  if (id === "article" && arg) showArticle(decodeURIComponent(arg));
  window.scrollTo(0, 0);
}

function onRouteChange() {
  route();
  // Move keyboard and screen-reader focus to the new page, like a real page load.
  const h1 = document.querySelector(".page:not([hidden]) h1");
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
}

$("#examples").innerHTML = EXAMPLES.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
$("#examples").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) { $("#question").value = chip.textContent; $("#ask-form").requestSubmit(); }
});
$("#ask-form").addEventListener("submit", onAsk);
$("#debate-examples").innerHTML = DEBATE_EXAMPLES.map(([p], i) => `<button type="button" class="chip" data-i="${i}">${esc(p.length > 48 ? p.slice(0, 46) + "…" : p)}</button>`).join("");
$("#debate-examples").addEventListener("click", (e) => {
  const i = e.target.closest(".chip")?.dataset.i;
  if (i === undefined) return;
  [$("#position").value, $("#opp").value] = DEBATE_EXAMPLES[i];
  $("#debate-form").requestSubmit();
});
$("#debate-form").addEventListener("submit", onDebate);
const submitOnCtrlEnter = (form) => (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); form.requestSubmit(); } };
$("#question").addEventListener("keydown", submitOnCtrlEnter($("#ask-form")));
$("#position").addEventListener("keydown", submitOnCtrlEnter($("#debate-form")));
$("#opp").addEventListener("keydown", submitOnCtrlEnter($("#debate-form")));
$("#lib-filter").addEventListener("input", onFilter);
$("#topics").innerHTML = TOPICS.map(([label, q]) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(label)}</button>`).join("");
$("#topics").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  $("#lib-filter").value = chip.classList.contains("on") ? "" : chip.dataset.q;
  onFilter();
});
document.addEventListener("click", (e) => {
  const retry = e.target.closest(".retry");
  if (retry) document.getElementById(retry.dataset.form).requestSubmit();
  const about = e.target.closest("#ask-about");
  if (about) {
    $("#question").value = `What does Article ${about.dataset.article} say, in simple words?`;
    location.hash = "#/ask";
    $("#ask-form").requestSubmit();
  }
});
window.addEventListener("hashchange", onRouteChange);
route();
