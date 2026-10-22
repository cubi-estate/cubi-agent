// Cubi Agent page: streams one turn at a time from POST /api/chat (NDJSON).
// No framework, no build step. Every string from the server is escaped before
// it touches the DOM; the small markdown renderer only creates <b>, <i>, <a
// href="http(s)…">, lists and paragraphs.
"use strict";

const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const tpl = document.getElementById("tpl-turn");
let sessionId = null;
let busy = false;

const T = {
  en: { open: "Open listing", ask: "Ask Cubi", updated: "Updated", bd: "bd", ba: "ba",
        price: n => `Is #${n}'s price in line with similar homes?`, contact: n => `How do I contact the agent for #${n}?`,
        steps: (n, s) => `${n} step${n === 1 ? "" : "s"} · ${s}s`, searched: "Search", none: "No homes matched.",
        within: c => `Asking price up to ${c}`, of: (a, b) => `${a} of ${b} listings`, was: (p, c) => `${p}% at ${c}`, note: "Share of each city's listed homes of this kind on Cubi, by asking price — not sale prices. Counts show Cubi's coverage, not market size.", na: "not available right now", more: c => `And up to ${c}?` },
  pt: { open: "Ver anúncio", ask: "Perguntar à Cubi", updated: "Atualizado", bd: "qt", ba: "wc",
        price: n => `O preço do #${n} está em linha com casas semelhantes?`, contact: n => `Como contacto o agente do #${n}?`,
        steps: (n, s) => `${n} passo${n === 1 ? "" : "s"} · ${s}s`, searched: "Pesquisa", none: "Nenhuma casa encontrada.",
        within: c => `Preço pedido até ${c}`, of: (a, b) => `${a} de ${b} anúncios`, was: (p, c) => `${p}% até ${c}`, note: "Percentagem dos anúncios deste tipo na Cubi em cada cidade, por preço pedido — não preços de venda. As contagens refletem a cobertura da Cubi, não o tamanho do mercado.", na: "indisponível de momento", more: c => `E até ${c}?` },
  es: { open: "Ver anuncio", ask: "Preguntar a Cubi", updated: "Actualizado", bd: "hab", ba: "baños",
        price: n => `¿El precio del #${n} está en línea con viviendas similares?`, contact: n => `¿Cómo contacto con el agente del #${n}?`,
        steps: (n, s) => `${n} paso${n === 1 ? "" : "s"} · ${s}s`, searched: "Búsqueda", none: "Ninguna vivienda encontrada.",
        within: c => `Precio de oferta hasta ${c}`, of: (a, b) => `${a} de ${b} anuncios`, was: (p, c) => `${p}% hasta ${c}`, note: "Porcentaje de los anuncios de este tipo en Cubi en cada ciudad, por precio de oferta — no precios de venta. Los recuentos reflejan la cobertura de Cubi, no el tamaño del mercado.", na: "no disponible ahora", more: c => `¿Y hasta ${c}?` },
  fr: { open: "Voir l'annonce", ask: "Demander à Cubi", updated: "Mis à jour", bd: "ch", ba: "sdb",
        price: n => `Le prix du n°${n} est-il cohérent avec des biens similaires ?`, contact: n => `Comment contacter l'agent du n°${n} ?`,
        steps: (n, s) => `${n} étape${n === 1 ? "" : "s"} · ${s}s`, searched: "Recherche", none: "Aucun bien trouvé.",
        within: c => `Prix demandé jusqu'à ${c}`, of: (a, b) => `${a} sur ${b} annonces`, was: (p, c) => `${p} % jusqu'à ${c}`, note: "Part des annonces de ce type sur Cubi dans chaque ville, selon le prix demandé — pas les prix de vente. Les nombres reflètent la couverture de Cubi, pas la taille du marché.", na: "indisponible pour le moment", more: c => `Et jusqu'à ${c} ?` },
  de: { open: "Inserat öffnen", ask: "Cubi fragen", updated: "Aktualisiert", bd: "Schlafz.", ba: "Bad",
        price: n => `Liegt der Preis von #${n} im Rahmen ähnlicher Objekte?`, contact: n => `Wie erreiche ich den Makler von #${n}?`,
        steps: (n, s) => `${n} Schritt${n === 1 ? "" : "e"} · ${s}s`, searched: "Suche", none: "Keine passenden Objekte.",
        within: c => `Angebotspreis bis ${c}`, of: (a, b) => `${a} von ${b} Inseraten`, was: (p, c) => `${p} % bis ${c}`, note: "Anteil der Inserate dieser Art auf Cubi je Stadt, nach Angebotspreis — keine Verkaufspreise. Die Anzahlen zeigen Cubis Abdeckung, nicht die Marktgröße.", na: "gerade nicht verfügbar", more: c => `Und bis ${c}?` },
  nl: { open: "Advertentie openen", ask: "Vraag het Cubi", updated: "Bijgewerkt", bd: "slpk", ba: "badk",
        price: n => `Ligt de prijs van #${n} in lijn met vergelijkbare woningen?`, contact: n => `Hoe bereik ik de makelaar van #${n}?`,
        steps: (n, s) => `${n} stap${n === 1 ? "" : "pen"} · ${s}s`, searched: "Zoekopdracht", none: "Geen woningen gevonden.",
        within: c => `Vraagprijs tot ${c}`, of: (a, b) => `${a} van ${b} advertenties`, was: (p, c) => `${p}% tot ${c}`, note: "Aandeel van de advertenties van dit type op Cubi per stad, naar vraagprijs — geen verkoopprijzen. De aantallen tonen Cubi's dekking, niet de omvang van de markt.", na: "nu niet beschikbaar", more: c => `En tot ${c}?` },
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function safeUrl(u) {
  try { const x = new URL(u); return x.protocol === "https:" || x.protocol === "http:" ? x.href : null; }
  catch { return null; }
}

// Inline markdown on already-escaped text.
function inline(s) {
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, text, url) => {
    const u = safeUrl(url.replace(/&amp;/g, "&"));
    return u ? `<a href="${esc(u)}" target="_blank" rel="noopener nofollow">${text}</a>` : text;
  });
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (m, pre, url) => {
    const u = safeUrl(url.replace(/&amp;/g, "&"));
    return u ? `${pre}<a href="${esc(u)}" target="_blank" rel="noopener nofollow">${esc(new URL(u).hostname)}</a>` : m;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  s = s.replace(/(^|[\s(])[_*]([^_*\n]+)[_*](?=[\s).,;:!?]|$)/g, "$1<i>$2</i>");
  return s;
}

