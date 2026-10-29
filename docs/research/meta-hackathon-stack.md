# Meta Global AI Developer Hackathon: stack research for ConformScope

Researched 2026-10-29 against primary sources: Cerebral Valley event pages, the Official Rules, Meta Model API docs (dev.meta.ai), the facebookresearch/sam3 GitHub repo, and the Hugging Face, Baseten, Fireworks and Modal docs. Each fact links to its source. **[Inferred]** marks my own reasoning, not something a source states. "Not found" means I looked and the primary sources don't say.

---

## TL;DR

- **Deadline:** Wed **Nov 4, 9:00 PM ET**. That is **Thu Nov 5, 03:00 in Tunisia** (UTC+1), because US DST ends Nov 1, so ET is UTC-5 on Nov 4 ([participant guide][guide]; [event page][event-md] also says "submissions due Nov 5, 2026 UTC"). The $150 Meta credit claim closes at the same moment ([guide][guide]).
- **Submission:** a **public repo**, a **3-minute demo video**, and the live product, submitted through the CV portal ([guide][guide]; [Official Rules][rules]). The video is "one of the primary artifacts" judges use ([guide][guide]).
- **Judging:** Stage 1 is pass/fail: does the project fit a theme, and did it "reasonably" use Meta Model API and/or Meta open-weight models. Stage 2 scores each criterion 0–10: **Impact 30%, Use of Meta AI Tooling 25%, Technical Depth & Execution 20%, Demo 25%**. Stage 3: the top 5 per track are ranked live from their videos ([guide][guide]; [rules][rules]).
- **Biggest risk: "New work only."** Anything you present must have been built during the event. Only **startups** may build on an existing codebase, and they must say what is new. If you don't clearly identify your original contributions, judges can disqualify the project immediately ([guide][guide]). For an Indie entrant, porting the old `pmr-checker` code into the demo is risky. **[Inferred]** Build fresh in the new ConformScope repo, and say in the README exactly what was built Oct 26 – Nov 4.
- **Anti-project list** includes "Simple Image Analyzers" and "Basic RAG Applications" ([guide][guide]). **[Inferred]** Frame ConformScope around the agentic pipeline (segment, then simulate a wheelchair, then explain, then correct with a human in the loop), not "AI reads a plan".
- **Meta Model API** is OpenAI-compatible at `https://api.meta.ai/v1` (Bearer key, env var `MODEL_API_KEY`) and Anthropic-Messages-compatible at `https://api.meta.ai` ([SDKs][sdks]; [auth][auth]). Model IDs: `muse-spark-1.3`, `muse-wonder-1.0`, `muse-image-1.0`, `sam-3.1` ([models][models]). It supports images and PDFs, schema-constrained JSON, tool calling and a 1,048,576-token context ([models][models]; [structured output][so]).
- **SAM 3.1 is hosted on the Meta Model API** (`sam-3.1` on `/v1/responses`). It takes a text noun phrase **or** box/point prompts, returns boxes plus pixel masks, and costs $2.50 per 1,000 images ([SAM overview][sam-ov]; [pricing][pricing]). **[Inferred]** This makes Modal unnecessary for SAM on images. Modal becomes an optional extra.
- **Open-weight models** are "Muse Spark Open" (816B MoE with 42B active, Muse Model License) and "Muse Glimmer" (30B dense, Apache-2.0) ([Muse Spark Open][mso]; [Glimmer][glimmer]). There is a **$10K bonus for "Best Build on Meta Open Weight Models"** ([guide][guide]).
- **Baseten:** for the hackathon, use model **`meta-models/muse-spark-open-1026`**, not the documented `meta-models/muse-spark-open` ([guide][guide]). Baseten's Muse Spark Open does **not** support structured outputs or JSON mode. Tool calling is supported ([Baseten Model APIs][bt-ov]).
- **Fireworks:** Muse Spark Open runs serverless as `accounts/fireworks/models/muse-spark-open` ([Meta deploy][mso-deploy]). **Muse Glimmer 30B SFT is free on Fireworks until Nov 30, 2026** ([FW models][fw-models]). That makes it the cheapest way to "fine-tune on auditor corrections". Serving a tuned model needs a dedicated deployment ([FW SFT][fw-sft]).

---

## 1. The hackathon

### What it is
- Virtual and worldwide. Ten days, $1M in prizes, two tracks ([event page][event-md]).
- **Indie track:** "individual builders and students, teams of up to four" ([rules][rules]). Judged on "creativity, technical ambition, and whether it works" ([event page][event-md]). Solo entrants are allowed ([guide][guide]).
- **Indie prizes:** $150K, $100K, $75K, $50K, $25K. **Bonus prizes ($50K total):** Most Viral on X $20K; Best Build on Meta Open Weight Models $10K; Community Vote $10K; Best Agentic Use-Case $5K; Best Creative Build (Muse Image or Muse Wonder) $5K ([guide][guide]).
- **Themes:** "Build for Your World" or "Push the Frontier" ([guide][guide]). **[Inferred]** ConformScope fits "Build for Your World".

