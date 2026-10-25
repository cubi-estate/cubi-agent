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
    const ul = line.match(/^\s*[-*•]\s+(.*)$/), ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/), h = line.match(/^#{1,4}\s+(.*)$/);
    if (ul && list === "ol" && /^\s{2,}/.test(raw)) {
      // An indented bullet under a numbered item belongs inside that item.
      const item = `<li>${inline(ul[1])}</li>`;
      html = html.endsWith("</ul></li>") ? html.slice(0, -10) + item + "</ul></li>"
                                         : html.replace(/<\/li>$/, `<ul>${item}</ul></li>`);
    } else if (ul || ol) {
      flushPara();
      const kind = ul ? "ul" : "ol";
      // Keep the model's own number: a list split by bullets or blank lines
      // otherwise restarts at 1 ("1. … 1. … 1.", live 2026-10-22).
      if (list !== kind) { flushList(); html += kind === "ol" ? `<ol start="${Number(ol[1])}">` : "<ul>"; list = kind; }
      html += `<li>${inline(ul ? ul[1] : ol[2])}</li>`;
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

// Labels for the side-by-side table. Row keys match agent/similar.py.
const SIM = {
  en: { home: "This home", in: c => `In ${c}`, price: "Asking price", m2: "€/m²", area: "Living area", rooms: "Bedrooms · bathrooms",
        features: "Stated in the listing", env: "Surroundings (area data)", minutes: "Minutes away", climate: "Regional climate",
        legend: "✓ stated · – not stated (the listing doesn't say; not a “no”) · ? no reading. Matched on the home, never on price. Asking prices, not valuations.",
        none: c => `No listing in ${c} with the same bedrooms and a similar size.`,
        f: { balcony: "Balcony", terrace: "Terrace", lift: "Lift", parking: "Parking", air_conditioning: "Air conditioning", garden: "Garden", pool: "Pool", camp_site_nearby: "Campsite nearby" },
        e: { quiet: "Quiet (road/rail < 65 dB)", clean_air: "Clean air (PM2.5 ≤ 15)", leafy: "Leafy", coastal: "Within 5 km of the coast", flood_safe: "Outside river-flood zones", wildfire_safer: "Lower wildfire weather", seismic_safer: "Lower seismic hazard", stable_ground: "Stable ground" },
        m: { "walk_time.metro_station": "Walk to metro", "walk_time.railway_station": "Walk to train", "walk_time.supermarket": "Walk to supermarket", "walk_time.school": "Walk to school", "walk_time.park": "Walk to a park", "drive_time.coast": "Drive to the coast", "drive_time.airport": "Drive to the airport" },
        c: { sunshine_hours: "Sunshine, h/yr", sea_temp_summer_c: "Sea in summer, °C", summer_max_c: "Summer high, °C", winter_min_c: "Winter low, °C" } },
  pt: { home: "Esta casa", in: c => `Em ${c}`, price: "Preço pedido", m2: "€/m²", area: "Área útil", rooms: "Quartos · WC",
        features: "Indicado no anúncio", env: "Envolvente (dados da zona)", minutes: "Minutos", climate: "Clima regional",
        legend: "✓ indicado · – não indicado (o anúncio não diz; não é um “não”) · ? sem dados. Escolhidas pela casa, nunca pelo preço. Preços pedidos, não avaliações.",
        none: c => `Nenhum anúncio em ${c} com os mesmos quartos e área semelhante.`,
        f: { balcony: "Varanda", terrace: "Terraço", lift: "Elevador", parking: "Estacionamento", air_conditioning: "Ar condicionado", garden: "Jardim", pool: "Piscina", camp_site_nearby: "Parque de campismo perto" },
        e: { quiet: "Sossegado (estrada/ferrovia < 65 dB)", clean_air: "Ar limpo (PM2.5 ≤ 15)", leafy: "Arborizado", coastal: "A ≤ 5 km da costa", flood_safe: "Fora de zonas de cheia", wildfire_safer: "Menos risco meteorológico de incêndio", seismic_safer: "Menor perigo sísmico", stable_ground: "Solo estável" },
        m: { "walk_time.metro_station": "A pé até ao metro", "walk_time.railway_station": "A pé até ao comboio", "walk_time.supermarket": "A pé até ao supermercado", "walk_time.school": "A pé até à escola", "walk_time.park": "A pé até um parque", "drive_time.coast": "De carro até à costa", "drive_time.airport": "De carro até ao aeroporto" },
        c: { sunshine_hours: "Sol, h/ano", sea_temp_summer_c: "Mar no verão, °C", summer_max_c: "Máx. de verão, °C", winter_min_c: "Mín. de inverno, °C" } },
  es: { home: "Esta vivienda", in: c => `En ${c}`, price: "Precio de oferta", m2: "€/m²", area: "Superficie", rooms: "Dormitorios · baños",
        features: "Indicado en el anuncio", env: "Entorno (datos de zona)", minutes: "Minutos", climate: "Clima regional",
        legend: "✓ indicado · – no indicado (el anuncio no lo dice; no es un “no”) · ? sin datos. Elegidas por la vivienda, nunca por el precio. Precios de oferta, no tasaciones.",
        none: c => `Ningún anuncio en ${c} con los mismos dormitorios y una superficie similar.`,
        f: { balcony: "Balcón", terrace: "Terraza", lift: "Ascensor", parking: "Garaje", air_conditioning: "Aire acondicionado", garden: "Jardín", pool: "Piscina", camp_site_nearby: "Camping cerca" },
        e: { quiet: "Tranquilo (carretera/tren < 65 dB)", clean_air: "Aire limpio (PM2.5 ≤ 15)", leafy: "Arbolado", coastal: "A ≤ 5 km de la costa", flood_safe: "Fuera de zonas inundables", wildfire_safer: "Menor riesgo meteorológico de incendio", seismic_safer: "Menor peligro sísmico", stable_ground: "Terreno estable" },
        m: { "walk_time.metro_station": "A pie al metro", "walk_time.railway_station": "A pie al tren", "walk_time.supermarket": "A pie al supermercado", "walk_time.school": "A pie al colegio", "walk_time.park": "A pie a un parque", "drive_time.coast": "En coche a la costa", "drive_time.airport": "En coche al aeropuerto" },
        c: { sunshine_hours: "Sol, h/año", sea_temp_summer_c: "Mar en verano, °C", summer_max_c: "Máx. de verano, °C", winter_min_c: "Mín. de invierno, °C" } },
  fr: { home: "Ce bien", in: c => `À ${c}`, price: "Prix demandé", m2: "€/m²", area: "Surface", rooms: "Chambres · sdb",
        features: "Indiqué dans l'annonce", env: "Environnement (données de zone)", minutes: "Minutes", climate: "Climat régional",
        legend: "✓ indiqué · – non indiqué (l'annonce ne le dit pas ; pas un « non ») · ? pas de donnée. Choisis sur le bien, jamais sur le prix. Prix demandés, pas des estimations.",
        none: c => `Aucune annonce à ${c} avec le même nombre de chambres et une surface proche.`,
        f: { balcony: "Balcon", terrace: "Terrasse", lift: "Ascenseur", parking: "Parking", air_conditioning: "Climatisation", garden: "Jardin", pool: "Piscine", camp_site_nearby: "Camping à proximité" },
        e: { quiet: "Calme (route/rail < 65 dB)", clean_air: "Air sain (PM2.5 ≤ 15)", leafy: "Arboré", coastal: "À ≤ 5 km de la côte", flood_safe: "Hors zones inondables", wildfire_safer: "Moindre risque météo d'incendie", seismic_safer: "Aléa sismique plus faible", stable_ground: "Sol stable" },
        m: { "walk_time.metro_station": "À pied au métro", "walk_time.railway_station": "À pied à la gare", "walk_time.supermarket": "À pied au supermarché", "walk_time.school": "À pied à l'école", "walk_time.park": "À pied à un parc", "drive_time.coast": "En voiture à la côte", "drive_time.airport": "En voiture à l'aéroport" },
        c: { sunshine_hours: "Soleil, h/an", sea_temp_summer_c: "Mer en été, °C", summer_max_c: "Max. d'été, °C", winter_min_c: "Min. d'hiver, °C" } },
  de: { home: "Dieses Objekt", in: c => `In ${c}`, price: "Angebotspreis", m2: "€/m²", area: "Wohnfläche", rooms: "Schlafzimmer · Bäder",
        features: "Im Inserat genannt", env: "Umgebung (Gebietsdaten)", minutes: "Minuten", climate: "Regionales Klima",
        legend: "✓ genannt · – nicht genannt (das Inserat sagt es nicht; kein „nein“) · ? keine Daten. Nach dem Objekt ausgewählt, nie nach dem Preis. Angebotspreise, keine Bewertungen.",
        none: c => `Kein Inserat in ${c} mit gleich vielen Schlafzimmern und ähnlicher Fläche.`,
        f: { balcony: "Balkon", terrace: "Terrasse", lift: "Aufzug", parking: "Stellplatz", air_conditioning: "Klimaanlage", garden: "Garten", pool: "Pool", camp_site_nearby: "Campingplatz in der Nähe" },
        e: { quiet: "Ruhig (Straße/Bahn < 65 dB)", clean_air: "Saubere Luft (PM2,5 ≤ 15)", leafy: "Grün", coastal: "≤ 5 km zur Küste", flood_safe: "Außerhalb von Hochwasserzonen", wildfire_safer: "Geringere Waldbrandwetterlage", seismic_safer: "Geringere Erdbebengefahr", stable_ground: "Stabiler Boden" },
        m: { "walk_time.metro_station": "Zu Fuß zur Metro", "walk_time.railway_station": "Zu Fuß zum Bahnhof", "walk_time.supermarket": "Zu Fuß zum Supermarkt", "walk_time.school": "Zu Fuß zur Schule", "walk_time.park": "Zu Fuß zum Park", "drive_time.coast": "Mit dem Auto zur Küste", "drive_time.airport": "Mit dem Auto zum Flughafen" },
        c: { sunshine_hours: "Sonne, h/Jahr", sea_temp_summer_c: "Meer im Sommer, °C", summer_max_c: "Sommerhoch, °C", winter_min_c: "Wintertief, °C" } },
  nl: { home: "Deze woning", in: c => `In ${c}`, price: "Vraagprijs", m2: "€/m²", area: "Woonoppervlak", rooms: "Slaapkamers · badkamers",
        features: "Vermeld in de advertentie", env: "Omgeving (gebiedsdata)", minutes: "Minuten", climate: "Regionaal klimaat",
        legend: "✓ vermeld · – niet vermeld (de advertentie zegt het niet; geen “nee”) · ? geen meting. Gekozen op de woning, nooit op prijs. Vraagprijzen, geen taxaties.",
        none: c => `Geen advertentie in ${c} met evenveel slaapkamers en een vergelijkbaar oppervlak.`,
        f: { balcony: "Balkon", terrace: "Terras", lift: "Lift", parking: "Parkeerplaats", air_conditioning: "Airco", garden: "Tuin", pool: "Zwembad", camp_site_nearby: "Camping in de buurt" },
        e: { quiet: "Rustig (weg/spoor < 65 dB)", clean_air: "Schone lucht (PM2,5 ≤ 15)", leafy: "Groen", coastal: "≤ 5 km van de kust", flood_safe: "Buiten overstromingsgebied", wildfire_safer: "Minder bosbrandweer", seismic_safer: "Lager aardbevingsgevaar", stable_ground: "Stabiele bodem" },
        m: { "walk_time.metro_station": "Lopen naar de metro", "walk_time.railway_station": "Lopen naar het station", "walk_time.supermarket": "Lopen naar de supermarkt", "walk_time.school": "Lopen naar school", "walk_time.park": "Lopen naar een park", "drive_time.coast": "Rijden naar de kust", "drive_time.airport": "Rijden naar de luchthaven" },
        c: { sunshine_hours: "Zon, u/jaar", sea_temp_summer_c: "Zee in de zomer, °C", summer_max_c: "Zomermax., °C", winter_min_c: "Wintermin., °C" } },
};

// The side-by-side table: this home, then each match (numbered as its card).
// Every cell is drawn from find_similar_elsewhere's result, escaped.
function similarTable(el, s, lang) {
  const L = SIM[lang] || SIM.en, cols = s.columns || [];
  if (!cols.length) return;
  const num = v => (v == null || v === "") ? "" : Math.round(Number(v)).toLocaleString(lang || "en").replace(/,/g, " ");
  const head = cols.map(c => c.role === "seed"
    ? `<th scope="col">${esc(L.home)}${c.card ? ` <span class="n">#${esc(c.card)}</span>` : ""}<span>${esc(c.city || "")}</span></th>`
    : `<th scope="col">${esc(L.in(c.city || s.city))} <span class="n">#${esc(c.card)}</span><span>${esc(c.city || "")}</span></th>`).join("");
  const row = (label, cells, cls = "") => `<tr class="${cls}"><th scope="row">${esc(label)}</th>${cells.map(x => `<td>${x}</td>`).join("")}</tr>`;
  const group = label => `<tr class="grp"><th colspan="${cols.length + 1}">${esc(label)}</th></tr>`;
  const any = vals => vals.some(v => v != null && v !== "");
  let body = "";
  body += row(L.price, cols.map(c => c.price ? `<b>€${esc(num(c.price))}</b>` : "–"), "big");
  if (any(cols.map(c => c.eur_per_m2))) body += row(L.m2, cols.map(c => c.eur_per_m2 ? `€${esc(num(c.eur_per_m2))}` : "–"));
  if (any(cols.map(c => c.living_area))) body += row(L.area, cols.map(c => c.living_area ? `${esc(num(c.living_area))} m²` : "–"));
  body += row(L.rooms, cols.map(c => `${esc(c.bedrooms ?? "–")} · ${esc(c.bathrooms ?? "–")}`));
  const feats = Object.keys(L.f).filter(k => cols.some(c => (c.features || {})[k] === "stated"));
  if (feats.length) {
    body += group(L.features);
    for (const k of feats) body += row(L.f[k], cols.map(c => (c.features || {})[k] === "stated" ? `<span class="ok">✓</span>` : `<span class="ns">–</span>`));
  }
  const envs = Object.keys(L.e).filter(k => cols.some(c => ((c.environment || {})[k] || {}).state !== "unknown"));
  if (envs.length) {
    body += group(L.env);
    for (const k of envs) body += row(L.e[k], cols.map(c => {
      const a = (c.environment || {})[k] || { state: "unknown" };
      const mark = a.state === "yes" ? `<span class="ok">✓</span>` : a.state === "no" ? `<span class="no">✗</span>` : `<span class="ns">?</span>`;
      return mark + (a.value != null ? ` <small>${esc(a.value)}${a.unit ? " " + esc(a.unit) : ""}</small>` : "");
    }));
  }
  const mins = Object.keys(L.m).filter(k => any(cols.map(c => (c.minutes || {})[k])));
  if (mins.length) {
    body += group(L.minutes);
    for (const k of mins) body += row(L.m[k], cols.map(c => (c.minutes || {})[k] != null ? `${esc(num(c.minutes[k]))} min` : "?"));
  }
  const clim = Object.keys(L.c).filter(k => any(cols.map(c => (c.climate || {})[k])));
  if (clim.length) {
    body += group(L.climate);
    for (const k of clim) body += row(L.c[k], cols.map(c => (c.climate || {})[k] != null ? esc(num(c.climate[k])) : "?"));
  }
  el.innerHTML = `<div class="simwrap"><table><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table></div>
    ${cols.length < 2 ? `<p class="simnone">${esc(L.none(s.city))}</p>` : ""}
    <p class="simnote">${esc(L.legend)}</p>`;
  el.hidden = false;
}

const PH = {
  en: { title: n => `Asking price on Cubi${n ? ` · #${n}` : ""}`, now: "Now", since: d => `On Cubi since ${d}`,
        none: d => `No change observed since ${d}, when Cubi began tracking prices.`, total: "Since first seen",
        xhead: "Posts on X · last 7 days", xnote: "People’s posts, shown as published on X; not checked by Cubi.", xview: "View on X", x: "Latest posts on X", note: "Asking prices, not sale prices. Cubi records changes it sees in its daily syncs." },
  pt: { title: n => `Preço pedido na Cubi${n ? ` · #${n}` : ""}`, now: "Agora", since: d => `Na Cubi desde ${d}`,
        none: d => `Nenhuma alteração observada desde ${d}, quando a Cubi começou a acompanhar preços.`, total: "Desde o primeiro registo",
        xhead: "Publicações no X · últimos 7 dias", xnote: "Publicações de pessoas, tal como no X; a Cubi não as verificou.", xview: "Ver no X", x: "Publicações recentes no X", note: "Preços pedidos, não preços de venda. A Cubi regista as alterações que vê nas sincronizações diárias." },
  es: { title: n => `Precio de oferta en Cubi${n ? ` · #${n}` : ""}`, now: "Ahora", since: d => `En Cubi desde ${d}`,
        none: d => `Sin cambios observados desde ${d}, cuando Cubi empezó a seguir los precios.`, total: "Desde el primer registro",
        xhead: "Publicaciones en X · últimos 7 días", xnote: "Publicaciones de personas, tal como en X; Cubi no las ha verificado.", xview: "Ver en X", x: "Publicaciones recientes en X", note: "Precios de oferta, no de venta. Cubi registra los cambios que ve en sus sincronizaciones diarias." },
  fr: { title: n => `Prix demandé sur Cubi${n ? ` · n°${n}` : ""}`, now: "Aujourd'hui", since: d => `Sur Cubi depuis le ${d}`,
        none: d => `Aucun changement observé depuis le ${d}, début du suivi des prix par Cubi.`, total: "Depuis la première observation",
        xhead: "Posts sur X · 7 derniers jours", xnote: "Posts de particuliers, tels que publiés sur X ; non vérifiés par Cubi.", xview: "Voir sur X", x: "Derniers posts sur X", note: "Prix demandés, pas des prix de vente. Cubi enregistre les changements vus lors de ses synchronisations quotidiennes." },
  de: { title: n => `Angebotspreis auf Cubi${n ? ` · #${n}` : ""}`, now: "Jetzt", since: d => `Auf Cubi seit ${d}`,
        none: d => `Keine Änderung beobachtet seit ${d}, als Cubi mit der Preisverfolgung begann.`, total: "Seit der ersten Erfassung",
        xhead: "Beiträge auf X · letzte 7 Tage", xnote: "Beiträge von Personen, wie auf X veröffentlicht; nicht von Cubi geprüft.", xview: "Auf X ansehen", x: "Neueste Beiträge auf X", note: "Angebotspreise, keine Verkaufspreise. Cubi erfasst Änderungen bei der täglichen Synchronisierung." },
  nl: { title: n => `Vraagprijs op Cubi${n ? ` · #${n}` : ""}`, now: "Nu", since: d => `Op Cubi sinds ${d}`,
        none: d => `Geen wijziging gezien sinds ${d}, toen Cubi prijzen begon te volgen.`, total: "Sinds eerste waarneming",
        xhead: "Berichten op X · laatste 7 dagen", xnote: "Berichten van mensen, zoals op X geplaatst; niet gecontroleerd door Cubi.", xview: "Bekijk op X", x: "Laatste berichten op X", note: "Vraagprijzen, geen verkoopprijzen. Cubi legt wijzigingen vast die het bij de dagelijkse synchronisatie ziet." },
};

// The home's observed price changes, and a link to X's live search for its city.
function priceHistory(el, h, xUrl, lang, posts) {
  const L = PH[lang] || PH.en;
  const eur = v => euro(v, lang);
  let body = "";
  if (h) {
    const rows = (h.changes || []).map(c => `<tr><td>${esc(c.date)}</td><td>${esc(eur(c.old_price))} → <b>${esc(eur(c.new_price))}</b></td>
      <td class="${c.pct < 0 ? "down" : "up"}">${c.pct > 0 ? "+" : ""}${esc(c.pct)}%</td></tr>`).join("");
    body += `<div class="phhead">${esc(L.title(h.card))}</div>
      <table>${rows}<tr class="now"><td>${esc(L.now)}</td><td><b>${esc(eur(h.current_price))}</b></td>
      <td>${h.total_change_pct != null ? `<span class="${h.total_change_pct < 0 ? "down" : "up"}">${h.total_change_pct > 0 ? "+" : ""}${esc(h.total_change_pct)}%</span> <small>${esc(L.total)}</small>` : ""}</td></tr></table>
      ${(h.changes || []).length ? "" : `<p class="phnone">${esc(L.none(h.tracked_since))}</p>`}
      <p class="phnote">${esc(L.since(h.on_cubi_since || "?"))} · ${esc(L.note)}</p>`;
  }
  // Posts as X's display terms ask: name, @handle, date, the text unchanged, a link to the post.
  const shown = (posts || []).filter(p => safeUrl(p.url));
  if (shown.length) {
    body += `<div class="xposts"><div class="phhead">${esc(L.xhead)}</div>` + shown.map(p => `
      <div class="xpost"><div class="xwho"><b>${esc(p.name)}</b> <span>@${esc(p.handle)} · ${esc(p.date)}</span>
        <span class="xsid">${esc(p.sid)}</span></div>
        <p>${esc(p.text)}</p><a href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener nofollow">${esc(L.xview)} ↗</a></div>`).join("")
      + `<p class="phnote">${esc(L.xnote)}</p></div>`;
  }
  const x = safeUrl(xUrl);
  if (x) body += `<a class="xlink" href="${esc(x)}" target="_blank" rel="noopener nofollow">${esc(L.x)} ↗</a>`;
  if (!body) return;
  el.innerHTML = body;
  el.hidden = false;
}

// Next questions, chosen by the server from the conversation (agent/suggest.py).
function suggestions(box, list) {
  for (const text of list.slice(0, 3)) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", () => ask(text));
    box.appendChild(b);
  }
}

function scrollDown() { window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); }