function markdown(text) {
  const lines = esc(text).split("\n");
  let html = "", list = null, para = [];
  const flushPara = () => { if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; } };
  const flushList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const ul = line.match(/^\s*[-*•]\s+(.*)$/), ol = line.match(/^\s*\d+[.)]\s+(.*)$/), h = line.match(/^#{1,4}\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const kind = ul ? "ul" : "ol";
      if (list !== kind) { flushList(); html += `<${kind}>`; list = kind; }
      html += `<li>${inline((ul || ol)[1])}</li>`;
    } else if (h) {
      flushPara(); flushList(); html += `<h4>${inline(h[1])}</h4>`;
    } else if (!line.trim()) {
      flushPara(); flushList();
    } else if (list && /^\s{2,}/.test(raw)) {
      html = html.replace(/<\/li>$/, ` ${inline(line.trim())}</li>`);
    } else {
      flushList(); para.push(line.trim());
    }
  }
  flushPara(); flushList();
  return html;
}

function places(location) {
  // Mirrors agent/listings.places: drop the street part, keep two place names.
  const parts = String(location || "").split(",").map(s => s.trim()).filter(Boolean);
  let last = -1;
  parts.forEach((p, i) => { if (/\d/.test(p)) last = i; });
  return parts.slice(last + 1).slice(0, 2).join(", ");
}

