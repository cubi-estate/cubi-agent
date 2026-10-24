// Home wizard: five quick picks (region → country → type → budget → must-haves) that
// build a plain search message and send it to the agent like a typed one (ask() in
// app.js). Every step can continue or search now. Options and image prompts are in
// /static/wizard/options.json (the images come from scripts/make_wizard_images.py);
// listing counts come from /api/wizard (Cubi's corpus, cached on the server).
(() => {
  const root = document.getElementById("wizard");
  if (!root) return;
  const STEPS = ["Region", "Country", "Type", "Budget", "Must-haves"];
  const NEW_MIN = 100;  // "new this week" shown from this many; fewer says more about scraping than the market
  let opt = null, stats = { countries: {} };
  const pick = { region: null, country: null, type: null, deal: "sale", budget: null, features: [] };
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

  function query() {
    const t = opt.types.find(x => x.id === pick.type);
    let q = `${t ? t.plural : "Homes"} ${pick.deal === "rent" ? "to rent" : "for sale"} in ${pick.country}`;
    const feats = opt.features.filter(f => pick.features.includes(f.id)).map(f => f.phrase);
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
          onClick: () => { pick.country = n; render(); },
        }));
      }
    } else if (step === 2) {
      title = "What kind of home?";
      for (const t of opt.types) grid.append(tile({
        id: t.id, label: t.label, blurb: t.blurb, selected: pick.type === t.id,
        onClick: () => { pick.type = pick.type === t.id ? null : t.id; render(); },
      }));
    } else if (step === 3) {
      title = "Buy or rent, and up to how much?";
      grid.className = "wz-budget";
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
      grid.append(deal, chips);
    } else {
      title = "Anything you can't do without?";
      for (const f of opt.features) grid.append(tile({
        id: f.id, label: f.label, blurb: f.blurb, multi: true, selected: pick.features.includes(f.id),
        onClick: () => {
          pick.features = pick.features.includes(f.id) ? pick.features.filter(x => x !== f.id) : [...pick.features, f.id];
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
