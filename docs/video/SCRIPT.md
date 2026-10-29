# Demo video: script and shot list

Target **2:52** (the limit is 3:00). One screen recording of the live demo (the
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

   Also walk the wizard once on the day, in a new chat: **By the sea → Portugal →
   House and Townhouse → Buy to live, Up to €700,000 → Garden & privacy twice (must-have)
   → Search.** Expect a brief with "a sea view" and "must have: garden & privacy" under
   *Filters* (a picked landscape filters — Cubi's free-text search ignores an "ideally"
   wish when ranking, live 2026-10-25), then about 400 homes in under 10 s, a chip line
   "for sale · house/townhouse · ≤ €700,000 · Sea View + Garden · in Portugal" and never
   "all have a garden" (a guard drops that). If the count is small, a listings change
   has made Garden rare: pick Terrace instead and read the brief aloud as it stands.

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

Not yet recorded: **Homes like this one** in the pane and the two similar-homes buttons,
which wait for the connector release of Oct 30; if filmed, redo shot 7b after the
morning check.

## Shots

| # | Time | Picture | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:12 | Card 1 (problem) | Moving from Germany, torn between Porto and Valencia? That's two countries, two languages and a handful of portals that don't talk to each other. |
| 2 | 0:12–0:25 | Card 2 (how it's built) | Cubi Agent is one conversation over two point three million listings in twenty European countries. NVIDIA Nemotron 3 Super, on Nebius Token Factory, reads the request and writes the answer; the app runs on Nebius AI Cloud. |
| 3 | 0:25–0:37 | New chat. Tap By the sea → Portugal → House, Townhouse → Buy to live, Up to €700,000 → Garden & privacy twice; hold a beat on the brief, then Search | No typing to start with: pick a feeling, a country, a kind of home, a plan and a budget, and what matters. The brief under the pictures says what filters, what is only a wish and what is still open — and the search is one plain sentence. |
| 4 | 0:37–0:59 | Click New chat, paste turn 1, let the steps stream, scroll over the six cards, end on the three buttons | Or ask in German: a flat to buy in Porto or Valencia, up to four hundred thousand, two bedrooms at least. *(pause on the step log)* Nemotron turns that into a structured filter; code checks it, and the agent searches each city separately. Every card comes from Cubi's data, not from the model. |
| 5 | 0:59–1:21 | Paste turn 2, then scroll to the Sources list | Then the question a mover actually has: what are the schools and public transport like? The agent searches the web with Tavily, one search per city and topic, and writes the two cities side by side. Every point carries a numbered source, linked in code, and where no source covers a topic, it says so. |
| 6 | 1:21–1:41 | Paste turn 3: bars grow. Click "And up to €500,000?": bars move, markers stay at the old shares | And from Cubi's own data: what does four hundred thousand buy in Lisbon versus Porto? *(read the two shares on screen)* Raise it to five hundred, and the bars move from the old shares. Cubi counted these; the model only wrote the sentence around them. |
| 7 | 1:41–2:01 | Click "Compare #… and #… feature by feature"; scroll the table slowly | Now the top home in each city, feature by feature: the asking price, what each listing states, and Cubi's area data — noise, air quality, flood and wildfire screening from European open data. Where a listing doesn't say, the table says "not stated", never "no". |
| 7b | 2:01–2:17 | Tap card #3 in a Lisbon search (or the top card of the budget scene): the pane opens on the right — brief, highlights, *Check before deciding*, neighbourhood line, the map with its pins — and the chat gets the home's line and its buttons; scroll the pane to the map | Tap a card and the home opens in full: Nemotron's brief in your language, what to check before deciding, Cubi's area data, and a map of what's nearby from OpenStreetMap. The tap also writes the home into the chat, with every question you can ask about it as a button. *(Recorded Oct 29: Ameixoeira flat, "No lift mentioned", "No mention of energy class", pinned at the listed address with 64 places nearby, four buttons. Once the connector release lands, the pane also lists up to three similar homes and the buttons grow to six — see the paragraph below.)* |
| 8 | 2:17–2:33 | Paste turn 6 (or click it if offered); hold on the three-sentence answer, then scroll past the price box to the sources and the three posts from X | Has this Lisbon flat's price dropped, and what's new there? Three sentences: Cubi's price log *(read it, e.g. "no change since September")*, the housing news with its sources, and what people post on X — the sources and the posts sit underneath, each with a link. *(Live Oct 26 on builds eb53519 and c95c8b6, same answer: the Lisbon housing protests — Yahoo and The Jerusalem Post on the Oct 17 march, Reuters on the Oct 20 camp clearance — [S1]–[S3], and three posts from X dated Oct 20–25 [X1]–[X3]; 2–6 s. Lisbon has enough reporting of its own, so no regional fallback fires here. Since build 46a2c7c a place-only question — "What's new in Nazaré, Leiria" — is about that place: no card, no price box, news and posts for the town; off the filmed path. Since c95c8b6 a small town falls back to its region's housing news, labelled as such — Nazaré answers with Leiria's price rise and says nothing town-specific was found.)* |
| 9 | 2:33–2:44 | Paste turn 7 (in Italian), hold on the Italian answer, then highlight the sign-in link | Ask in Italian, or any language: Nemotron translates in and out. And contacting the agent goes only through Cubi's consented flow; the demo sends nothing for you. |
| 10 | 2:44–2:56 | Card 3 (results) | Measured on thirty-six requests in six languages the rules never saw, Super got every field right. Against Cubi's own search, the agent is four times faster on a tenth of the quota, at similar precision. |
| 11 | 2:56–3:00 | Card 4 (try it) | Try it at cubi.estate/agent, no account needed. The agent, the evals and our feedback for Nebius and NVIDIA are open source. |

With shot 7b that is about 460 words, which fills the 3:00 limit; the Oct 29 draft cut (`~/Downloads/cubi-agent-demo.mp4`, synthesized voice, eight recorded clips and the four cards) runs 2:53. To buy room, trim the table scroll in scene 7 (its table showed only price, size and climate on Oct 29) before anything else (the clicks and scrolls need room); the limit is 3:00. If the takes run
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

Not filmed, in the app since Oct 26 evening: **tap a card** and the home opens in a pane on the right (full screen on a phone) — Nemotron nano's brief in the user's language (in short, highlights, things to check before deciding, e.g. "Needs renovation", "Energy class F"), Cubi's surroundings profile (noise, air, flood, wildfire, seismic; minutes on foot to a supermarket, school, park; climate; €/m²), the agency's description and every tag by section; about 2 s. Photos are held for now: Cubi's connector sends no image list, so the pane says so and links to the listing page. Checked live in Chrome on Oct 26 (build 7063166): on "Houses to rent with a mountain view and near a lake, anywhere in Europe" every card lit **Mountain view**, and tapping #4 (a Fundão house) opened the pane in 2 s with "Ground floor", "No lift" and "High fire-weather risk (62 days/yr)" under *Check before deciding*, the coast 116 km away, a school 15 min on foot. Since the same evening the pane also has a **map**: the listing's address line geocoded on OpenStreetMap (the street or the named place when the listing gives one, else the town centre — the caption says which; Cubi's connector shares no coordinates) with the home pinned and places nearby from OpenStreetMap as pins (supermarkets, schools, parks, stations, pharmacies, restaurants; one category a second, so the pins land one kind at a time over about eight seconds, and the view then zooms to fit the home and every pin). The caption reads e.g. "Pinned at the listed address · 67 places nearby from OpenStreetMap". Checked live on Oct 26 (build 94d8af8): the Carnide flat (#5 of the "2-bed apartment in Lisbon under 450k" example) pinned at Quinta do Bom Nome, with the Pontinha and Carnide metro stations, a supermarket and a school in view. If filmed: tap the card, let the brief land (2 s), scroll to the map and wait for the pins — about ten seconds in all, so it only fits a spare beat in turn 7 or 8. Since Oct 29 (agent 5ecef8a → 0c7be46) the pane also carries **Homes like this one**: up to three homes in the same market picked by Cubi's similarity model — a 50-dimension PCA embedding of each listing's catalogued features, nearest neighbours, then a ranker on stated features, size, place and asking price — each as a small card with the ranker's own reason ("same city · within 7% on price", "€169,000 more · similar size (108 m²)") and a line saying how they were picked. It reads the connector's new `find_similar_homes` tool (cleverdragon 373a5c97 → d9eb1ee4: engine unhydrated, cards from one key lookup, 12 s budget → 504, so the pane leaves the section out rather than wait). Checked on STAGE Oct 29: a Famalicão house seed answered with three PCA-ranked matches; a Warsaw seed hit the budget on STAGE's saturated database (the same query runs in 0.25–0.5 s on PROD). The tool reaches Cubi's production connector with the nightly release of Oct 30 (about 07:30 UTC); until then the section stays out and the rest of the pane is unchanged. If filmed: it sits right under *Neighbourhood & environment*, before the map, and lands with the brief (about 2 s on PROD) — tap the card, read the brief, then point at the three small cards and their reasons; about 6 s, so a spare beat in turn 7 or 8, and only after the morning check that a tapped Lisbon card shows matches. Since Oct 29 afternoon (agent 9f316af → 1faa1e0, live 14:18 UTC) the tap also writes a line into the chat — "#1 · Casa · Cascais, Lisboa · afinest_pt:25505032" — followed by every question the app can answer about that home as buttons: *Compare #1 with its similar homes feature by feature* (code pairs the home with each pane pick, one connector read each in parallel, one merged table; the similar homes become the next cards), *Has #1's price dropped, and have its similar homes' prices dropped?* (price-history reads for all of them, prices only), *Is #1's price in line with similar homes?*, *Show me homes like #1 in Porto* (after a one-city search the country's other big market, never the card's own city), *What's new in Cascais?* and *How do I contact the agent for #1?*. Questions already asked or answered in the chat are not offered again. The first two need the similar homes, so until the connector release of Oct 30 they give way to the plain price-and-news question: checked live Oct 29 on a Portuguese Cascais search (four chips, in Portuguese) and on an English Lisbon search (the price chip answered in 5 s with the home's 4.1% drop). If filmed, this is the strongest 15 s of the pane: tap the card, let the chat line and the buttons land (about 2 s), press *Compare #1 with its similar homes feature by feature* and let the table come (about 4 s) — then the three similar homes are cards too, and the next buttons are about them. Record it only after the morning check that a tapped Lisbon card shows matches and six buttons. In the six languages the buttons are native; in any other they are translated once by Nemotron.

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

## Messages to paste

```
                           ← wizard: By the sea → Portugal → House, Townhouse → Buy to live,
                             Up to €700,000 → Garden & privacy ×2 → Search; then New chat
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
- No end screens that link off YouTube.