### Official Rules
- The Official Rules are on the **waiver page**, titled "Hackathon Terms & Conditions ('Official Rules') and Event Waiver" and dated **Oct 25, 2026** ([rules][rules]). The page is JS-rendered, so I read it in a browser. The event page still says the rules "will be published before the Hackathon begins" ([event page][event-md]).
- Participants need to be 18 or older ([rules][rules]). **Tunisia is not on the excluded list**, which names Belarus, China, Russia, Ukraine, Syria, Crimea, Donetsk, Luhansk, Cuba, North Korea and Iran ([rules][rules]). It is also not a Restricted Territory under Meta's Model API Geographic Use Policy. The only per-model country restriction there is Muse Image in India ([geo policy][geo]).
- **Submission ownership:** you keep your IP, but you grant the organizers a perpetual, royalty-free licence. You must warrant that the work is original and owned by you. Open-source components are fine if their licences are followed and your project "enhances or builds upon" them ([rules][rules]).
- **Confidentiality:** "Materials" you share are **not confidential** ([rules][rules]). **[Inferred]** Don't put private client plans (eval/private) in the repo or the video.

### Submission requirements
| Item | Requirement | Source |
|---|---|---|
| Portal | `https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit` | [rules][rules] |
| Repo | "Repositories must be public" | [guide][guide] |
| Video | **Three-minute** demo video showing only what you built during the hackathon. Make sure the link is accessible. | [guide][guide] |
| Team | Everyone who worked on the project is listed. A solo entrant is their own Representative. | [guide][guide], [rules][rules] |
| Live product / deploy link | Judges use "your code and live product", and Demo asks "Does the product hold up live?" A deploy URL is not named as a separate field. | [guide][guide] |
| Description | The exact form fields were **not found** (the portal is behind login). | — |
| Viral bonus | Post the demo on X and submit the post link. Engagement counts until Nov 8 EOD. | [guide][guide] |

### Pre-existing code and ideas
- "**New work only:** What you present at this Hackathon must have been built during the event… Startups may build on existing products or codebases, but you must clearly identify what was newly developed" ([guide][guide]).
- "**Demo requirements:** Your demo must only highlight the specific features, code, and functionality that you built during the Hackathon… Failure to clearly identify your original contributions will result in immediate disqualification" ([guide][guide]).
- An existing *idea* is not forbidden. The rule covers code and features ([guide][guide]). **[Inferred]**
- The rules allow third-party technical help and open-source components ([rules][rules]). **Not found:** any explicit rule on AI coding tools.

### Is using Meta models required?
- Yes. "Your project must incorporate Meta's models", and Stage 1 is pass/fail on whether the project "reasonably used Meta Model API and/or Meta's open-weight models" ([guide][guide]). No minimum amount is stated.
- Use of Meta tooling is 25% of the score, and judges ask whether you went "beyond a basic integration" ([guide][guide]). **[Inferred]** Give several Meta models distinct jobs: Muse Spark for perception and explanation, SAM 3.1 for masks, Muse Spark Open or Glimmer as the verifier or fine-tuned model, Muse Code as the dev agent.

### Deadlines in ET and Tunisia time (UTC+1, no DST)
US DST ends Sun **Nov 1, 2026**. Before that ET = UTC-4 (Tunisia is 5 h ahead of ET). From Nov 1 ET = UTC-5 (Tunisia is 6 h ahead). Times are from [guide][guide]; the conversion is mine.

| Event | ET | Tunisia |
|---|---|---|
| Fireworks workshop (Sinan Ozdemir) | Fri Oct 30, 12:00–12:30 PM EDT | Fri Oct 30, 17:00–17:30 |
| Discord office hours (weekdays) | 10–11 AM ET | 15:00–16:00 until Oct 30; **16:00–17:00 from Nov 2** |
| Last full day for submission questions | Tue Nov 3 | Tue Nov 3 |
| **Submissions due + credit claim deadline** | **Wed Nov 4, 9:00 PM EST** | **Thu Nov 5, 03:00** |
| Judging | Nov 5 – Nov 8 | — |
| Closing ceremony / finals | Mon Nov 9, 12:00 PM EST | Mon Nov 9, 18:00 |
| Community vote winner | Mon Nov 16 | — |

### Credits
- **Meta:** $150 in Model API credits per accepted participant, valid for the 10-day window ([rules][rules]). Claim through a Google Form. A **credit card must be on the account** and you will see a temporary pre-authorization charge. Set a Spend Limit on the Billing page. Claim by Nov 4, 9 PM ET ([guide][guide]).
- **Baseten:** $100 plus a 2M TPM limit, for up to 2,000 participants, reviewed by use case and granted per individual ([guide][guide]).
- **Modal:** $100 for the first 1,000 participants ([guide][guide]).
- **Fireworks:** $100 for "a shortlist of select teams" ([guide][guide]).
- None of the partner credits are guaranteed ([guide][guide]).

