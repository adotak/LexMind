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

function paragraphs(text) {
  return text.split(/\n(?=\(|Provided|Explanation)/).map((p) => `<p>${esc(p)}</p>`).join("");
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
    <div class="card fade-in"><div class="meta">${badges}</div><div class="answer-text">${citeLinks(a.answer)}</div></div>
    ${removed}
    <h3>Sources</h3>
    ${a.sources.map(sourceItem).join("") || '<p class="loading">No matching articles.</p>'}
    <div class="note">${esc(a.disclaimer)}</div>`;
}

async function onAsk(e) {
  e.preventDefault();
  const question = $("#question").value.trim();
  if (question.length < 3) return;
  const btn = $("#ask-btn");
  btn.disabled = true;
  $("#answer").innerHTML = `<p class="loading">Reading the Constitution<span class="dots"></span></p>`;
  try {
    renderAnswer(await api("/api/ask", { method: "POST", body: JSON.stringify({ question }) }));
  } catch (err) {
    $("#answer").innerHTML = `<div class="card"><span class="badge bad">${esc(err.message)}</span></div>`;
  } finally {
    btn.disabled = false;
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
    ? `<div class="card fade-in"><h3 class="h-small">Prepare for these</h3><ul>${d.verdict.weak_spots.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>`
    : "";
  const limits = d.limits.length
    ? `<details><summary><span>Exceptions the other side can use (${d.limits.length})</span></summary>
        ${d.limits.map((l) => `<p class="snippet"><a class="cite" href="#/article/${esc(l.article)}">Art. ${esc(l.article)}</a> ${esc(l.text)}</p>`).join("")}</details>`
    : "";
  $("#debate").innerHTML = `
    ${scorecard(d)}
    ${d.rounds.length ? `<h3>Attacks and your answers</h3>${d.rounds.map(roundItem).join("")}` : ""}
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
  btn.disabled = true;
  $("#debate").innerHTML = `<p class="loading">Opponent is preparing attacks<span class="dots"></span></p>`;
  try {
    renderDebate(await api("/api/debate", { method: "POST", body: JSON.stringify({ position, opponent: $("#opp").value.trim() }) }));
  } catch (err) {
    $("#debate").innerHTML = `<div class="card"><span class="badge bad">${esc(err.message)}</span></div>`;
  } finally {
    btn.disabled = false;
  }
}

let outline = null;
async function showLibrary() {
  if (!outline) {
    const lib = await api("/api/library");
    outline = lib.outline;
    $("#lib-source").innerHTML = `${esc(lib.source_name)}. <a href="${esc(lib.source_url)}" target="_blank" rel="noopener">Official PDF</a>`;
    $("#outline").innerHTML = outline.map((p) => `
      <details><summary><span>${esc(p.part)}</span><small>${p.chapters.reduce((n, c) => n + c.articles.length, 0)} articles</small></summary>
        ${p.chapters.map((c) => `${c.chapter ? `<h4>${esc(c.chapter)}</h4>` : ""}<div class="list">${c.articles.map((a) =>
          `<a href="#/article/${esc(a.article)}"><b>${esc(a.article)}</b>${esc(a.title)}</a>`).join("")}</div>`).join("")}
      </details>`).join("");
  }
}

let filterTimer;
function onFilter() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(async () => {
    const q = $("#lib-filter").value.trim();
    $("#outline").hidden = q.length >= 2;
    if (q.length < 2) { $("#lib-results").innerHTML = ""; return; }
    const hits = await api(`/api/search?q=${encodeURIComponent(q)}&limit=10`);
    $("#lib-results").innerHTML = hits.map(sourceItem).join("") || '<p class="loading">No matching articles.</p>';
  }, 250);
}

async function showArticle(num) {
  const view = $("#article-view");
  view.innerHTML = `<p class="loading">Loading<span class="dots"></span></p>`;
  try {
    const a = await api(`/api/articles/${encodeURIComponent(num)}`);
    view.innerHTML = `<h1 class="art-title">Article ${esc(a.article)}. ${esc(a.title)}</h1>
      <div class="art-meta">${esc(a.part)}${a.chapter ? " · " + esc(a.chapter) : ""} · page ${a.page} of the official text</div>
      <div class="card art-text">${paragraphs(a.text)}</div>`;
  } catch (err) {
    view.innerHTML = `<div class="card"><span class="badge bad">${esc(err.message)}</span></div>`;
  }
}

function route() {
  const [, page = "ask", arg] = (location.hash || "#/ask").split("/");
  const id = { ask: "ask", debate: "debate", library: "library", article: "article", about: "about" }[page] || "ask";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `page-${id}`; });
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === (id === "article" ? "library" : id)));
  if (id === "library") showLibrary();
  if (id === "article" && arg) showArticle(decodeURIComponent(arg));
  window.scrollTo(0, 0);
}

$("#examples").innerHTML = EXAMPLES.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
$("#examples").addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) { $("#question").value = e.target.textContent; $("#ask-form").requestSubmit(); }
});
$("#ask-form").addEventListener("submit", onAsk);
$("#debate-examples").innerHTML = DEBATE_EXAMPLES.map(([p], i) => `<button type="button" class="chip" data-i="${i}">${esc(p.length > 48 ? p.slice(0, 46) + "…" : p)}</button>`).join("");
$("#debate-examples").addEventListener("click", (e) => {
  const i = e.target.dataset.i;
  if (i === undefined) return;
  [$("#position").value, $("#opp").value] = DEBATE_EXAMPLES[i];
  $("#debate-form").requestSubmit();
});
$("#debate-form").addEventListener("submit", onDebate);
$("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#ask-form").requestSubmit(); });
$("#lib-filter").addEventListener("input", onFilter);
window.addEventListener("hashchange", route);
route();
