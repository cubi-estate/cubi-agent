# Demo video: script and shot list

Target **2:50** (the limit is 3:00). One screen recording of the live demo, four
title cards from `slides.html`, and a voice-over in English. No music, or only
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
   - turn 8 naming its number of comparables, with one "independent valuation" line
     and no "thin" when there are ten or more.

   Results change as listings change. Note the shares on turns 3–4, the card numbers
   turn 5 compares and what turn 6 says about the price, and fix those voice-over
   lines to match. The feature-by-feature scene comes after the budget on purpose:
   there the top homes are comparable Lisbon and Porto flats with full area data;
   straight after the German search they were a €350k flat 60 km from Porto (the
   search covers Porto district) against an €89k one, with sparse data.
2. **Browser:** a clean profile, no extensions or bookmarks bar, light mode, window
   1920×1080, zoom 125%. Open https://www.cubi.estate/agent and click **New chat**.
3. **Don't open "Open listing" on camera.** It leads to the portal's page, with its
   logo and photos (plan §4: no portal marks or listing photos). The cards
   themselves show no photos. Don't open the X link on camera either: it shows
   other people's posts.
4. **Typing:** paste each message, or click the suggestion button where the shot
   says so. Keep the step log open during turn 1 (it opens by default) and let it
   collapse on its own.
5. **Pace:** the demo allows 8 turns a minute per address. Seven filmed turns at a
   natural pace stay under it; don't rush the clicks.
6. **Slides:** open `docs/video/slides.html` in a second window and press F for full
   screen, H to hide the key hint, and → to advance.

## Shots

| # | Time | Picture | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:12 | Card 1 (problem) | Moving from Germany, torn between Porto and Valencia? That's two countries, two languages and a handful of portals that don't talk to each other. |
| 2 | 0:12–0:25 | Card 2 (how it's built) | Cubi Agent is one conversation over two point three million listings in twenty European countries. NVIDIA Nemotron 3 Super, on Nebius Token Factory, reads the request and writes the answer; the app runs on Nebius AI Cloud. |
| 3 | 0:25–0:52 | Paste turn 1, let the steps stream, scroll over the six cards, end on the three buttons | I ask in German: a flat to buy in Porto or Valencia, up to four hundred thousand, two bedrooms at least. *(pause on the step log)* Nemotron turns that into a structured filter; code checks it, and the agent searches each city separately. Every card comes from Cubi's data, not from the model. And every answer ends with the next questions worth asking, built from what's on screen. |
| 4 | 0:52–1:17 | Paste turn 2, then scroll to the Sources list | Then the question a mover actually has: what are the schools and public transport like? The agent searches the web with Tavily, one search per city and topic, and writes the two cities side by side. Every point carries a numbered source, linked in code, and where no source covers a topic, it says so. |
| 5 | 1:17–1:37 | Paste turn 3: bars grow. Click "And up to €500,000?": bars move, markers stay at the old shares | And from Cubi's own data: what does four hundred thousand buy in Lisbon versus Porto? *(read the two shares on screen)* Raise it to five hundred, and the bars move from the old shares. Cubi counted these; the model only wrote the sentence around them. |
| 6 | 1:37–2:00 | Click "Compare #… and #… feature by feature"; scroll the table slowly | Now the top home in each city, feature by feature. Same rows for both: the asking price, what each listing states, and Cubi's area data — noise, air quality, flood and wildfire screening from European open data. Where a listing doesn't say, the table says "not stated", never "no". |
| 7 | 2:00–2:18 | Paste turn 6 (or click it if offered); show the price box, then the cited news | Has this Lisbon flat's price dropped, and what's new there? Cubi's price log answers the first *(read it, e.g. "no change since September")*, and recent housing news answers the second, each point with its source. Posts on X are one click away. |
| 8 | 2:18–2:26 | Paste turn 7, then highlight the sign-in link | And contacting the agent goes only through Cubi's consented flow; the demo sends nothing on your behalf. |
| 9 | 2:26–2:42 | Card 3 (results) | Measured on thirty-six requests in six languages the rules never saw, Super got every field right. Against Cubi's own search, the agent is about four times faster and uses a tenth of the quota, at similar precision. |
| 10 | 2:42–2:50 | Card 4 (try it) | Try it at cubi.estate/agent, no account needed. The agent, the evals and our feedback for Nebius and NVIDIA are open source. |

That's about 380 words, or 2:30 of speech in a 2:50 cut (the clicks and scrolls need room); the limit is 3:00. If the takes run
long, cut scene 8. Read the figures the screen shows on the day — shares, card
numbers, the price line — they change as listings change. On 2026-10-22: Lisbon
6.3% → 12.2% and Porto 21.0% → 37.4% for 2+ bedroom flats.

Not filmed, still in the app (rehearsal turns 8–9): the price check against similar
homes ("Is #2 overpriced?": the range of asking prices and how many comparable homes
it rests on; with too few, one plain sentence saying there is no range, never a
verdict) and similar homes in another city ("Show me homes like #1 in Porto"). Don't add "with parking" anywhere: whether a listing records parking
depends on the agency that published it, so the agent doesn't compare it.

### Optional, if there's time to spare

**An honest "none" (about 8 s, in place of scene 8 if that is cut).** In a new chat,
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
Wir ziehen um: Wohnung zum Kauf in Porto oder Valencia, bis 400.000 €, mindestens 2 Schlafzimmer
Compare schools and public transport in Porto and Valencia
What does 400k buy in Lisbon vs Porto? 2-bed flats
                           ← click "And up to €500,000?"
                           ← click "Compare #… and #… feature by feature"
Has #1's price dropped, and what's new in Lisbon?
How do I contact the agent for #1?
```

## YouTube

- **Title:** Cubi Agent: cross-border home search on NVIDIA Nemotron and Nebius
- **Description:**

  > Ask in your own language for homes anywhere in Europe, then dig into them:
  > compare the top home in each city feature by feature, with environmental data;
  > see what your budget buys city by city; check a home's price history and the
  > latest local news; compare schools and transport with cited sources; contact the
  > agent through a consented flow. Built on NVIDIA Nemotron 3 Super via Nebius Token
  > Factory, hosted on Nebius AI Cloud, with Tavily and Cubi Estate's listing connector.
  > Live demo: https://www.cubi.estate/agent · Code: https://github.com/cubi-estate/cubi-agent
  > Nebius × NVIDIA Global AI Hackathon, Best Apps and Agents.

- Visibility **Public**, and "not made for kids".
- No end screens that link off YouTube.