function card(c, t) {
  const el = document.createElement("div");
  el.className = "card";
  const facts = [];
  if (c.bedrooms != null) facts.push(`${Math.round(c.bedrooms)} ${t.bd}`);
  if (c.bathrooms != null) facts.push(`${Math.round(c.bathrooms)} ${t.ba}`);
  if (c.living_area != null) facts.push(`${Math.round(c.living_area)} m²`);
  const open = safeUrl(c.url), ask = safeUrl(c.ask_url);
  el.innerHTML = `
    <div class="row1"><span class="price">${esc(c.price_text || "—")}</span><span class="n">#${esc(c.n)}</span></div>
    <div class="what">${esc(c.type || "Home")}</div>
    <div class="where">${esc(places(c.location))}</div>
    ${facts.length ? `<div class="facts">${esc(facts.join(" · "))}</div>` : ""}
    ${(c.tags || []).length ? `<div class="tags">${c.tags.slice(0, 3).map(x => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
    ${c.updated ? `<div class="updated">${esc(t.updated)} ${esc(c.updated)}</div>` : ""}
    <div class="links">
      ${open ? `<a class="open" href="${esc(open)}" target="_blank" rel="noopener">${esc(t.open)}</a>` : ""}
      ${ask ? `<a class="ask" href="${esc(ask)}" target="_blank" rel="noopener">${esc(t.ask)}</a>` : ""}
    </div>`;
  return el;
}

function euro(n, lang) {
  return "€" + Math.round(Number(n) || 0).toLocaleString(lang || "en").replace(/,/g, "\u202f");
}

// The budget comparison: one bar per city, the share of its priced listings
// within the cap; after a budget change, a marker at the earlier share.
function budget(el, b, t, lang) {
  const pct = v => Math.max(0, Math.min(100, Number(v) || 0));
  const rows = (b.rows || []).map(r => {
    if (r.error || r.share_pct == null) {
      return `<div class="brow"><div class="bplace">${esc(r.place)}</div><div class="bval na">${esc(t.na)}</div></div>`;
    }
    const prev = r.previous_pct != null && b.previous_max_price
      ? `<div class="bprev" style="left:${pct(r.previous_pct)}%"></div>` : "";
    const was = prev ? `<span class="bwas">${esc(t.was(r.previous_pct, euro(b.previous_max_price, lang)))}</span>` : "";
    return `<div class="brow">
      <div class="bplace">${esc(r.place)}</div>
      <div class="btrack"><div class="bfill" data-w="${pct(r.share_pct)}"
        style="width:${prev ? pct(r.previous_pct) : 0}%"></div>${prev}</div>
      <div class="bval"><b>${esc(r.share_pct)}%</b> <span>${esc(t.of(r.within, r.of))}</span> ${was}</div>
    </div>`;
  }).join("");
  el.innerHTML = `<div class="bhead">${esc(t.within(euro(b.max_price, lang)))}</div>${rows}
    <div class="bnote">${esc(t.note)}${b.as_of ? ` · ${esc(String(b.as_of).slice(0, 10))}` : ""}</div>`;
  el.hidden = false;
  // Grow from zero, or after a budget change from the earlier share, so the
  // change itself is what moves.
  requestAnimationFrame(() => requestAnimationFrame(() =>
    el.querySelectorAll(".bfill").forEach(f => { f.style.width = f.dataset.w + "%"; })));
}

function followups(box, t, n) {
  for (const text of [t.price(n), t.contact(n)]) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", () => ask(text));
    box.appendChild(b);
  }
}

function scrollDown() { window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); }

async function ask(text) {
  if (busy || !text.trim()) return;
  busy = true; send.disabled = true;
  document.getElementById("empty")?.remove();
  document.querySelectorAll(".followups").forEach(f => f.replaceChildren());

  const turn = tpl.content.firstElementChild.cloneNode(true);
  turn.querySelector(".bubble.user").textContent = text;
  const steps = turn.querySelector(".steps"), stepList = steps.querySelector("ol"), label = steps.querySelector(".label");
  const bot = turn.querySelector(".bubble.bot"), filter = turn.querySelector(".filter");
  const cards = turn.querySelector(".cards"), fups = turn.querySelector(".followups");
  log.appendChild(turn);
  scrollDown();

  const t0 = performance.now();
  let nSteps = 0, gotAnswer = false;
  const step = s => { const li = document.createElement("li"); li.textContent = s; stepList.appendChild(li); nSteps++; };
  const fail = msg => { bot.hidden = false; bot.className = "bubble error"; bot.textContent = msg; };

  try {
    const res = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "session") sessionId = ev.id;
        else if (ev.type === "action") { step(ev.text); label.textContent = ev.text; }
        else if (ev.type === "error") fail(ev.text);
        else if (ev.type === "answer") {
          gotAnswer = true;
          const t = T[ev.lang] || T.en;
          document.documentElement.lang = ev.lang || "en";
          bot.hidden = false;
          bot.innerHTML = markdown(ev.text || t.none);
          if (ev.filter && ev.listings && ev.listings.length) {
            filter.hidden = false;
            filter.innerHTML = `${esc(t.searched)}: <b>${esc(ev.filter)}</b>`;
          }
          if (ev.inventory) {
            budget(turn.querySelector(".budget"), ev.inventory, t, ev.lang);
            const next = (Number(ev.inventory.max_price) || 0) + 100000;
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = t.more(euro(next, ev.lang));
            b.addEventListener("click", () => ask(b.textContent));
            fups.appendChild(b);
          }
          (ev.listings || []).forEach(c => cards.appendChild(card(c, t)));
          if ((ev.listings || []).length) followups(fups, t, 1);
          label.textContent = t.steps(nSteps, ev.latency_s ?? ((performance.now() - t0) / 1000).toFixed(1));
        }
        scrollDown();
      }
    }
    if (!gotAnswer && bot.hidden) fail("No answer came back. Try again in a moment.");
  } catch (e) {
    fail("Couldn't reach the agent. Check your connection and try again.");
  } finally {
    steps.classList.add("done");
    if (gotAnswer) steps.open = false;
    if (!gotAnswer && label.textContent === "Working…") label.textContent = "Stopped";
    busy = false; send.disabled = false; input.focus();
    scrollDown();
  }
}

form.addEventListener("submit", e => {
  e.preventDefault();
  const text = input.value; input.value = ""; input.style.height = "";
  ask(text);
});
input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
});
input.addEventListener("input", () => { input.style.height = ""; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
document.getElementById("examples")?.addEventListener("click", e => {
  if (e.target.closest("button")) ask(e.target.closest("button").textContent);
});
document.getElementById("new").addEventListener("click", () => {
  if (sessionId) fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId }) });
  sessionId = null;
  location.reload();
});