---

## 2. Meta Model API

### What it is
Meta's hosted API for Muse Wonder, Muse Spark, Muse Image, Muse Voice Transcribe and SAM 3.1. It offers three wire formats (Responses, Chat Completions, Messages) on the same models with the same auth ([models][models]; [protocols][protocols]).

### Access, keys, base URL, auth
- Create a key in the Model API dashboard at dev.meta.ai under **API keys → Create API key**. Keys start with `LLM_` and are shown only once ([auth][auth]).
- Auth header: `Authorization: Bearer $MODEL_API_KEY` ([auth][auth]).
- **OpenAI-compatible base URL:** `https://api.meta.ai/v1` ([SDKs][sdks]). Use the `openai` package on Python or npm. **No SDK reads `MODEL_API_KEY` on its own**, so pass it explicitly ([auth][auth]).
- **Anthropic Messages-compatible:** `base_url="https://api.meta.ai"`, with the key passed as `auth_token`. Responses start with a `redacted_thinking` block, so read the `text` blocks ([SDKs][sdks]).
- **Claude Code setup:** `ANTHROPIC_BASE_URL="https://api.meta.ai"`, `ANTHROPIC_AUTH_TOKEN="$MODEL_API_KEY"` ([coding agents][coding]). Per the Meta developer console's Start building panel (seen 2026-10-29), the model env vars are set to `muse-wonder-1.0`.
- **Codex:** `base_url = "https://api.meta.ai/v1"`, `env_key = "MODEL_API_KEY"`, `wire_api = "responses"` ([coding agents][coding]).
- **Muse Code uses a different env var: `META_API_KEY`** ([Muse Code auth][mc-auth]).
- Keys on the same team share rate limits. Keep keys server-side ([auth][auth]).

### Model IDs ([models][models])
| Model | ID | In → Out | Context |
|---|---|---|---|
| Muse Spark 1.3 (recommended) | `muse-spark-1.3` (cheap Contributor variant: `muse-spark-1.3-contributor`) | text/image/video/audio/PDF → text | 1,048,576 |
| Muse Spark 1.2 / 1.1 | `muse-spark-1.2`, `muse-spark-1.1` | same | 1,048,576 |
| Muse Wonder (preview) | `muse-wonder-1.0` | same | 1,048,576 |
| Muse Image | `muse-image-1.0` | text+image → image | — |
| SAM 3.1 | `sam-3.1` | text prompt + image/video → boxes and masks | — |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0` | audio → text | — |

Contributor mode means "your content may be used to train future Meta models" ([models][models]). **[Inferred]** Don't send client plans through `-contributor` models.

### Image and PDF input
- Send images as a URL, a base64 `data:` URL, or a Files API `file_id`. Formats: jpeg, png, gif, webp. Up to **50 images per request** and 50 MB per inline image ([image understanding][img]).
- **Perception grounding:** Muse Spark returns points and boxes on a **0–1000 normalized grid**. Convert with `x = x_norm*width/1000` and clamp to the image ([image understanding][img]).
- A ~1280 px image costs about 1,300–1,500 input tokens ([image understanding][img]).
- **PDFs** are converted to text plus per-page images. The model sees images from the first 50 pages and text from the first 100 ([file handling][files]). **[Inferred]** Vector-PDF text such as room labels reaches the model as text as well as pixels, which should help label reading.

### Structured output, JSON mode, tool calling
- `response_format={"type":"json_schema", ...}` on Chat Completions, or `text.format` on Responses. Decoding is **constrained**, so the output is guaranteed to match the schema. **Recursive schemas return HTTP 400** ([structured output][so]).
- Tool calling uses `tools`, `tool_choice` and `parallel_tool_calls` (default true). The `strict` flag only validates your schema. Arguments are "not guaranteed to validate", so validate them yourself ([tool calling][tools]).
- `reasoning_effort` ranges from `"minimal"` to `"max"` ([models][models]; [reasoning][reasoning]).

Code sketch (from the docs, [structured output][so]):
```python
from openai import OpenAI
client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
resp = client.chat.completions.create(
    model="muse-spark-1.3",
    messages=[{"role": "user", "content": [...]}],
    response_format={"type": "json_schema", "json_schema": {"name": "Rooms", "schema": {...}}},
)
```

### Rate limits and pricing ([pricing][pricing])
| Model | RPM | TPM | Price |
|---|---|---|---|
| `muse-spark-1.3` | 3,000 | 4M | $1.25 in / $4.25 out per 1M tokens (cached $0.15) |
| `muse-spark-1.3-contributor` | 150 | 3M | $0.10 / $0.20 |
| `muse-wonder-1.0` | 3,000 | 4M | $4.00 / $20.00 |
| `sam-3.1` | 3,000 | — | $2.50 per 1,000 images; $0.20 per 1,000 video frames (min 50 frames) |
| `muse-image-1.0` | 150 | — | $0.01 per image |

- Rate limits are **per team, not per key**. Retry 429s with exponential backoff and jitter. Responses carry `x-ratelimit-*` headers ([pricing][pricing]).
- Prompt caching is automatic ([pricing][pricing]).
- The $150 hackathon credit comes from the [Official Rules][rules] and the [guide][guide].

### How ConformScope uses it
Muse Spark 1.3 reads the plan image or PDF and returns schema-constrained JSON: room labels, room types, scale, and door symbol positions as 0–1000 points. It then writes the plain-language failure explanation and the report text. SAM 3.1 handles room and door masks (section 3). Muse Image is optional (section 3b).

### Gotchas
- Two env var names: `MODEL_API_KEY` for the API and `META_API_KEY` for Muse Code ([auth][auth]; [mc-auth][mc-auth]).
- `text.format` and `response_format` are not interchangeable across endpoints ([structured output][so]).
- Keep keys out of the Next.js browser bundle. Proxy calls through FastAPI ([auth][auth]).
- Credits require a card on file ([guide][guide]).

---

## 3. SAM 3.1

### What it is
- "Segment Anything with Concepts": a unified model for promptable segmentation in images and video. It can exhaustively segment every instance of a concept named by a short text phrase, or work from points, boxes and masks ([sam3 README][sam3-gh]).
- SAM 3.1 (Mar 27, 2026) added "Object Multiplex" for faster multi-object video tracking and shipped new checkpoints ([SAM 3.1 release notes][sam31-rel]).
- On the Meta Model API it takes **either** a concept noun phrase **or** box/point prompts, never both in one request ([segmenting][sam-seg]).

### How to call it via the Meta Model API
- Call `POST https://api.meta.ai/v1/responses` with `model="sam-3.1"`. The message holds one `input_text` (the concept) and one `input_image` (or `input_video`). Streaming is recommended for video and optional for images ([SAM overview][sam-ov]).
- **Output** is special-token text in `output_text`, for example `<0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=0;y=0;data=...|>`. Masks are base85 encoded (not base64). Request `metadata.mask_encoding: "one_bit"` for the smallest payloads, and `include_confidence` to get a score ([reading output][sam-read]; [SAM overview][sam-ov]).
- **Parsers:** `pip install meta-sam-parser` (Python 3.10+, no dependencies) or `npm install @meta-sam/parser`. Both decode masks to binary rasters, COCO RLE or SVG, and build box/point prompts (`build_object_prompt`) ([client libraries][sam-lib]).
- **Prompt rules:** one concept per request. Comma lists return zero matches. Negation and spatial phrasing are unreliable. A concept that isn't present returns an empty result, which is not an error. Point and box coordinates must be in the media's own pixels, with `w`/`h` set to the media size ([segmenting][sam-seg]).

