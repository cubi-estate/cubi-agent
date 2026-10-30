# Demo video: script and shot list

The Oct 29 cut runs **2:30** (the limit is 3:00): four title cards of 3, 5, 5 and 5 seconds around eight screen scenes totalling 2:12. One screen recording of the live demo (the
picture wizard, then seven typed turns), four title cards from `slides.html`, and a
voice-over in English. No music, or only
music you have the rights to. Upload to YouTube as **Public** and put the link in Devpost.

## Before recording

1. **Rehearse against the live demo** the same day:
   `python scripts/demo_rehearsal.py --show-text`. Turns 1–7 are the filmed ones, in
   order; turns 8–9 run features that aren't filmed. You want
   - 6 cards, 3 per city, on turn 1, and three `→` suggestions under every answer;
   - no `! error` lines and no "already asked" flags;
   - turn 2 with `[S1]`-style links and a **Sources** list, and no sentence about
     what a source "did not report" (a guard drops those; if one shows, run again);
   - turns 3 and 4 with a `▮` line per city, and "(was …%)" on turn 4;
   - turn 5 with two `▤` lines, both with most of the 8 environment readings;
   - turn 6 with a `€ price history` line and an `𝕏` link;
   - turn 7 asked in Italian and answered in Italian, with the Cubi sign-in link and
     Italian buttons, and its step line in Italian too ("Ricerca delle opzioni di
     contatto — annuncio #1 …"; the server translates step lines for common languages
     at start-up, so restart it at least a minute before recording);
   - turn 8 naming its number of comparables, with one "independent valuation" line
     and no "thin" when there are ten or more.

   Also walk the wizard once on the day, in a new chat: **By the sea → Anywhere in
   Europe → House and Townhouse → Buy to live, Up to €700,000 → Garden & privacy twice
   (must-have) → Search.** Expect a brief with "every country on Cubi at once … near the
   sea and must have: garden & privacy" under *Filters* (a picked landscape filters —
   Cubi's free-text search ignores an "ideally" wish when ranking, live 2026-10-25) and a
   *Heads-up* line that a Europe-wide search takes longer and falls back to Spain, Italy,
   Portugal and Germany side by side if it hits Cubi's time limit. Then either homes from
   several countries in 9–15 s, or — as on the Oct 29 recording — the time limit and the
   fallback's eight homes in about 45 s, with the chip line "for sale · house/townhouse ·
   ≤ €700,000 · Garden · anywhere in Europe". Never "all have a garden" (a guard drops
   that). If the count is small, a listings change has made Garden rare: pick Terrace
   instead and read the brief aloud as it stands. Picking a single country (Portugal)
   is the faster variant, about 10 s, but then the homes are from one country only.

   Results change as listings change. Note the shares on turns 3–4, the card numbers
   turn 5 compares and what turn 6 says about the price, and fix those voice-over
   lines to match. The feature-by-feature scene comes after the budget on purpose:
   there the top homes are comparable Lisbon and Porto flats with full area data;
   straight after the German search they were a €350k flat 60 km from Porto (the
   search covers Porto district) against an €89k one, with sparse data.
2. **Browser:** a clean profile, no extensions or bookmarks bar, light mode, window
   1920×1080, zoom 125%. Open https://www.cubi.estate/agent and click **New chat**: the
   page opens on the wizard's first step (the pictures are AI-generated, labelled so).
3. **Don't open "Open listing" on camera.** It leads to the portal's page, with its
   logo and photos (plan §4: no portal marks or listing photos). The cards
   themselves show no photos. Don't open the X link on camera either: it shows
   other people's posts. With the demo's X key set, turn 6 shows up to three posts
   in the page itself, with their authors' names: blur that box in the edit, or
   record before the key is added.
4. **Typing:** paste each message, or click the suggestion button where the shot
   says so. Keep the step log open during turn 1 (it opens by default) and let it
   collapse on its own.
5. **Pace:** the demo allows 8 turns a minute per address. Seven filmed turns at a
   natural pace stay under it; don't rush the clicks.
6. **Slides:** open `docs/video/slides.html` in a second window and press F for full
   screen, H to hide the key hint, and → to advance.

## Recording log · Oct 29

Two screen-recorded takes exist (the owner recorded the Chrome window at 1920×1080
on a 4K display; the agent drove the browser; no overlays). Cut from these, not from
the frame-captured GIFs in `~/Downloads/cubi-agent-scene*.gif`, which were the draft.

