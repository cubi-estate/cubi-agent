// Home wizard: six quick picks (region → country → type → setting → bedrooms and
// budget → must-haves) that build a plain search message and send it to the agent like a typed one (ask() in
// app.js). Every step can continue or search now. Options and image prompts are in
// /static/wizard/options.json (the images come from scripts/make_wizard_images.py);
// listing counts come from /api/wizard (Cubi's corpus, cached on the server).
(() => {
  const root = document.getElementById("wizard");
  if (!root) return;
  const STEPS = ["Region", "Country", "Type", "Setting", "Size and budget", "Must-haves"];
  const MAX_FEATURES = 8;  // amenities shown; condition tiles (renovated, to renovate) come on top
  const NEW_MIN = 100;  // "new this week" shown from this many; fewer says more about scraping than the market
  let opt = null, stats = { countries: {} };
  const pick = { region: null, country: null, type: null, setting: null, beds: null, deal: "sale", budget: null, features: [] };
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

  function tile({ id, label, blurb, stat, selected, onClick, multi }) {
    const b = el("button", "wz-tile" + (selected ? " on" : ""));
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
    if (multi) ph.append(el("span", "wz-check", selected ? "✓" : ""));
    b.append(ph, el("strong", null, label));
    if (blurb) b.append(el("span", "wz-blurb", blurb));
    if (stat) b.append(el("span", "wz-stat", stat));
    b.addEventListener("click", onClick);
    return b;
  }

  const country = () => opt.countries[pick.country] || null;
  // A setting or feature can need a landscape ("needs": coast, mountains, lakes) or
  // a climate; with no country picked yet, nothing is ruled out.
  const fits = x => {
    const c = country();
    if (x.needs && c && !c.has.includes(x.needs)) return false;
    if (x.climate && (!c || !x.climate.includes(c.climate))) return false;
    if (x.types && pick.type && !x.types.includes(pick.type)) return false;
    if (x.deal && x.deal !== pick.deal) return false;
    return true;
  };
  const settings = () => {
    const list = opt.settings.filter(fits);
    // An apartment search starts in a city, a house or villa search out of one.
    if (pick.type && pick.type !== "apartment") list.sort((a, b) => (a.id === "city") - (b.id === "city"));
    return list;
  };
  // Must-haves that make sense for this country, type, setting and deal, the most
  // relevant first ("top" names a climate, landscape, setting, type or deal).
  function features() {
    // The landscape counts only once it is the chosen setting: Portugal has mountains,
    // but a seaside villa there wants a sea view before a fireplace.
    const c = country() || {};
    const ctx = new Set([c.climate, pick.setting, pick.type, pick.deal].filter(Boolean));
    if (pick.setting === "lake") ctx.add("lakes");
    const ranked = opt.features.filter(f => fits(f) && !f.group)
      .map((f, i) => ({ f, score: i - ((f.top || []).some(t => ctx.has(t)) ? 100 : 0) }))
      .sort((a, b) => a.score - b.score).map(x => x.f);
    const shown = ranked.slice(0, MAX_FEATURES);
    for (const f of ranked.slice(MAX_FEATURES)) if (pick.features.includes(f.id)) shown.push(f);
    return [...shown, ...opt.features.filter(f => fits(f) && f.group)];
  }
  const bedsLabel = n => n === 0 ? "Studio" : n >= 4 ? "4+" : String(n);

  function query() {
    const t = opt.types.find(x => x.id === pick.type);
    const chosen = features().filter(f => pick.features.includes(f.id));
    const pre = chosen.filter(f => f.pre).map(f => f.pre);
    let noun = t ? t.plural : "Homes";
    if (pick.beds === 0) noun = "Studio apartments";
    else if (pick.beds && pick.beds < 4) noun = `${pick.beds}-bedroom ${noun.toLowerCase()}`;
    if (pre.length) noun = pre.join(" ") + " " + noun.charAt(0).toLowerCase() + noun.slice(1);
    noun = noun.charAt(0).toUpperCase() + noun.slice(1);
    const setting = opt.settings.find(x => x.id === pick.setting && fits(x));
    let q = `${noun} ${pick.deal === "rent" ? "to rent" : "for sale"}${setting ? " " + setting.phrase : ""} in ${pick.country}`;
    const feats = chosen.filter(f => f.phrase).map(f => f.phrase);
    if (pick.beds >= 4) feats.unshift("4 or more bedrooms");
    if (feats.length) q += " with " + feats.join(", ").replace(/, ([^,]*)$/, " and $1");
    if (pick.budget) q += ` up to ${money(pick.budget)}${pick.deal === "rent" ? " a month" : ""}`;
    return q;
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
    let title = "", canContinue = true;
    if (step === 0) {
      title = "Where in Europe?";
      canContinue = !!pick.region;
      for (const r of opt.regions) grid.append(tile({
        id: r.id, label: r.label, blurb: r.blurb, stat: countryStats(r.countries), selected: pick.region === r.id,
        onClick: () => { if (pick.region !== r.id) pick.country = null; pick.region = r.id; render(); },
      }));
    } else if (step === 1) {
      title = "Which country?";
      canContinue = !!pick.country;
      const region = opt.regions.find(r => r.id === pick.region);
      const names = [...region.countries].sort((a, b) => (stats.countries[b]?.homes || 0) - (stats.countries[a]?.homes || 0));
      for (const n of names) {
        const c = opt.countries[n];
        grid.append(tile({
          id: c.id, label: n, blurb: c.blurb, stat: countryStats([n]), selected: pick.country === n,
          onClick: () => { if (pick.country !== n) pick.features = []; pick.country = n; render(); },
        }));
      }
    } else if (step === 2) {
      title = "What kind of home?";
      for (const t of opt.types) grid.append(tile({
        id: t.id, label: t.label, blurb: t.blurb, selected: pick.type === t.id,
        onClick: () => {
          pick.type = pick.type === t.id ? null : t.id;
          if (pick.beds === 0 && pick.type && pick.type !== "apartment") pick.beds = null;
          render();
        },
      }));
    } else if (step === 3) {
      title = "What kind of place?";
      for (const x of settings()) grid.append(tile({
        id: x.id, label: x.label, blurb: x.blurb, selected: pick.setting === x.id,
        onClick: () => { pick.setting = pick.setting === x.id ? null : x.id; render(); },
      }));
    } else if (step === 4) {
      title = "How many bedrooms, and up to how much?";
      grid.className = "wz-budget";
      const beds = el("div", "wz-chips");
      beds.setAttribute("aria-label", "Bedrooms");
      for (const n of opt.bedrooms) {
        if (n === 0 && pick.type && pick.type !== "apartment") continue;
        const b = el("button", pick.beds === n ? "on" : "", bedsLabel(n));
        b.type = "button";
        b.addEventListener("click", () => { pick.beds = pick.beds === n ? null : n; render(); });
        beds.append(b);
      }
      const deal = el("div", "wz-seg");
      for (const [k, label] of [["sale", "Buy"], ["rent", "Rent"]]) {
        const b = el("button", pick.deal === k ? "on" : "", label);
        b.type = "button";
        b.addEventListener("click", () => { if (pick.deal !== k) pick.budget = null; pick.deal = k; render(); });
        deal.append(b);
      }
      const chips = el("div", "wz-chips");
      for (const v of [...opt.budgets[pick.deal], null]) {
        const label = v == null ? "Any budget" : `Up to ${money(v)}${pick.deal === "rent" ? " / month" : ""}`;
        const b = el("button", pick.budget === v ? "on" : "", label);
        b.type = "button";
        b.addEventListener("click", () => { pick.budget = v; render(); });
        chips.append(b);
      }
      grid.append(el("p", "wz-label", "Bedrooms"), beds, el("p", "wz-label", "Budget"), deal, chips);
    } else {
      title = "Anything you can't do without?";
      for (const f of features()) grid.append(tile({
        id: f.id, label: f.label, blurb: f.blurb, multi: true, selected: pick.features.includes(f.id),
        onClick: () => {
          const on = pick.features.includes(f.id);
          // One condition at most: renovated or to renovate.
          const rest = pick.features.filter(x => x !== f.id &&
            !(f.group && opt.features.find(o => o.id === x)?.group === f.group));
          pick.features = on ? rest : [...rest, f.id];
          render();
        },
      }));
    }
    root.append(el("h3", "wz-title", title), grid);

    // A search needs a country: three at once timed out on Cubi's free-text search (live 2026-10-24).
    const preview = pick.country ? query() : "";
    if (preview) root.append(el("p", "wz-preview", `“${preview}”`));
    const actions = el("div", "wz-actions");
    if (step < STEPS.length - 1) {
      const next = el("button", "wz-next", step >= 2 ? "Continue (or skip)" : "Continue");
      next.type = "button";
      next.disabled = !canContinue;
      next.addEventListener("click", () => { step += 1; render(); });
      actions.append(next);
    }
    const go = el("button", "wz-go", step === STEPS.length - 1 ? "Search" : "Search now");
    go.type = "button";
    go.disabled = !pick.country;
    if (!pick.country) go.title = "Pick a country to search";
    go.addEventListener("click", () => ask(query()));
    actions.append(go);
    root.append(actions, el("p", "wz-note", (step === 0 ? "Search opens once you pick a country. " : "") +
      "Images are AI-generated inspiration, not listings."));
  }

  Promise.all([
    fetch("/static/wizard/options.json").then(r => r.json()),
    fetch("/api/wizard").then(r => r.ok ? r.json() : { countries: {} }).catch(() => ({ countries: {} })),
  ]).then(([o, s]) => { opt = o; stats = s || { countries: {} }; root.hidden = false; render(); })
    .catch(() => root.remove());
})();