Code sketch (from the docs, [media segmentation][sam-media]):
```python
with client.responses.stream(model="sam-3.1", input=[{"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "door"},
    {"type": "input_image", "image_url": "data:image/png;base64,..."}]}]) as stream:
    for event in stream:
        if event.type == "response.output_text.delta": ...
```

### Running the open weights instead
- **Code:** [github.com/facebookresearch/sam3][sam3-gh]. **Weights:** [huggingface.co/facebook/sam3.1][hf-sam31]. The weights are **gated with manual approval**, and you must authenticate with HF to download them ([sam3 README][sam3-gh]; [HF API][hf-sam31]).
- **License:** SAM License, a non-exclusive, worldwide, royalty-free licence with trade-control terms ([LICENSE][sam3-lic]).
- **Requirements:** Python 3.12+, PyTorch 2.7+, a CUDA GPU with CUDA 12.6+ ([sam3 README][sam3-gh]). No minimum VRAM is stated. The 7× speedup figure was measured on an H100 ([release notes][sam31-rel]).
- **Python API:** `build_sam3_image_model()` → `Sam3Processor(model)` → `set_image` → `set_text_prompt(prompt=...)`. It returns `masks`, `boxes`, `scores` ([sam3 README][sam3-gh]).

### Will it work on architectural line drawings?
- **No primary source evaluates SAM 3.1 on architectural plans.** Meta's docs list measuring regions from "photos, scans, or charts" as a use case ([media segmentation][sam-media]), which is suggestive at best.
- **[Inferred]** Concept prompts like "room" may fail, because rooms on plans are empty white regions bounded by lines and don't look like objects. Door symbols (arcs) might match "door" or might not.
- **[Inferred]** A more reliable pattern: ask Muse Spark for the pixel point of each room label, convert from 0–1000 to pixels, and send each point as a **point prompt** to SAM 3.1 (optionally with negative points on walls). Muse Spark proposes and SAM produces the mask. Meta's docs recommend exactly this pairing of VLM and SAM ([media segmentation][sam-media]).
- **[Inferred]** Keep the vector-wall pipeline as the primary geometry for vector PDFs, and use SAM for scans and raster input. Test on 3–5 plans on day one.