**Take 1, 15:46–15:56 UTC, one continuous chat, in this order** (about four seconds of
stillness at each boundary):

1. Wizard with **Anywhere in Europe** instead of a country (By the sea → Anywhere in
   Europe → House, Townhouse → Buy to live, Up to €700,000 → Garden & privacy twice →
   Search). The Europe-wide search hit Cubi's time limit and the per-market fallback ran
   — the brief had said it would — and delivered eight homes from Spain, Italy, Portugal
   and Germany in 45 s. Keep the fallback in the cut or trim it: both are honest.
2. New chat, the German Porto/Valencia search: six cards, three per city, German
   buttons, 2.6 s.
3. Schools and public transport, Porto vs Valencia: twelve sources, 4.5 s.
4. Budget: 400k Lisbon vs Porto (7.4% / 18%), then the **And up to €500,000?** button
   (13.8% / 35.9%, markers at the old shares).
5. **Compare #1 and #4 feature by feature**: asking price, €/m², size, bedrooms and the
   regional climate. No stated-feature or environment rows came back for these two
   flats on Oct 29 — read the voice-over accordingly (the 7b take below covers the
   area data).
6. Listing pane: tap on card #3 (a 4-bedroom Lisbon flat, €497,000): brief, highlights,
   *Check before deciding* ("Price on request", "Needs renovation"), climate line, the
   map pinned at the listed address with 72 places nearby, and in the chat the tap's
   line "#3 · Apartment · Lisboa, Lisboa · imovirtual_pt:19325958" with four buttons.
7. The price-and-news button answered **without news** this time (Tavily and X did
   not run on that turn): discard, use take 2.