// A redeploy takes the endpoint away for a few minutes (the public link answers 404
// "No tunnel") and the restart forgets every chat (tester F6, F19). The page waits
// for the agent to come back and sends the message then, instead of a dead end.
const RESTART = {
  en: { wait: "The demo is restarting — your message goes out as soon as it's back…",
        lost: "The demo restarted, so earlier results in this chat are forgotten: search again before asking about a card." },
  pt: { wait: "A demo está a reiniciar — a sua mensagem segue assim que voltar…",
        lost: "A demo reiniciou e esqueceu os resultados anteriores desta conversa: pesquise de novo antes de perguntar por um cartão." },
  es: { wait: "La demo se está reiniciando — tu mensaje se enviará en cuanto vuelva…",
        lost: "La demo se reinició y olvidó los resultados anteriores de este chat: busca de nuevo antes de preguntar por una tarjeta." },
  fr: { wait: "La démo redémarre — votre message partira dès son retour…",
        lost: "La démo a redémarré et a oublié les résultats précédents : relancez une recherche avant de parler d'une carte." },
  de: { wait: "Die Demo startet neu — Ihre Nachricht wird gesendet, sobald sie zurück ist…",
        lost: "Die Demo wurde neu gestartet und hat frühere Ergebnisse vergessen: Suchen Sie erneut, bevor Sie nach einer Karte fragen." },
  nl: { wait: "De demo start opnieuw op — uw bericht gaat zodra hij terug is…",
        lost: "De demo is herstart en is eerdere resultaten vergeten: zoek opnieuw voordat u naar een kaart vraagt." },
};
const DOWN = new Set([404, 502, 503, 504]);
const REACH_FOR_MS = 4 * 60 * 1000, POLL_MS = 5000;