### How ConformScope uses it
SAM 3.1 produces room and door masks on raster or scanned plans, seeded with Muse Spark points. The masks feed the Ø1.50 m turning-circle test and the wheelchair simulation.

### Gotchas
- Pricing is per image, so re-segmenting each room separately multiplies cost ([pricing][pricing]). Still cheap: 1,000 calls cost $2.50.
- Results "can vary slightly between runs" ([segmenting][sam-seg]). **[Inferred]** Cache the masks and store them alongside auditor corrections.

---

## 3b. Muse Image (optional)

- `muse-image-1.0` generates and edits images. Use the Responses API for multi-turn edits, or `/v1/images/generations` and `/v1/images/edits` for one-shot calls ([models][models]; [image generation][imggen]). It costs $0.01 per image and is limited to 150 RPM ([pricing][pricing]).
- **[Inferred]** A "suggested fix" before/after render is possible, but generated images of a plan are not measurements. Label them as illustrations. It could qualify for the $5K Best Creative Build bonus ([guide][guide]), but it's low priority.

---

## 4. Muse Spark Open and Meta open-weight models

### What they are
| Model | Size | Inputs | Context | License | Weights |
|---|---|---|---|---|---|
| **Muse Spark Open** | 816B total / 42B active, sparse MoE | text, image, audio, video → text | 1,048,576 | Muse Model License + Acceptable Use Policy | HF `meta-models/Muse-Spark-Open-816B-A42B` (BF16, ~1.65 TB) and `meta-models/Muse-Spark-Open-816B-A42B-NVFP4` (~537 GB) |
| **Muse Glimmer** | 30B dense | text + image → text | 128K default | **Apache 2.0** | HF `meta-models/Muse-Glimmer-30B` (~60 GB bf16), plus `-GGUF` |

Sources: [Muse Spark Open][mso], [get the model][mso-get], [Muse Glimmer][glimmer], [Glimmer get the model][glimmer-get].

- Muse Spark Open needs about 8×B300 for BF16 or 4× Blackwell for NVFP4 ([Muse Spark Open][mso]). **[Inferred]** Self-hosting is not realistic for this hackathon. Use a hosted provider.
- **Hosted providers** ([deploy][mso-deploy]): Baseten `meta-models/muse-spark-open`, Fireworks `accounts/fireworks/models/muse-spark-open`, Together, Groq, Nebius, Modal, OpenRouter.
- Muse Glimmer is hosted on Together (`meta-models/Muse-Glimmer-30B`) ([Glimmer deploy][glimmer-deploy]) and on Modal Dedicated Endpoints ([Modal supported models][modal-sm]). It is fine-tunable on Fireworks ([FW Glimmer cookbook][fw-glimmer]).
- Using these makes you eligible for the **$10K Best Build on Meta Open Weight Models** bonus, "served on participants' own hardware or through partner-provided inference" ([guide][guide]).

---

## 5. Baseten

### What it is
Model APIs (serverless, pay per token) and dedicated deployments (Truss). Baseten serves Muse Spark Open on both ([Meta deploy][mso-deploy]; [Baseten Model APIs][bt-ov]).

### How to call it
- OpenAI-compatible base URL `https://inference.baseten.co/v1`, using a Baseten API key from Settings → API Keys ([Baseten Model APIs][bt-ov]; [Meta deploy][mso-deploy]).
- **Hackathon model ID: `meta-models/muse-spark-open-1026`** ([guide][guide]).