**Take 2, 15:57–16:00 UTC, new chat:** the Lisbon example button (six cards), then
**Has #1's price dropped, and what's new in Lisbon?** — no change since 29 October,
AP and Yahoo sources, three posts from X (blur their authors' names in the edit), the
price box — then **Come posso contattare l'agente per il #1?** answered in Italian in
15 s with the Cubi sign-in link and Italian buttons.

An earlier abandoned take (15:30) chose Portugal in the wizard; its first search timed
out and a typed retry succeeded. Not needed.

Not yet recorded: **Homes like this one** in the pane and the two similar-homes buttons.
The connector release landed Oct 30 01:17 UTC (PROD v3156, c7fab5d3) and the morning
check of 07:56 UTC passed on a **Porto** search (pane 2.4 s, three matches, six chips,
the compare table in 1.8 s) but not on Lisbon (the Lisbon pool times out at the route's
12 s budget). If filmed, redo shot 7b on "2-bed apartment in Porto under 300k".

## Shots

| # | Time | Picture | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:03 | Card 1 (problem), 3 s | Moving abroad? Two countries, two languages, five portals. |
| 2 | 0:03–0:08 | Card 2 (how it's built), 5 s | Cubi Agent: one conversation over two point three million European listings, on NVIDIA Nemotron and Nebius. |
| 3 | 0:08–0:24 | **Scene 1 · Wizard.** By the sea → Anywhere in Europe (Portugal in the original plan: the faster, one-country variant) → House, Townhouse → Buy to live, Up to €700,000 → Garden & privacy twice; hold a beat on the brief, then Search. Recorded Oct 29: the Europe-wide search hit Cubi's time limit and the agent searched Spain, Italy, Portugal and Germany side by side, eight homes from four countries | No typing to start with: pick a feeling, all of Europe or one country, a kind of home, a plan and a budget, and what matters. The brief under the pictures says what filters, what is only a wish and what is still open — and the search is one plain sentence. *(If the fallback stays in the cut:)* When a search across the whole continent runs long, it splits it by market and says so. |
| 4 | 0:24–0:43 | **Scene 2 · German search.** New chat, paste turn 1, let the steps stream, scroll over the six cards, end on the three buttons | Or ask in German: a flat to buy in Porto or Valencia, up to four hundred thousand, two bedrooms at least. *(pause on the step log)* Nemotron turns that into a structured filter; code checks it, and the agent searches each city separately. Every card comes from Cubi's data, not from the model. |
| 5 | 0:43–1:00 | **Scene 3 · Schools and transport.** Paste turn 2, then scroll to the Sources list | Then the question a mover actually has: what are the schools and public transport like? The agent searches the web with Tavily, one search per city and topic, and writes the two cities side by side. Every point carries a numbered source, linked in code, and where no source covers a topic, it says so. |
| 6 | 1:00–1:19 | **Scene 4 · Budget.** Paste turn 3: bars grow. Click "And up to €500,000?": bars move, markers stay at the old shares (Oct 29: Lisbon 7.4% → 13.8%, Porto 18% → 35.9%) | And from Cubi's own data: what does four hundred thousand buy in Lisbon versus Porto? *(read the two shares on screen)* Raise it to five hundred, and the bars move from the old shares. Cubi counted these; the model only wrote the sentence around them. |
| 7 | 1:19–1:33 | **Scene 5 · Feature by feature.** Click "Compare #1 and #4 feature by feature"; scroll the table slowly. Oct 29: asking price, €/m², size, bedrooms and the regional climate; no stated-feature or environment rows for these two flats | Now the top home in each city, feature by feature: the asking price, the price per square metre, the size, and the regional climate side by side. Where a listing doesn't say, the table says "not stated", never "no". |
| 8 | 1:33–1:52 | **Scene 6 · Listing pane.** Tap card #1 (Oct 29 take: card #3, a 4-bedroom Lisbon flat): the pane opens on the right — brief, highlights, *Check before deciding*, climate line, the map with its pins — and the chat gets the home's line and its buttons; scroll the pane to the map | Tap a card and the home opens in full: Nemotron's brief in your language, what to check before deciding, Cubi's area data, and a map of what's nearby from OpenStreetMap. The tap also writes the home into the chat, with every question you can ask about it as a button. |
| 9 | 1:52–2:08 | **Scene 7 · Price and news.** Click the price-and-news button; hold on the three-sentence answer, then scroll past the price box to the sources and the three posts from X (real names: blur the box in the edit) | Has this Lisbon flat's price dropped, and what's new there? Three sentences: Cubi's price log *(read it: "no change since it appeared")*, the housing news with its sources, and what people post on X — the sources and the posts sit underneath, each with a link. |
| 10 | 2:08–2:20 | **Scene 8 · Italian.** Paste turn 7 (in Italian), hold on the Italian answer, then highlight the sign-in link | Ask in Italian, or any language: Nemotron translates in and out. And contacting the agent goes only through Cubi's consented flow; the demo sends nothing for you. |
| 11 | 2:20–2:25 | Card 3 (results), 5 s | Thirty-six unseen requests in six languages: every field right. Four times faster than Cubi's own search, on a tenth of the quota. |
| 12 | 2:25–2:30 | Card 4 (try it), 5 s: the demo address and github.com/cubi-estate/cubi-agent, public since Oct 29 under Apache-2.0 | Try it at cubi.estate/agent, no account needed. Agent, evals and feedback: open source. |

The eight screen scenes are the Oct 29 recording order (see the recording log above): scenes 1–6 are in take 1, scenes 7–8 in take 2. The cut runs 2:30: the cards take 18 s (3 + 5 + 5 + 5) and the eight screen scenes 2:12, so the scene timings above are a proportional guide — read each scene's line over its actual length in the edit, and trim the scene-5 table scroll first if a line runs long. The card lines are cut to their seconds: about 8 words for 3 s, 13 for 5 s. In all about 380 words.
long, trim the table scroll in scene 7 first, then cut scene 9 (it is the only
any-language shot, so the six-language claim on card 3 then stands alone); the
wizard scene can lose its first three taps (start on the country) but not the brief.
The wizard writes a country-wide search, which runs on Cubi's free-text search (6–10 s);
the German turn is the structured path (about 3 s), so the two scenes also show both. Read the figures the screen shows on the day — shares, card
numbers, the price line — they change as listings change. On 2026-10-22: Lisbon
6.3% → 12.2% and Porto 21.0% → 37.4% for 2+ bedroom flats.

Not filmed, still in the app: the wizard's first country tile, **Anywhere in Europe**,
runs every country at once (the sentence ends ", anywhere in Europe"; lakeside houses
up to €400k came back from Italy, Spain and Portugal in 9 s on 2026-10-26), and the
first button then is "Compare #1 and #3 feature by feature" — two countries side by
side, the table naming "Gittana, Italy" and "Alcaucín, Spain". Broad Europe-wide
picks (a sea view, no feel) can take 15 s or hit Cubi's 22 s limit; when they do, the
agent searches Spain, Italy, Portugal and Germany side by side, merges the cards by
country and says so (a rental with a mountain view near a lake timed out on 2026-10-26
and the reply asked for a town — that is the case this covers). It stays off the filmed path.

Not filmed, in the app since Oct 26 evening: **tap a card** and the home opens in a pane on the right (full screen on a phone) — Nemotron nano's brief in the user's language (in short, highlights, things to check before deciding, e.g. "Needs renovation", "Energy class F"), Cubi's surroundings profile (noise, air, flood, wildfire, seismic; minutes on foot to a supermarket, school, park; climate; €/m²), the agency's description and every tag by section; about 2 s. Photos are held for now: Cubi's connector sends no image list, so the pane says so and links to the listing page. Checked live in Chrome on Oct 26 (build 7063166): on "Houses to rent with a mountain view and near a lake, anywhere in Europe" every card lit **Mountain view**, and tapping #4 (a Fundão house) opened the pane in 2 s with "Ground floor", "No lift" and "High fire-weather risk (62 days/yr)" under *Check before deciding*, the coast 116 km away, a school 15 min on foot. Since the same evening the pane also has a **map**: the listing's address line geocoded on OpenStreetMap (the street or the named place when the listing gives one, else the town centre — the caption says which; Cubi's connector shares no coordinates) with the home pinned and places nearby from OpenStreetMap as pins (supermarkets, schools, parks, stations, pharmacies, restaurants; one category a second, so the pins land one kind at a time over about eight seconds, and the view then zooms to fit the home and every pin). The caption reads e.g. "Pinned at the listed address · 67 places nearby from OpenStreetMap". Checked live on Oct 26 (build 94d8af8): the Carnide flat (#5 of the "2-bed apartment in Lisbon under 450k" example) pinned at Quinta do Bom Nome, with the Pontinha and Carnide metro stations, a supermarket and a school in view. If filmed: tap the card, let the brief land (2 s), scroll to the map and wait for the pins — about ten seconds in all, so it only fits a spare beat in turn 7 or 8. Since Oct 29 (agent 5ecef8a → 0c7be46) the pane also carries **Homes like this one**: up to three homes in the same market picked by Cubi's similarity model — a 50-dimension PCA embedding of each listing's catalogued features, nearest neighbours, then a ranker on stated features, size, place and asking price — each as a small card with the ranker's own reason ("same city · within 7% on price", "€169,000 more · similar size (108 m²)") and a line saying how they were picked. It reads the connector's new `find_similar_homes` tool (cleverdragon 373a5c97 → d9eb1ee4: engine unhydrated, cards from one key lookup, 12 s budget → 504, so the pane leaves the section out rather than wait). Checked on STAGE Oct 29: a Famalicão house seed answered with three PCA-ranked matches; a Warsaw seed hit the budget on STAGE's saturated database (the same query runs in 0.25–0.5 s on PROD). The tool reached Cubi's production connector with release v3156 (c7fab5d3, Oct 30 01:17 UTC). Checked live Oct 30 07:56 UTC: a Porto seed answers in 1.4–2.4 s with three matches (method pca · hybrid · in_city); every Lisbon seed hits the 12 s budget (its candidate pool is 200 homes and the engine takes about 22 s on PROD), so a Lisbon pane shows no similar homes and only four chips. The backend log also shows the Porto seeds had no PCA embedding yet and the pool came from the structural branch while the reply still says `pca` — a label to fix upstream. If filmed: it sits right under *Neighbourhood & environment*, before the map, and lands with the brief (about 2 s on PROD) — tap the card, read the brief, then point at the three small cards and their reasons; about 6 s, so a spare beat in turn 7 or 8, and only after the morning check that a tapped Lisbon card shows matches. Since Oct 29 afternoon (agent 9f316af → 1faa1e0, live 14:18 UTC) the tap also writes a line into the chat — "#1 · Casa · Cascais, Lisboa · afinest_pt:25505032" — followed by every question the app can answer about that home as buttons: *Compare #1 with its similar homes feature by feature* (code pairs the home with each pane pick, one connector read each in parallel, one merged table; the similar homes become the next cards), *Has #1's price dropped, and have its similar homes' prices dropped?* (price-history reads for all of them, prices only), *Is #1's price in line with similar homes?*, *Show me homes like #1 in Porto* (after a one-city search the country's other big market, never the card's own city), *What's new in Cascais?* and *How do I contact the agent for #1?*. Questions already asked or answered in the chat are not offered again. The first two need the similar homes, so until the connector release of Oct 30 they give way to the plain price-and-news question: checked live Oct 29 on a Portuguese Cascais search (four chips, in Portuguese) and on an English Lisbon search (the price chip answered in 5 s with the home's 4.1% drop). If filmed, this is the strongest 15 s of the pane: tap the card, let the chat line and the buttons land (about 2 s), press *Compare #1 with its similar homes feature by feature* and let the table come (about 4 s) — then the three similar homes are cards too, and the next buttons are about them. Checked Oct 30 07:56 UTC on "2-bed apartment in Porto under 300k": tap #1 → six chips; the compare chip ran three pair reads in parallel (1.8 s), asking prices side by side with one feature difference, the picks as cards #7–#9; the drops chip (1.3 s) reported no change on #1 or #7–#9. Film it on Porto, not Lisbon. In the six languages the buttons are native; in any other they are translated once by Nemotron.

Not filmed either (rehearsal turns 8–9): the price check against similar
homes ("Is #2 overpriced?": the range of asking prices and how many comparable homes
it rests on; with too few, one plain sentence saying there is no range, never a
verdict) and similar homes in another city ("Show me homes like #1 in Porto"). Don't add "with parking" anywhere: whether a listing records parking
depends on the agency that published it, so the agent doesn't compare it.

### Optional, if there's time to spare

**An honest "none" (about 8 s, in place of scene 9 if that is cut).** In a new chat,
paste `Appartement à louer à Lyon, 1 200 € par mois max`. Cubi has no Lyon rentals, and
the agent says so: it checks the search without the budget and as a purchase, then
answers that a higher rent wouldn't help, and offers one button, homes for sale in
Lyon. Voice-over: *"When there's nothing to find, it tells you why, instead of telling
you to raise your budget."* Rehearse it first: the reason depends on the listings that
day.

Run the same German query in Claude with the Cubi Estate plugin. It uses the same
skill files, and that shows they're portable. Only add it if the cut stays under 3:00.

## Second recording · rent first, then buy (owner's flow, run end to end in Chrome Oct 30, 13:20 UTC)

A weekend house in the mountains by a lake: picked from pictures, rented first on the
whole corpus, narrowed by region in Portuguese and Spanish, then everything in English:
buying on Lake Como, the price check, Andalusia, the asking prices of homes like it in
Málaga, the listing pane with the OpenStreetMap map, its price check and its twins in
Lisbon, schools and transport, the X news turn, and the contact options. Live build
9fcdf61 (a reply no longer scrolls the page; the down arrow does). Times from the
browser run with Cubi's cache warm.

1. **The wizard, not a typed line.** Feel: Mountains & forests + Near a lake → Country:
   Anywhere in Europe → Type: House → Goal: Rent (no bedrooms, no budget) → Priorities:
   Fireplace tapped twice (must), Garden & privacy once, Mountain view once → Search.
   The sentence it builds is exactly "Houses to rent with a fireplace, in the mountains
   and near a lake, anywhere in Europe, ideally with a garden and a mountain view";
   six cards in 3–13 s (Sofia, Attica, Warsaw, Lefkada — not mountain-lake homes; cut
   away as they land).
2. **PT** `Vamos limitar a pesquisa à Lombardia, por favor` — to rent is kept, 4 villas,
   Lake Garda and Lake Segrino named, 2 s. (Not the short "Vamos restringir à
   Lombardia": it reads as French.)
3. **ES** `¿Y lo mismo en Andalucía?` — to rent, 4 houses, 2 s. No more language switches
   after this turn.
4. `What if I buy instead? Show me homes for sale with a fireplace on Lake Como` — six
   Como villas €440k–€2.8M, 2–4 s.
5. `Is #1's price in line with similar homes?` — €630k inside €590k–€845k of 8
   comparables, 2 s.
6. `And the same in Andalusia?` — six for sale, Colmenar is #4, 2–13 s.
7. `Show me homes like #4 in Málaga` — the asking-prices comparison: two Málaga villas
   (€4.2M, €8.8M) against the €1.19M cortijo, matched on features and surroundings,
   never on price; the table with drive times and climate, 3–7 s.
8. **Tap card #1** (the €4.2M Málaga villa) — the pane: brief, highlights, area data,
   three homes like it within 0–5% on price, the **OpenStreetMap map** with places
   nearby, the description collapsed with Show more, features. Scroll the pane to the
   map; leave it open.
9. `Is #1's price in line with similar homes?` — this region: €4.2M inside
   €3.82M–€4.86M of 16 comparables, 2–4 s.
10. `Compare schools and public transport in Málaga and Lisbon` — Tavily, nine cited
    sources, 5–7 s.
11. `Has #1's price dropped, and what's new in Málaga?` — the X turn on the Málaga
    villa: price log, Tavily news and recent posts on X about housing in Málaga, each
    linked, 7–10 s. **Before the Lisbon turn**, while #1 is still the villa: once the
    Lisbon homes are the cards, "#1" is a Lisbon house (the 13:40 take asked about the
    wrong home's price).
12. `Show me homes like #1 in Lisboa` — another country: two Lisbon houses at €6.5M,
    same bedrooms and size, 5 s. (Como, Milano and Paris have none; Roma has two.)
13. **The ending** `How do I contact the agent for the Málaga villa I opened?` — the
    three consented options and the sign-in link, 2–4 s. Say "the Málaga villa I
    opened", not "#1" (a Lisbon house by then). Since 76f5c28 a link the conversation
    has already shown is no longer removed, so the "something was removed" note of the
    13:40 take is gone.

### Voice-over · second recording (for voice generation)

Read each line over its scene; about 435 words, 2:50 at a calm pace. Cards from
`docs/video/slides.html` (cards 1 and 2 first, cards 3 and 4 at the end).

| Scene | You type or do | Voice-over |
|---|---|---|
| Card 1 (4 s) | title card 1 | A weekend house in the mountains, by a lake. Which country? Let's not decide yet. |
| Card 2 (5 s) | title card 2 | Cubi Agent: one conversation over two point three million European listings, on NVIDIA Nemotron and Nebius. |
| 1 · wizard | Mountains & forests + Near a lake → Anywhere in Europe → House → Rent → Fireplace ×2, Garden & privacy, Mountain view → Search | No typing to start with. Pick a feeling: mountains, a lake. All of Europe. A house, to rent. A fireplace as a must, a garden and a view as wishes. The brief under the pictures says what filters and what only ranks, and the search is one plain sentence over every country on Cubi. |
| 2 · Portuguese | `Vamos limitar a pesquisa à Lombardia, por favor` | Narrow it in Portuguese: Lombardy. The agent keeps "to rent": a first place after a Europe-wide search narrows it, it doesn't start over. |
| 3 · Spanish | `¿Y lo mismo en Andalucía?` | The same in Andalusia, in Spanish. Four houses, two seconds. |
| 4 · Lake Como | `What if I buy instead? Show me homes for sale with a fireplace on Lake Como` | What if I buy instead? Lake Como, with a fireplace: six villas, from four hundred and forty thousand. |
| 5 · price check | `Is #1's price in line with similar homes?` | Is the first one priced in line? Six hundred and thirty thousand sits inside the middle half of eight comparable homes. Asking prices, never a valuation. |
| 6 · Andalusia | `And the same in Andalusia?` | And the same, for sale, in Andalusia. |
| 7 · Málaga | `Show me homes like #4 in Málaga` | Homes like the Colmenar cortijo, in Málaga. Cubi's similarity model matches on features, size and surroundings, never on price, and the table puts the asking prices side by side, with drive times and climate underneath. |
| 8 · the pane | tap card #1 (the €4.2M Málaga villa), scroll the pane to the map | Tap a card and the home opens in full: Nemotron's brief, what to check before deciding, Cubi's area data, three homes like it within five percent on price, and a map from OpenStreetMap with what's nearby. The description stays folded until you ask. |
| 9 · its price | `Is #1's price in line with similar homes?` | This one's price: four point two million, inside the range of sixteen comparable homes in Málaga. |
| 10 · schools | `Compare schools and public transport in Málaga and Lisbon` | Schools and public transport, Málaga against Lisbon. The agent searches the web with Tavily, one search per city and topic, and every point carries a numbered source, linked in code. |
| 11 · X | `Has #1's price dropped, and what's new in Málaga?` | Has the price dropped, and what's new in Málaga? Cubi's price log, the housing news with its sources, and what people post on X, shown as published, not checked by Cubi. |
| 12 · Lisbon | `Show me homes like #1 in Lisboa` | The same home in another country: two houses in Lisbon with the same bedrooms and size, at six and a half million each. |
| 13 · contact | `How do I contact the agent for the Málaga villa I opened?` | And to reach the agent: only through Cubi's consented flow. Questions via Cubi, Cubi Connect, or an email request. No phone number, no email on screen. |
| Card 3 (5 s) | title card 3 | Thirty-six unseen requests in six languages: every field right. Four times faster than Cubi's own search, on a tenth of the quota. |
| Card 4 (5 s) | title card 4 | Try it at cubi.estate/agent, no account needed. Agent, evals and feedback: open source. |

Findings from the runs, and what was done:
- An English question right after a Dutch turn was answered in Dutch: fixed, both ways
  (f739356). The pane's brief came in English on a Dutch turn: open, not in this flow.
- Colmenar's similar homes were the town's €160k houses: the structural branch's
  unguarded fallback is off by default in cleverdragon 4932e51a (STAGE now, PROD with
  the nightly release). Turn 8 opens the Málaga villa instead, whose matches are within
  5% on price.
- The description is collapsed (1d9d66c); the reply no longer scrolls the page and a
  down arrow shows while the end is out of view (9fcdf61), checked in Chrome.
- The Colmenar listing has no coordinates ("Map not available"); the Málaga villa has
  the map, that is why the pane is opened on it.
- X posts for Andalusia once included an unrelated political post; for Málaga they were
  about housing (rent decrees, a social-housing request).

## Messages to paste

```
                           ← wizard: By the sea → Anywhere in Europe → House, Townhouse →
                             Buy to live, Up to €700,000 → Garden & privacy ×2 → Search; then New chat
Wir ziehen um: Wohnung zum Kauf in Porto oder Valencia, bis 400.000 €, mindestens 2 Schlafzimmer
Compare schools and public transport in Porto and Valencia
What does 400k buy in Lisbon vs Porto? 2-bed flats
                           ← click "And up to €500,000?"
                           ← click "Compare #… and #… feature by feature"
Has #1's price dropped, and what's new in Lisbon?
Come posso contattare l'agente per il #1?
```

Six languages (en, pt, es, fr, de, nl) run natively. Any other is named and translated
to English by Nemotron, run, and translated back (`agent/pivot.py`): about 1.5–4 s
more per turn. Italian is the filmed example because the demo has Italian listings
too; the card numbers and the sign-in link survive the translation.

## YouTube

**Published Oct 29, 20:50 UTC, as Public: https://www.youtube.com/watch?v=Xbn-tKv-FDA** (2:34,
the owner's cut from the Oct 29 takes, 1918×870 HEVC source, "not made for kids",
copyright check clean). The link is in the Devpost draft's "Demo video URL" field.
An earlier 8.6 MB test upload of the same cut stays private on the channel.

- **Title:** Cubi Agent: cross-border home search on NVIDIA Nemotron and Nebius
- **Description:**

  > Start from pictures — the feel of a place, a country, the kind of home, your plan
  > and budget — or ask in any language for homes anywhere in Europe, then dig into them:
  > compare the top home in each city feature by feature, with environmental data;
  > see what your budget buys city by city; check a home's price history and the
  > latest local news; compare schools and transport with cited sources; contact the
  > agent through a consented flow. Built on NVIDIA Nemotron 3 Super via Nebius Token
  > Factory, hosted on Nebius AI Cloud, with Tavily and Cubi Estate's listing connector.
  > Live demo: https://www.cubi.estate/agent · Code: https://github.com/cubi-estate/cubi-agent
  > Nebius × NVIDIA Global AI Hackathon, Best Apps and Agents.

- Visibility **Public**, and "not made for kids".
- The code link resolves: the repository has been public (Apache-2.0) since Oct 29, so
  the description, card 4's "open source" line and the Devpost links all point at a
  page anyone can open. Nothing in the video needs redoing for it.
- No end screens that link off YouTube.
