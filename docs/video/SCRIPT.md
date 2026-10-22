# Demo video: script and shot list

Target **2:53** (the limit is 3:00). One screen recording of the live demo, four
title cards from `slides.html`, and a voice-over in English. No music, or only
music you have the rights to. Upload to YouTube as **Public** and put the link in Devpost.

## Before recording

1. **Rehearse against the live demo** the same day:
   `python scripts/demo_rehearsal.py --show-text`. You want
   - 6 cards, 3 per city, on turn 1;
   - no `! error` lines;
   - turn 3 with `[S1]`-style links and a **Sources** list;
   - turns 4 and 5 with a `▮` line per city, and "(was …%)" on turn 5.

   Results change as listings change. Note which home is #2 and what its price check
   says, and fix the voice-over line in scene 4 to match.
2. **Browser:** a clean profile, no extensions or bookmarks bar, light mode, window
   1920×1080, zoom 125%. Open https://www.cubi.estate/agent and click **New chat**.
3. **Don't open "Open listing" on camera.** It leads to the portal's page, with its
   logo and photos (plan §4: no portal marks or listing photos). The cards
   themselves show no photos.
4. **Typing:** paste each message, don't type it. Keep the step log open during turn 1
   (it opens by default) and let it collapse on its own.
5. **Slides:** open `docs/video/slides.html` in a second window and press F for full
   screen, H to hide the key hint, and → to advance.

## Shots

| # | Time | Picture | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:15 | Card 1 (problem) | Say you're moving from Germany and can't decide between Porto and Valencia. That's two countries, two languages and a handful of property portals that don't talk to each other. |
| 2 | 0:15–0:30 | Card 2 (how it's built) | Cubi Agent is one conversation over two point three million listings in twenty European countries. NVIDIA Nemotron 3 Super, served by Nebius Token Factory, reads the request and writes the answer. The app runs on a Nebius AI Cloud endpoint. |
| 3 | 0:30–1:05 | Demo. Paste turn 1, let the steps stream, scroll slowly over the six cards | I'll ask in German: an apartment to buy in Porto or Valencia, up to four hundred thousand euros, two bedrooms at least. *(pause on the step log)* Nemotron turns that into a structured filter. Code checks it, and the agent searches each city separately, so both get results. Every card comes from the search result, not from the model, and links to the original listing. The model only writes the short summary above them. |
| 4 | 1:05–1:30 | Paste turn 2, then highlight the band sentence and the "not a valuation" line | Now in English: is number two overpriced? Code works out which home "number two" is and asks Cubi how its asking price compares with similar homes nearby. *(read the result, e.g. "below the typical range of 20 comparables")* It's a comparison of asking prices, not a valuation, and the app always says so. |
| 5 | 1:30–2:00 | Paste turn 3, then scroll to the Sources list | Then the question a mover actually has: what are the schools and public transport like? The agent searches the web with Tavily, one search per city and topic, and writes the two cities side by side. Every point carries a numbered source, the links are added in code, and the dated ones say when they're from. |
| 6 | 2:00–2:18 | Paste turn 4: bars grow. Click "And up to €500 000?": bars move, markers stay at the old shares | And the buying question, from Cubi's own data: what does four hundred thousand buy in Lisbon versus Porto? *(read the two shares on screen)* Raise it to five hundred, and watch Porto's share move. Cubi counted these; the model only wrote the sentence around them. |
| 7 | 2:18–2:28 | Paste turn 6, then highlight the sign-in link | How do I contact the agent? Only through Cubi's consented contact flow. The demo sends nothing on your behalf. |
| 8 | 2:28–2:45 | Card 3 (results) | We measured it on thirty-six requests in six languages that the rules never saw. Super got every field right on all thirty-six. Compared with sending the same request straight to Cubi's own search, the agent is about four times faster and uses a tenth of the quota, at similar precision. |
| 9 | 2:45–2:53 | Card 4 (try it) | Try it at cubi.estate/agent. No account is needed. The agent, the evals and our feedback for Nebius and NVIDIA are open source on GitHub. |

That's about 400 words, or 2:50 at a calm pace; the limit is 3:00. If the takes run long,
cut scene 7 to its first sentence. In scene 6, read the shares the bars show on the day:
they change as listings change (on 2026-10-22: Lisbon 9.6% → 16.8%, Porto 30.3% → 57.5%).
Don't add "with parking": whether a listing records parking depends on the agency that
published it, so the agent doesn't compare it.

### Optional, if there's time to spare

Run the same German query in Claude with the Cubi Estate plugin. It uses the same
skill files, and that shows they're portable. Only add it if the cut stays under 3:00.

## Messages to paste

```
Wir ziehen um: Wohnung zum Kauf in Porto oder Valencia, bis 400.000 €, mindestens 2 Schlafzimmer
Is #2 overpriced?
Compare schools and public transport in Porto and Valencia
What does 400k buy in Lisbon vs Porto? 2-bed flats
And up to 500k?            ← or click the "And up to €500 000?" button
How do I contact the agent for #2?
```

## YouTube

- **Title:** Cubi Agent: cross-border home search on NVIDIA Nemotron and Nebius
- **Description:**

  > Ask in your own language for homes anywhere in Europe, then ask about one: its
  > price against similar homes, the area's schools and transport, how to contact the
  > agent. Built on NVIDIA Nemotron 3 Super via Nebius Token Factory, hosted on Nebius
  > AI Cloud, with Tavily for cited area research and Cubi Estate's listing connector.
  > Live demo: https://www.cubi.estate/agent · Code: https://github.com/cubi-estate/cubi-agent
  > Nebius × NVIDIA Global AI Hackathon, Best Apps and Agents.

- Visibility **Public**, and "not made for kids".
- No end screens that link off YouTube.