Code sketch (from Meta's deploy docs, [deploy][mso-deploy], with the model swapped per the [guide][guide]):
```python
client = OpenAI(api_key=os.environ["BASETEN_API_KEY"], base_url="https://inference.baseten.co/v1")
r = client.chat.completions.create(model="meta-models/muse-spark-open-1026",
                                   messages=[{"role": "user", "content": "..."}])
```

- Images go in OpenAI `image_url` parts. Send media over ~74 MB by URL ([deploy][mso-deploy]).

### Batching and async
- **Async inference** (a queue plus a webhook, queued up to 72 h) works only on **dedicated deployments. It "isn't available on Model APIs"**, and Baseten doesn't store outputs if webhook delivery fails ([Baseten async][bt-async]).
- **[Inferred]** For a batch verifier on the Model API, use client-side concurrency (asyncio with a semaphore) within the 2M TPM limit, and back off on `429` and `529 Overloaded` ([Baseten limits][bt-limits]).

### How ConformScope uses it
A verifier agent re-checks each room or door verdict with Muse Spark Open and flags disagreements for the auditor. That counts toward the open-weights bonus.

### Gotchas
- **Muse Spark Open on Baseten does not support structured outputs or JSON mode**. It does support tool calling ([Baseten Model APIs][bt-ov]). **[Inferred]** Get structured verdicts via a single forced tool call and validate them with Pydantic.
- `n>1` returns 400. `seed` and `temperature: 0` don't guarantee determinism ([Baseten Model APIs][bt-ov]).
- Credits are reviewed and not guaranteed ([guide][guide]).

---

## 6. Fireworks

### What it is
Serverless and dedicated inference plus fine-tuning. It serves **Muse Spark Open** serverless (text and images, tool calling, 1M context, `reasoning_effort`) ([Meta deploy][mso-deploy]). It fine-tunes **Muse Glimmer 30B** (free SFT until Nov 30, 2026) and Muse Spark Open (serverless LoRA) ([FW models][fw-models]; [post-training][mso-post]).

### How to call it
- OpenAI-compatible endpoint `https://api.fireworks.ai/inference/v1/chat/completions`, model `accounts/fireworks/models/muse-spark-open` ([Meta deploy][mso-deploy]).
- **Structured output:** `response_format` with `{"type":"json_object"}` or `{"type":"json_schema", ...}`. Recursive schemas are supported. **Using `json_schema` disables reasoning output** ([FW structured][fw-so]). **Not verified:** that structured output works specifically with Muse Spark Open on Fireworks.

### Fine-tuning workflow
- **Muse Glimmer 30B (recommended for the hackathon):** free LoRA SFT through the UI or the Serverless Training API until 11/30, no card required. Base `accounts/fireworks/models/muse-glimmer-30b`, tokenizer `meta-models/Muse-Glimmer-30B`, default LoRA rank 8. **The offer doesn't cover deployments or inference outside the training run** ([FW Glimmer cookbook][fw-glimmer]).
- **Managed SFT data format:** JSONL in OpenAI chat format, `{"messages":[...]}` per line, optionally with `tools`, between 3 and 3M lines ([FW SFT][fw-sft]).
- **Managed SFT commands:** `firectl dataset create <ID> file.jsonl`, then `firectl sftj create --base-model <MODEL> --dataset <ID> --output-model <OUT>`, then `firectl deployment create <OUT>` ([FW SFT][fw-sft]).
- **Serving:** "on-demand (dedicated) deployment… is the only supported method for serving trained models" ([FW SFT][fw-sft]).
- **Muse Spark Open LoRA:** serverless, rank up to 64, sequences up to 262,144 tokens, via `pip install "fireworks-ai[training]"` and `FiretitanServiceClient(...).create_lora_training_client(base_model="accounts/fireworks/models/muse-spark-open-nvfp4", rank=64)`. Rows with `"weight": 0` messages are excluded from the loss ([Meta post-training][mso-post]).

### How ConformScope uses it
- Each auditor correction is stored as `{"messages":[system, user: room/door context + original verdict, assistant: corrected verdict + explanation]}`.
- **[Inferred]** Show one LoRA SFT run on Muse Glimmer in the demo. A few dozen synthetic or seeded rows is enough to show the loop working. Don't claim accuracy gains you haven't measured. Use the evaluate-base-vs-tuned step in the cookbook ([FW Glimmer cookbook][fw-glimmer]).

### Gotchas
- Credits go only to a shortlist ([guide][guide]).
- A dedicated deployment for the tuned model costs money beyond the free training ([FW Glimmer cookbook][fw-glimmer]).
- **[Inferred]** Budget for it, or show sampling from the tuned model inside the training session.

---

## 7. Modal

### What it is
Serverless GPU functions and web endpoints, plus **Endpoints** (managed model serving). Endpoints come as **Shared** (per token, Modal-managed pool) or **Dedicated** (your containers, autoscaling, scale-to-zero, custom weights). Both expose OpenAI Chat/Responses-compatible and Anthropic Messages-compatible APIs ([Modal Endpoints][modal-ep]).

### Endpoints
- Create one with `modal endpoint create --shared --model <model>`. Auth uses a Proxy Token (`modal workspace proxy-tokens create`), sent as `Authorization: Bearer wk-<id>.ws-<secret>` ([Modal Endpoints][modal-ep]).
- **Muse Spark Open** is a Shared Endpoint model at $1.25 in / $4.25 out per Mtok. **Muse Glimmer 30B** (BF16 and NVFP4) is available on Dedicated Endpoints ([supported models][modal-sm]).
- **Gotcha:** "Credits included with your plan cannot be used for Shared Endpoint usage" ([Shared Endpoints][modal-shared]). **Not verified:** whether the hackathon's $100 credit covers Shared Endpoints. The event page says it is "for running Meta's open-weight models through Endpoints" ([guide][guide]).

### GPU function and web endpoint for SAM 3.1 or any HF model
- Set the GPU with `@app.function(gpu="A100")` (or T4, L4, A10, L40S, H100…). **A payment method on file is required** ([Modal GPU][modal-gpu]).
- For HTTP, use `@modal.fastapi_endpoint(method="POST")`, or `@modal.asgi_app()` to mount a full FastAPI app. `modal serve` runs it in development and `modal deploy` deploys it ([Web Functions][modal-web]).
- Store weights in a `modal.Volume` rather than downloading at boot ([model weights][modal-weights]).
- **Cold starts:** containers boot in about 1 s, but imports and `@modal.enter` model loading add time. Use `scaledown_window`, `min_containers` and `buffer_containers` ([cold start][modal-cold]). Memory snapshots use `enable_memory_snapshot=True`. GPU snapshots (alpha) use `experimental_options={"enable_gpu_snapshot": True}` ([memory snapshots][modal-snap]).

Pattern sketch (**[Inferred]**, assembled from the Modal patterns above and the SAM 3 Python API; not a doc example):
```python
import modal
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch==2.10.0", "torchvision", extra_index_url="https://download.pytorch.org/whl/cu128")
         .pip_install("git+https://github.com/facebookresearch/sam3.git"))
app = modal.App("sam31", image=image)
vol = modal.Volume.from_name("sam31-weights", create_if_missing=True)

@app.cls(gpu="L40S", volumes={"/weights": vol}, scaledown_window=300,
         secrets=[modal.Secret.from_name("huggingface")])
class Sam:
    @modal.enter()
    def load(self):
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor
        self.proc = Sam3Processor(build_sam3_image_model())

    @modal.fastapi_endpoint(method="POST")
    def segment(self, body: dict): ...
```
The GPU choice is a guess. The sam3 repo states no VRAM minimum ([sam3 README][sam3-gh]).

### How ConformScope uses it
**[Inferred]** Modal is optional. SAM 3.1 is cheaper and simpler on the Meta Model API. Use Modal only if (a) you need self-hosted SAM (privacy or offline demo), or (b) you serve Muse Glimmer or Muse Spark Open from a Modal Endpoint for the open-weights bonus.

---

## 8. Muse Code

### What it is
Meta's coding agent for the terminal and CI, built for Muse Spark. It runs with approvals and an OS sandbox ([Muse Code][mc]).

### How to install and use it
- **Install on Windows:** `irm https://dev.meta.ai/install.ps1 | iex`, then `muse --version` ([Muse Code][mc]).
- Run `muse` in the project. It asks whether to trust the workspace and then asks for a browser sign-in or an API key. **The default model is `muse-spark-1.2`** ([Muse Code][mc]).
- Headless runs: `muse exec "<prompt>"`. CI auth: `META_API_KEY` ([Muse Code][mc]; [auth][mc-auth]).
- **On Windows**, agent commands use PowerShell. The sandbox may trigger a UAC prompt. Voice input and session messaging are unavailable ([Muse Code][mc]).
- There is a TypeScript SDK, `@muse-code/sdk`, and `muse serve` exposes a session protocol ([Muse Code][mc]).
- Billing is pay-as-you-go per token, or a subscription. Subscriptions default to Contributor mode ([auth][mc-auth]; [pricing][pricing]).

### How ConformScope uses it
**[Inferred]** Use it as the dev agent for at least part of the build, and show it in the video or README. This supports the "Use of Meta AI Tooling" criterion.

---

## Recommended wiring

All of this section is **[Inferred]**: my design proposal built on the facts above.

| ConformScope feature | Tool | Why |
|---|---|---|
| Read plan (labels, room types, scale, door symbols) | **Muse Spark 1.3** via Meta Model API, PDF or image input, `json_schema` output with 0–1000 grounding points | Native PDF handling, constrained JSON, grounding coordinates |
| Room and door masks on raster or scanned plans | **SAM 3.1 on Meta Model API**, using point prompts seeded from Muse Spark labels | Hosted, $2.50 per 1,000 images, no GPU ops |
| Geometry on vector PDFs | Existing vector-wall approach, rebuilt in the new repo | Deterministic, and better than masks for measurement |
| Ø1.50 m turning circle, door width, manoeuvre space, wheelchair walk | Deterministic Python (FastAPI) | Rules must be exact and auditable, not LLM-guessed |
| Plain-language failure explanation and fix | **Muse Spark 1.3** (structured JSON) | Same API, one key |
| Batch verifier agent | **Muse Spark Open on Baseten** (`meta-models/muse-spark-open-1026`), forced tool call for structured verdicts | Open-weights bonus. Baseten lacks JSON mode, so use a tool call. |
| Fast structured explanations (alternative) | Fireworks `muse-spark-open` with `json_schema` | Only if Fireworks credits arrive |
| Fine-tune on auditor corrections | **Fireworks LoRA SFT on Muse Glimmer 30B** (free until Nov 30) | Cheapest visible learning loop |
| Report text and PDF export | Muse Spark 1.3 for text; PDF rendered server-side | — |
| Before/after fix illustration (stretch) | Muse Image | Creative-bonus candidate. Label it as illustrative. |
| Dev agent | **Muse Code** | Shows use of Meta tooling |
| Self-hosted SAM / Glimmer endpoint (optional) | **Modal** | Only if needed for privacy or the bonus |

**Demo narrative** (the guide says Demo and Impact together are 55%): upload a plan → rooms light up → the wheelchair gets stuck at a 0.77 m door → plain-French explanation and fix → the auditor overrides a verdict → that row lands in the training JSONL → tuned-model sample. Spend 3 minutes and clearly mark what was built during the event ([guide][guide]).

---

## Open questions and unverified items

1. **Submission form fields.** The portal needs login, so I couldn't see whether a deploy URL or description field is mandatory.
2. **Deploy link.** Judges assess the "live product", but no source says a hosted URL is required.
3. **Whether Muse Code usage draws from the $150 credit.** Not stated. The credit is described as "Meta Model API credits" ([rules][rules]).
4. **Modal hackathon credit vs. Shared Endpoints.** Modal says plan credits can't pay for Shared Endpoints ([Modal shared][modal-shared]). Whether the $100 hackathon grant counts as a "plan credit" is unknown.
5. **SAM 3.1 on architectural line drawings.** No benchmark or doc covers it. Test early.
6. **SAM 3.1 GPU and VRAM needs** for self-hosting. Not stated in the repo.
7. **Fireworks structured output on Muse Spark Open** specifically. The general docs say it works; there's no model-specific confirmation.
8. **Baseten pricing for Muse Spark Open** and whether `-1026` differs in features. The model page wasn't checked; the table in the Baseten docs didn't render.
9. **Use of non-Meta AI tools** (e.g. Claude Code) for coding. The rules don't address it; disclose in the README.
10. **Third-party "$150 per participant" reports** match the Official Rules ([rules][rules]). Third-party judging-weight reports also match the Official Rules.

---

<!-- Link references -->
[event-md]: https://cerebralvalley.ai/e/meta-ai-developer-hackathon.md
[guide]: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details
[rules]: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver
[geo]: https://dev.meta.ai/legal/geographic-use-policy
[models]: https://dev.meta.ai/docs/models
[auth]: https://dev.meta.ai/docs/authentication
[sdks]: https://dev.meta.ai/docs/sdks
[protocols]: https://dev.meta.ai/docs/protocols
[coding]: https://dev.meta.ai/docs/coding-agents
[pricing]: https://dev.meta.ai/docs/pricing-rate-limits
[so]: https://dev.meta.ai/docs/structured-output
[tools]: https://dev.meta.ai/docs/tool-calling
[reasoning]: https://dev.meta.ai/docs/reasoning
[img]: https://dev.meta.ai/docs/image-understanding
[files]: https://dev.meta.ai/docs/file-handling
[imggen]: https://dev.meta.ai/docs/image-generation
[sam-media]: https://dev.meta.ai/docs/media-segmentation
[sam-ov]: https://dev.meta.ai/docs/sam/overview
[sam-seg]: https://dev.meta.ai/docs/sam/segmenting
[sam-read]: https://dev.meta.ai/docs/sam/reading-segmentation
[sam-lib]: https://dev.meta.ai/docs/sam/client-libraries
[sam3-gh]: https://github.com/facebookresearch/sam3
[sam31-rel]: https://github.com/facebookresearch/sam3/blob/main/RELEASE_SAM3p1.md
[sam3-lic]: https://github.com/facebookresearch/sam3/blob/main/LICENSE
[hf-sam31]: https://huggingface.co/facebook/sam3.1
[mso]: https://dev.meta.ai/docs/muse-spark-open
[mso-get]: https://dev.meta.ai/docs/muse-spark-open/get-the-model
[mso-deploy]: https://dev.meta.ai/docs/muse-spark-open/deploy
[mso-post]: https://dev.meta.ai/docs/muse-spark-open/post-training
[glimmer]: https://dev.meta.ai/docs/muse-glimmer
[glimmer-get]: https://dev.meta.ai/docs/muse-glimmer/get-the-model
[glimmer-deploy]: https://dev.meta.ai/docs/muse-glimmer/deploy
[mc]: https://dev.meta.ai/docs/muse-code
[mc-auth]: https://dev.meta.ai/docs/muse-code/auth
[bt-ov]: https://docs.baseten.co/inference/model-apis/overview
[bt-async]: https://docs.baseten.co/inference/async
[bt-limits]: https://docs.baseten.co/inference/model-apis/pricing-and-limits
[fw-so]: https://docs.fireworks.ai/structured-responses/structured-response-formatting
[fw-models]: https://docs.fireworks.ai/fine-tuning/models
[fw-sft]: https://docs.fireworks.ai/fine-tuning/fine-tuning-models
[fw-glimmer]: https://docs.fireworks.ai/fine-tuning/training-api/cookbook/muse-glimmer
[modal-ep]: https://modal.com/docs/guide/endpoints
[modal-shared]: https://modal.com/docs/guide/shared-endpoints
[modal-sm]: https://modal.com/docs/guide/supported-models
[modal-gpu]: https://modal.com/docs/guide/gpu
[modal-web]: https://modal.com/docs/guide/webhooks
[modal-weights]: https://modal.com/docs/guide/model-weights
[modal-cold]: https://modal.com/docs/guide/cold-start
[modal-snap]: https://modal.com/docs/guide/memory-snapshots
