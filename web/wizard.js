// Home wizard: five quick picks (feel → country → type → goal and budget → priorities)
// that build a plain search message and a living brief, then send the message to the
// agent like a typed one (ask() in app.js). Every step can continue or search now.
// Options and image prompts are in /static/wizard/options.json (the images come from
// scripts/make_wizard_images.py); listing counts come from /api/wizard (Cubi's corpus,
// cached on the server).
//
// Hard and soft: country, deal, types (OR), bedrooms, budget and must-haves are written
// as filters; the feel of a place and "nice to have" priorities go after "ideally", which
// Cubi's search ranks on without excluding anything (live 2026-10-25: "ideally with a sea
// view" kept all 8,432 Greek 1-bed flats; "near the coast" in any form cut them to 11).
// At most three wishes go in: from the fourth Cubi started applying one as a filter
// ("ideally with a sea view, furnished and close to public transport" cut 538 Spanish
// fixer-uppers to 14; any two of them kept 538).
(() => {
  const root = document.getElementById("wizard");
  if (!root) return;
  const STEPS = ["Feel", "Country", "Type", "Goal and budget", "Priorities"];
  const THE = new Set(["Netherlands", "United Kingdom", "Czech Republic"]);  // "in the Netherlands"
  const MAX_PRIORITIES = 8;  // shown at once; condition tiles (renovated, to renovate) come on top
  const MAX_SOFT = 3;  // wishes written after "ideally"; see the note above
  // A picked landscape is a filter, not a wish: Cubi's free-text search ignores an
  // "ideally …" clause when ranking (Italy, 2026-10-25: the top homes were the same with
  // and without "ideally with a lake view"), while "near a lake" as a requirement
  // returned 725 lakeside homes. Each landscape's `phrase` is written before the budget.
  const NEW_MIN = 100;  // "new this week" shown from this many; fewer says more about scraping than the market
  // Every country at once. Cubi's free-text search runs the whole corpus only when the
  // sentence says so, and asks "where?" otherwise; written at the end, after the budget
  // (live 2026-10-26: lakeside houses 104, mountain houses 233, sea-view houses 1,000+;
  // the same words in the middle of the sentence timed out once).
  const ANY = "Anywhere in Europe";
  const anywhere = () => pick.country === ANY;
  let opt = null, stats = { countries: {} };
  // budget: a number, "flexible" (no cap, by choice), "unsure" (no cap, still open) or null.
  const pick = { envs: [], region: null, country: null, types: [], goal: null, beds: null, budget: null, nice: [], must: [] };
  let step = 0;

  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const compact = n => n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M"
    : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(n);
  const money = n => "€" + n.toLocaleString("en-GB");
  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
  const list = a => a.join(", ").replace(/, ([^,]*)$/, " and $1");
  const toggle = (arr, id) => arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  function countryStats(names) {
    let homes = 0, fresh = 0, any = false;
    for (const n of names) {
      const s = stats.countries[n];
      if (!s) continue;
      any = true; homes += s.homes || 0; fresh += s.new_7d || 0;
    }
    if (!any) return "";
    return `${compact(homes)} homes on Cubi` + (fresh >= NEW_MIN ? ` · ${compact(fresh)} new this week` : "");
  }

  function tile({ id, label, blurb, stat, selected, badge, onClick, cls }) {
    const b = el("button", "wz-tile" + (selected ? " on" : "") + (cls ? " " + cls : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", selected ? "true" : "false");
    const ph = el("div", "wz-img");
    ph.dataset.label = label;
    const img = new Image();
    img.alt = "";
    img.loading = "lazy";
    img.src = `/static/wizard/${id}.jpg`;
    img.onerror = () => img.remove();  // the coloured tile stays
    ph.append(img);
    if (badge != null) ph.append(el("span", "wz-check" + (selected ? " on" : ""), selected ? badge : ""));
    b.append(ph, el("strong", null, label));
    if (blurb) b.append(el("span", "wz-blurb", blurb));
    if (stat) b.append(el("span", "wz-stat", stat));
    b.addEventListener("click", onClick);
    return b;
  }

  const country = () => opt.countries[pick.country] || null;
  const goal = () => opt.goals.find(g => g.id === pick.goal) || null;
  const deal = () => (goal() || {}).deal || "sale";
  // "Build" with no type picked means land; the brief says so ("assumed").
  const typesInferred = () => !pick.types.length && !!(goal() || {}).types;
  const types = () => pick.types.length ? pick.types : ((goal() || {}).types || []);
  const hasLand = () => types().includes("land");
  const studioOk = () => types().every(t => t === "apartment");
  const typeOf = id => opt.types.find(t => t.id === id);
  const bedsLabel = n => n === 0 ? "Studio" : n >= 4 ? "4+" : String(n);

  // Does this environment or priority make sense for the country (landscape, climate),
  // the property types (any of them) and the goal? Nothing picked rules nothing out.
  const fits = x => {
    const c = country();
    if (x.needs && c && !c.has.includes(x.needs)) return false;
    if (x.climate && c && !x.climate.includes(c.climate)) return false;  // Europe-wide: every climate
    const t = types();
    if (x.types && t.length && !t.some(id => x.types.includes(id))) return false;
    if (x.goals && pick.goal && !x.goals.includes(pick.goal)) return false;
    return true;
  };
  const envs = () => opt.environments.filter(e => pick.envs.includes(e.id));
  // Countries that offer every landscape the picked feel needs come first.
  const countryFits = name => envs().every(e => !e.needs || opt.countries[name].has.includes(e.needs));

  // Priorities that make sense here, the most relevant first ("top" names a climate,
  // an environment, a type, a goal or a deal; a goal or deal match outranks a landscape
  // match, which outranks the climate, so "furnished" surfaces for renters and investors).
  const CLIMATES = ["warm", "mild", "cold"];
  const weight = t => opt.goals.some(g => g.id === t) || t === "sale" || t === "rent" ? 3 : CLIMATES.includes(t) ? 1 : 2;
  function priorities() {
    const c = country() || {};
    const ctx = new Set([c.climate, ...pick.envs, ...types(), pick.goal, deal()].filter(Boolean));
    const ranked = opt.priorities.filter(f => fits(f) && !f.group)
      .map((f, i) => ({ f, score: i - 100 * Math.max(0, ...(f.top || []).filter(t => ctx.has(t)).map(weight)) }))
      .sort((a, b) => a.score - b.score).map(x => x.f);
    const shown = ranked.slice(0, MAX_PRIORITIES);
    for (const f of ranked.slice(MAX_PRIORITIES)) if (pick.nice.includes(f.id) || pick.must.includes(f.id)) shown.push(f);
    return [...shown, ...opt.priorities.filter(f => fits(f) && f.group)];
  }
  const chosen = which => opt.priorities.filter(f => fits(f) && pick[which].includes(f.id));
  const stateOf = id => pick.must.includes(id) ? "must" : pick.nice.includes(id) ? "nice" : "";

  // "with a pool", "with a garden", "in a quiet spot" → "with a pool and a garden, in a quiet spot"
  function phrases(items) {
    const withs = items.filter(p => p.startsWith("with ")).map(p => p.slice(5));
    const rest = items.filter(p => !p.startsWith("with "));
    const parts = (withs.length ? ["with " + list(withs)] : []).concat(rest);
    return withs.length > 1 ? parts.join(", ") : list(parts);  // one "and" per sentence
  }

  function query() {
    const t = types().map(typeOf).filter(Boolean);
    const must = chosen("must"), nice = chosen("nice");
    const beds = hasLand() ? null : pick.beds;  // a plot has no bedrooms
    let noun = t.length ? t.map(x => x.plural.toLowerCase()).join(" or ") : "homes";
    if (beds === 0) noun = "studio apartments";
    else if (beds && beds < 4) noun = `${beds}-bedroom ${noun}`;
    const pre = must.filter(f => f.pre).map(f => f.pre);
    if (pre.length) noun = pre.join(" ") + " " + noun;
    let q = `${cap(noun)} ${deal() === "rent" ? "to rent" : "for sale"}`;
    if (!anywhere()) q += ` in ${THE.has(pick.country) ? "the " : ""}${pick.country}`;
    if (goal() && goal().phrase) q += " " + goal().phrase;
    const hard = [...envs().filter(fits).map(e => e.phrase), ...must.filter(f => f.phrase).map(f => f.phrase)];
    if (beds >= 4) hard.unshift("with 4 or more bedrooms");
    if (hard.length) q += " " + phrases(hard);
    if (typeof pick.budget === "number") q += ` up to ${money(pick.budget)}${deal() === "rent" ? " a month" : ""}`;
    if (anywhere()) q += ", anywhere in Europe";
    const soft = nice.map(f => f.phrase || f.pre).slice(0, MAX_SOFT);
    if (soft.length) q += ", ideally " + phrases(soft);
    return q;
  }

  // The living brief: what will filter, what will only rank, what is still open.
  function brief() {
    const facts = [], prefs = [], open = [], skipped = [], notes = [];
    if (anywhere()) facts.push("every country on Cubi at once");
    else if (pick.country) facts.push(pick.country); else open.push("country");
    if (pick.goal) facts.push(deal() === "rent" ? "to rent" : "for sale");
    else open.push("buy or rent (for sale until you pick a goal)");  // the default is an assumption, not a filter
    const t = types().map(typeOf).filter(Boolean);
    const beds = hasLand() ? null : pick.beds;
    if (beds === 0) facts.push("studio apartments");  // a studio is an apartment: the type isn't open
    else if (t.length) facts.push(t.map(x => x.plural.toLowerCase()).join(" or ") + (typesInferred() ? " (assumed from Build)" : ""));
    else open.push("property type");
    if (!hasLand() && beds !== 0) {
      if (beds != null) facts.push(beds >= 4 ? "4 or more bedrooms" : `${beds} bedroom${beds > 1 ? "s" : ""}`);
      else open.push("bedrooms");
    }
    if (typeof pick.budget === "number") facts.push(`up to ${money(pick.budget)}${deal() === "rent" ? " a month" : ""}`);
    else if (pick.budget === "flexible") facts.push("any budget");
    else open.push("budget");
    for (const e of opt.environments.filter(e => pick.envs.includes(e.id))) {
      if (fits(e)) facts.push(e.id === "coast" ? "a sea view" : e.phrase);
      else skipped.push(`${e.label.toLowerCase()} — ${e.missing} in ${THE.has(pick.country) ? "the " : ""}${pick.country}`);
    }
    const must = chosen("must");
    if (must.length) facts.push("must have: " + list(must.map(f => f.label.toLowerCase())));
    prefs.push(...chosen("nice").map(f => f.label.toLowerCase()));
    const later = prefs.splice(MAX_SOFT);  // the search takes three; the chat takes the rest
    if (later.length) open.push("also wanted, ask in the chat: " + list(later));
    if (pick.goal === "invest") prefs.push("an investment — Cubi has asking prices, no yields");
    if (pick.goal === "build") prefs.push("to build on — buildability isn't verified by Cubi");
    open.push(anywhere() ? "a country or a town (narrow it in the chat)" : "town or city (narrow it in the chat)");
    if (anywhere()) notes.push("a Europe-wide search takes longer; if it hits Cubi's time limit the agent searches Spain, Italy, "
                               + "Portugal and Germany side by side instead and says so. The homes come from different countries; "
                               + "the chat can compare two of them feature by feature");
    const box = el("div", "wz-brief");
    box.append(el("strong", null, "Cubi Agent understands"));
    const row = (name, items, note) => {
      if (!items.length) return;
      const p = el("p");
      p.append(el("b", null, name), " ");
      if (note) p.append(el("i", null, note + " "));
      p.append(list(items));
      box.append(p);
    };
    row("Filters:", facts);
    row("Wishes:", prefs, "(tried as requirements first; kept as wishes if too few homes have them all)");
    row("Skipped:", skipped);
    row("Still open:", open);
    row("Heads-up:", notes);
    return box;
  }

  function render() {
    root.replaceChildren();
    const head = el("div", "wz-head");
    const back = el("button", "wz-back", "← Back");
    back.type = "button";
    back.hidden = step === 0;
    back.addEventListener("click", () => { step -= 1; render(); });
    const dots = el("ol", "wz-dots");
    STEPS.forEach((s, i) => {
      const d = el("li", i < step ? "done" : i === step ? "now" : "");
      d.title = s;
      dots.append(d);
    });
    head.append(back, dots);
    root.append(head, el("p", "wz-step", `${step + 1} of ${STEPS.length} · ${STEPS[step]}`));

    const grid = el("div", "wz-grid");
    let title = "", hint = "", canContinue = true;
    if (step === 0) {
      title = "Where would you love to wake up?";
      hint = "Pick the feeling, one or more. These filter the homes; a town or city can come later.";
      for (const e of opt.environments) grid.append(tile({
        id: e.id, label: e.label, blurb: e.blurb, badge: "✓", selected: pick.envs.includes(e.id),
        onClick: () => { pick.envs = toggle(pick.envs, e.id); render(); },
      }));
    } else if (step === 1) {
      title = "Which country?";
      hint = "One country — or every country on Cubi at once, to compare homes across borders.";
      canContinue = !!pick.country;
      const chips = el("div", "wz-chips wz-regions");
      for (const r of [{ id: null, label: "All" }, ...opt.regions]) {
        const b = el("button", pick.region === r.id ? "on" : "", r.label);
        b.type = "button";
        b.addEventListener("click", () => { pick.region = r.id; render(); });
        chips.append(b);
      }
      root.append(el("h3", "wz-title", title), el("p", "wz-hint", hint), chips);
      title = ""; hint = "";
      grid.append(tile({
        id: "anywhere", label: ANY, cls: "wz-any", selected: anywhere(), stat: countryStats(Object.keys(opt.countries)),
        blurb: "Every country at once; the homes can be compared across borders",
        onClick: () => { if (!anywhere()) { pick.nice = []; pick.must = []; } pick.country = ANY; render(); },
      }));
      const region = opt.regions.find(r => r.id === pick.region);
      const names = (region ? region.countries : Object.keys(opt.countries))
        .sort((a, b) => countryFits(b) - countryFits(a) || (stats.countries[b]?.homes || 0) - (stats.countries[a]?.homes || 0));
      for (const n of names) {
        const c = opt.countries[n];
        const miss = envs().filter(e => e.needs && !c.has.includes(e.needs)).map(e => e.missing);
        grid.append(tile({
          id: c.id, label: n, blurb: miss.length ? cap(list(miss)) : c.blurb, stat: countryStats([n]), selected: pick.country === n,
          onClick: () => { if (pick.country !== n) { pick.nice = []; pick.must = []; } pick.country = n; render(); },
        }));
      }
    } else if (step === 2) {
      title = "What kind of space do you imagine?";
      hint = "More than one is fine: the search takes any of them.";
      for (const t of opt.types) grid.append(tile({
        id: t.id, label: t.label, blurb: t.blurb, badge: "✓", selected: pick.types.includes(t.id),
        onClick: () => {
          pick.types = toggle(pick.types, t.id);
          if (pick.beds === 0 && !studioOk()) pick.beds = null;
          render();
        },
      }));
    } else if (step === 3) {
      title = "What are you planning, and what budget feels comfortable?";
      grid.className = "wz-budget";
      const goals = el("div", "wz-grid");
      for (const g of opt.goals) goals.append(tile({
        id: g.id, label: g.label, blurb: g.blurb, selected: pick.goal === g.id,
        onClick: () => {
          const before = deal();
          pick.goal = pick.goal === g.id ? null : g.id;
          if (deal() !== before && typeof pick.budget === "number") pick.budget = null;  // € a month is not a price
          render();
        },
      }));
      grid.append(el("p", "wz-label", "Goal"), goals);
      if (!hasLand()) {
        const beds = el("div", "wz-chips");
        beds.setAttribute("aria-label", "Bedrooms");
        for (const n of opt.bedrooms) {
          if (n === 0 && !studioOk()) continue;
          const b = el("button", pick.beds === n ? "on" : "", bedsLabel(n));
          b.type = "button";
          b.addEventListener("click", () => { pick.beds = pick.beds === n ? null : n; render(); });
          beds.append(b);
        }
        grid.append(el("p", "wz-label", "Bedrooms (optional)"), beds);
      }
      const chips = el("div", "wz-chips");
      const rent = deal() === "rent";
      for (const v of [...opt.budgets[deal()], "flexible", "unsure"]) {
        const label = v === "flexible" ? "Flexible" : v === "unsure" ? "Not sure yet" : `Up to ${money(v)}${rent ? " / month" : ""}`;
        const b = el("button", pick.budget === v ? "on" : "", label);
        b.type = "button";
        b.addEventListener("click", () => { pick.budget = pick.budget === v ? null : v; render(); });
        chips.append(b);
      }
      grid.append(el("p", "wz-label", rent ? "Monthly budget" : "Purchase budget"), chips);
    } else {
      title = "What matters most to you?";
      hint = "Tap once for nice to have (ranks the homes), twice for a must-have (filters them).";
      for (const f of priorities()) {
        const state = stateOf(f.id);
        grid.append(tile({
          id: f.id, label: f.label, badge: state === "must" ? "✓ Must" : "✓", selected: !!state,
          blurb: state === "must" ? "Must-have · tap again to clear" : state === "nice" ? "Nice to have · tap again for must-have" : f.blurb,
          onClick: () => {
            // One condition at most: renovated or to renovate.
            const other = x => x !== f.id && !(f.group && opt.priorities.find(o => o.id === x)?.group === f.group);
            pick.nice = pick.nice.filter(other); pick.must = pick.must.filter(other);
            if (state === "") pick.nice.push(f.id);
            else if (state === "nice") pick.must.push(f.id);
            render();
          },
        }));
      }
    }
    if (title) root.append(el("h3", "wz-title", title));
    if (hint) root.append(el("p", "wz-hint", hint));
    root.append(grid);

    // A search needs a country: three at once timed out on Cubi's free-text search (live 2026-10-24).
    if (step > 0 || pick.envs.length) root.append(brief());
    if (pick.country) root.append(el("p", "wz-preview", `“${query()}”`));
    const actions = el("div", "wz-actions");
    if (step < STEPS.length - 1) {
      const next = el("button", "wz-next", step === 1 ? "Continue" : "Continue (or skip)");
      next.type = "button";
      next.disabled = !canContinue;
      next.addEventListener("click", () => { step += 1; render(); });
      actions.append(next);
    }
    const go = el("button", "wz-go", step === STEPS.length - 1 ? "Search" : "Search now");
    go.type = "button";
    go.disabled = !pick.country;
    if (!pick.country) go.title = "Pick a country, or Anywhere in Europe, to search";
    go.addEventListener("click", () => ask(query()));
    actions.append(go);
    root.append(actions, el("p", "wz-note", (step < 2 ? "Search opens once you pick a country, or all of Europe. " : "") +
      "Images are AI-generated inspiration, not listings."));
  }

  Promise.all([
    fetch("/static/wizard/options.json").then(r => r.json()),
    fetch("/api/wizard").then(r => r.ok ? r.json() : { countries: {} }).catch(() => ({ countries: {} })),
  ]).then(([o, s]) => { opt = o; stats = s || { countries: {} }; root.hidden = false; render(); })
    .catch(() => root.remove());
})();