async function reach(send, label) {
  const until = Date.now() + REACH_FOR_MS;
  for (;;) {
    let res = null;
    try { res = await send(); } catch (e) { res = null; }
    if (res && !DOWN.has(res.status)) return res;
    if (Date.now() > until) { if (res) return res; throw new Error("unreachable"); }
    label.textContent = (RESTART[document.documentElement.lang] || RESTART.en).wait;
    for (;;) {   // wait for the health check, not for another failed turn
      await new Promise(r => setTimeout(r, POLL_MS));
      try { if ((await fetch("/api/health", { cache: "no-store" })).ok) break; } catch (e) { /* still down */ }
      if (Date.now() > until) break;
    }
  }
}

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

  const had = sessionId;
  try {
    const res = await reach(() => fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    }), label);
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
        if (ev.type === "session") {
          if (had && ev.id !== had) {   // the server no longer knows this chat: say so before "#2" means nothing
            const note = document.createElement("p");
            note.className = "restart-note";
            note.textContent = (RESTART[document.documentElement.lang] || RESTART.en).lost;
            bot.before(note);
          }
          sessionId = ev.id;
        }
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
          if (ev.similar) similarTable(turn.querySelector(".similar"), ev.similar, ev.lang);
          if (ev.price_history || ev.x_url) priceHistory(turn.querySelector(".pricehist"), ev.price_history, ev.x_url, ev.lang, ev.x_posts);
          if (ev.inventory) budget(turn.querySelector(".budget"), ev.inventory, t, ev.lang);
          (ev.listings || []).forEach(c => cards.appendChild(card(c, t)));
          suggestions(fups, ev.suggestions || []);
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
// +2: scrollHeight leaves out the border (box-sizing: border-box), which showed a scrollbar.
input.addEventListener("input", () => { input.style.height = ""; input.style.height = Math.min(input.scrollHeight + 2, 160) + "px"; });

// The notice opens while the user is typing and folds back to one line when they send
// or leave the field; tapping its summary opens or closes it at any time. Programmatic
// focus after an answer doesn't open it (that would cover the answer each time).
const notice = document.getElementById("notice");
let noticePinned = false;  // opened by the user's own tap: leave it open
notice.querySelector("summary").addEventListener("click", () => { noticePinned = !notice.open; });
input.addEventListener("input", () => { if (input.value) notice.open = true; });
input.addEventListener("pointerdown", () => { notice.open = true; });
input.addEventListener("blur", e => {
  if (!noticePinned && !notice.contains(e.relatedTarget)) notice.open = false;
});
form.addEventListener("submit", () => { if (!noticePinned) notice.open = false; });
document.getElementById("examples")?.addEventListener("click", e => {
  if (e.target.closest("button")) ask(e.target.closest("button").textContent);
});
document.getElementById("new").addEventListener("click", () => {
  if (sessionId) fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId }) });
  sessionId = null;
  location.reload();
});
