## Inspiration

Moving to another country means two languages, five property portals and a dozen questions no portal answers: is this price fair, what are the schools like, what does my budget buy in one city versus the next, how do I reach the agent without handing my phone number to a form. Cubi Estate already indexes 2.3M+ active listings across 20 European countries and exposes them through a public, read-only MCP connector. We wanted one conversation over all of it, in the buyer's own language, on open models. Our demo opens on a smaller version of the same question: a weekend house in the mountains, by a lake, in whichever country fits.

## What it does

**Cubi Agent** is a web chat at https://www.cubi.estate/agent (no account needed, free until the end of judging).

- **Pick pictures, not words.** A five-step wizard (a feeling, a country or all of Europe, a kind of home, rent or buy and a budget, what matters) ends in one plain sentence and a brief that says what filters, what only ranks, and what is still open.
- **Then narrow it in your own language.** Six languages natively (EN, PT, ES, FR, DE, NL); any other is pivoted through English and back. "Vamos limitar a pesquisa à Lombardia" keeps the search to rent; "What if I buy instead?" switches it, and the agent keeps that choice across the following turns. Nemotron turns the words into a structured filter, code checks it, and each place is searched separately.
- **Check the price.** Is this home priced in line with comparable homes in its city? The interquartile range of asking prices and how many homes it rests on; with too few, it says there is no range, never a verdict.
- **Find homes like it, there or abroad.** Cubi's similarity model (a 50-dimension embedding of each listing's catalogued features, nearest neighbours, then a ranker on stated features, size and place) matches on features and surroundings, never on price; the agent lays the asking prices side by side, in Málaga or in Lisbon, feature by feature, with "not stated" shown as such, never as "no".
- **Open a home.** Tap a card: Nemotron's brief in your language, what to check before deciding, Cubi's environment and walking-time data, homes like this one, a map from OpenStreetMap with what's nearby, and every question you can ask about that home as a button in the chat.
- **Ask about the place.** Schools and transport in two cities, each point linked to its web source; what's new in a town from Cubi's price log, Tavily housing news and recent posts on X.
- **Compare places with real data.** What €400k buys in Lisbon vs Porto, as the share of Cubi's priced listings within the budget, drawn as bars; raise the budget and the bars move from the old marks.
- **Reach the agent** only through Cubi's consented flow: questions via Cubi, Cubi Connect or an email request; no phone number or email on screen.

## How we built it

One open model does the language work: **nvidia/nemotron-3-super-120b-a12b** on **Nebius Token Factory** (OpenAI-compatible API) runs the tool loop, extracts the search filter under a strict JSON schema and writes the short answers; **Nemotron 3 Nano** writes the listing briefs. Thinking is switched off for these calls. The system prompts are the `SKILL.md` files of the Cubi Estate plugin for Claude, vendored as a pinned submodule, so the same skills drive Claude through the plugin and Nemotron here.

Code decides what the model should not: language detection, sale vs rent, feature names, which home "the second one" means, and whether a request needs the structured filter or Cubi's free-text search. Listing cards are parsed from the connector's replies, so the model cannot invent one. Deterministic guards run on every answer: every URL must appear verbatim in tool output, phone numbers and emails are scrubbed, "good deal / overpriced" verdicts are removed and a "not a valuation" line added, any claim of having contacted someone is dropped, and Tavily citations are linked in code.

The agent is a small FastAPI app (Python, no frontend build step, no external scripts) in a container built by GitHub Actions and hosted on a **Nebius AI Cloud serverless endpoint** in Paris. Tools: Cubi Estate's MCP connector (search, filter, listing, price comparison, price history, inventory shares, similar homes, contact options), Tavily for area questions, OpenStreetMap for the map.

## Results

- **Filter extraction, held-out set** (36 unseen requests, 6 per language, rules frozen before the run): Nemotron 3 Super got 148/148 fields and 36/36 requests right, p50 1.05 s.
- **Agent vs Cubi's own free-text search** (31 held-out requests): about the same precision (90% vs 94% of listings meeting every visible constraint), **4× faster** (p50 1.35 s vs 5.97 s) on **a tenth of the connector quota** (33 vs 310 units).
- **Answer audit**: 0 of 31 first turns needed a guard fix once cards came from code. Before that, one live German turn had invented three listings with plausible ids.
- 400+ offline tests; an uptime check every 30 minutes through judging.

## Challenges we ran into

- Nemotron's reasoning leaked into strict `json_schema` output until thinking was switched off; Nano then spent its whole budget thinking and returned nothing.
- Internal citation markup reached the answers in place of links, so sources are now numbered, the markup is read as a citation, and links are made in code.
- Short European queries defeat model language detection, so code does it.
- A country-wide search across all of Europe can exceed the connector's time limit; the agent now says so in advance and falls back to searching the largest markets side by side.
- Cubi's connector had no in-market similarity tool, so a read-only one was added upstream for the listing pane.

## What we learned

What open models do well, what to keep in code, and how to make an agent honest: render data from tools, not from the model, and guard every answer deterministically. Thirteen concrete findings on Token Factory, Nemotron and Nebius AI Cloud, each with the workaround and what would have helped, are in the repository's `docs/FEEDBACK.md`.

## What's next

The production build for cubi.estate: the wizard in seven languages with a persisted brief, photo-to-home search (a vision spike with Nemotron 3.5 Super VL passed every gate), and the X posts feed once its legal review is done.

## Note for judges

The agent, the web app, the evals and the skill pack are open source (Apache-2.0). The live listing service behind it, Cubi Estate's connector, is a separately maintained production service and keeps improving during judging; the demo is pinned to the submitted agent build.

---

# Additional info (judges and organisers, not public)

Answers entered on Oct 29. Ratings are proposals for the owner to adjust.

**Which model(s) did you use, and why that size/variant?**
nvidia/nemotron-3-super-120b-a12b (Nemotron 3 Super) for the tool loop, the strict-schema filter extraction and the short answers: on our held-out set it got 148/148 fields and 36/36 requests right at about 1 s per extraction with thinking off, and it is the largest Nemotron we could run at that latency and price (about $0.13 per 1,000 extractions). nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B for the listing briefs in the pane, where speed matters and the input is one listing; Nano is not used for extraction because it read "até 750€" as 75,000 in Portuguese. We also evaluated Nemotron 3 Ultra 550B and Nemotron 3.5 Lightning: both matched Super on the held-out set, Lightning at half the latency; we would switch to Lightning with a published price and region. Nemotron 3.5 Super VL passed a photo-to-home spike (14/14 inspiration images matched in 1.5 s) and is next.

**Output quality (1–10):** 8. Instruction following and structured output were excellent once thinking was off (36/36 held-out extractions in six languages, tool calls 3/3 on every model). What fell short: reasoning text leaking into strict json_schema fields with thinking on; internal citation markup (【…】) written in place of links; language drift when tool results are in English (a German question answered in English, one Spanish word in a German answer); unreliable language detection for short European queries; and answering a repeated question from history without calling the tool. Each has a code-side fix in the repository and a write-up in docs/FEEDBACK.md.

**Fine-tune, prompt-engineer or out of the box?**
Out of the box, prompt-engineered, with deterministic code around it. The system prompts are the SKILL.md files of the Cubi Estate plugin for Claude, vendored as a pinned submodule, so the same skills drive Claude and Nemotron. Thinking is switched off for every call (chat_template_kwargs.enable_thinking=false). Code owns what the eval showed the model gets wrong systematically: language detection, sale vs rent, feature names, which card "the second one" means, and the structured-vs-free-text routing; a normaliser fixes each systematic extraction error; guards check every answer (URLs must appear verbatim in tool output, contacts scrubbed, price verdicts removed, citations linked in code). Fine-tuning was not an option: Token Factory's fine-tuning lists Qwen, Llama, Gemma and DeepSeek, not Nemotron.

**Compared to other models?**
On this task Super matches what we get from the closed models Cubi uses in production for filter extraction (Cubi's own search runs on OpenAI): same held-out accuracy, lower latency (p50 1.05 s), far lower cost, and the agent path over Nemotron is 4× faster than sending the same request to Cubi's own free-text search (p50 1.35 s vs 5.97 s) on a tenth of the connector quota. The differences are around the edges: citation conventions, language stability in mixed-language context and the thinking default all needed code we did not need with the closed models.

**Most valuable Nebius capabilities?**
Token Factory's OpenAI-compatible API (json_schema strict and tool calls worked first time on all four models, so the OpenAI SDK was the only client), the model catalogue (four Nemotron sizes to evaluate side by side in one afternoon), and Nebius AI Cloud serverless endpoints for hosting: one command, a public GHCR image built by GitHub Actions, --auth none, secrets from MysteryBox, a managed HTTPS URL in minutes, CPU-only (the app needs no GPU; inference is on Token Factory). The demo at cubi.estate/agent redirects to the endpoint; restarts take seconds to a few minutes. The endpoints were restarted after the eMudhra advisory, and the image's CA bundle rejects the compromised chains.

**Recommend Nemotron on Nebius (1–10):** 8. Fast to start, cheap, and the API behaves like the one every team already knows. Reasons for not 10: the EU-region question (only Nano was served in an EU region; region decides GDPR posture for a European app, and we had to infer it), and two onboarding traps (two tenants behind one login with no hint, and "permission denied" errors that really meant "billing not activated").

**Experience vs previous environments (1–10):** 8. Better than running the models locally (no GPU to manage, four sizes on tap) and on par with the closed APIs we use otherwise. Serverless endpoints have no in-place image update, so the public URL changes on every redeploy (we put a stable redirect in front), --description is not accepted on endpoint create, and the docs do not say whether the proxy sets X-Forwarded-For (it does).

**What would have made it more effective?**
Default thinking off when response_format is a strict json_schema, or keep reasoning out of constrained fields, and say so on the model card; a documented citation convention; a region column on the catalogue page; Nemotron in Token Factory fine-tuning; a published price for Nemotron 3.5 Lightning; in-place image updates for serverless endpoints; a "billing not activated" error instead of PermissionDenied; and a non-zero default CPU quota in eu-north1.

**Most hope to see next from the Nemotron team?**
An EU-served Super or Lightning; guidance on keeping the response language stable when the context mixes languages (the normal case for European agents); a stronger small model for numbers in non-English text (750€ is not 75,000); and vision at Lightning speed, since photo-to-home search worked in our spike.

**Did you use Tavily?** Yes: a runtime call per place and topic for area questions (schools, transport, local housing news), one search per city and topic, with exclude_domains to drop social posts; citations are numbered and linked in code.

**Which AI tools did you use while building?**
Claude Code (Fable 5.1) as the coding agent for the whole build, with Cubi Estate's own MCP connector and a Perplexity-backed research agent for web questions; OpenAI gpt-image-2 for the fourteen AI-generated inspiration images in the wizard (Token Factory serves no image model); Nemotron itself for the eval runs.

**Level of learning:** Significant. **AI value for your career:** Yes.

**Left for the owner:** submitter type and organisation name, country of residence, the Canada province field ("N/A"), the two attestations (age of majority, not an employee of the promotion entities), the IRL city (optional), and the demo video URL on the Project details step.
