# ConformScope — hackathon roadmap

> Before a family signs for a home, ConformScope shows whether a wheelchair can
> actually live there — and how to fix it while it is still on paper.

Meta Global AI Developer Hackathon · **Indie track** · theme **Build for Your World**.
Submission due **Wed Nov 4, 9:00 PM EST = Thu Nov 5, 03:00 Tunisia**. Aim to submit
on **Nov 4 afternoon**, Tunisia time.

Research behind every choice: [`docs/research/meta-hackathon-stack.md`](docs/research/meta-hackathon-stack.md).

## Ground rules

- **New work only.** Every line in this repo is written during the event (Oct 26 – Nov 4).
  No code is copied from earlier projects; the commit history is the proof.
- **Not a "simple image analyzer".** The verdict comes from real geometry (a Ø1.50 m
  turning circle measured against the walls, door widths in cm). The AI reads the plan
  and explains; the geometry decides.
- **Secrets stay in env vars** (`MODEL_API_KEY`, `META_API_KEY`, `BASETEN_API_KEY`,
  `FIREWORKS_API_KEY`), loaded from a git-ignored `.env`.
- Every slice ends with something that runs, and is built test-first.

## Stack

| Piece | Tool |
|---|---|
| Read the plan: labels, room types, scale, door symbols | **Muse Spark** `muse-spark-1.3` (Meta Model API, `json_schema` output, grounding coords) |
| Segment rooms and doors | **SAM 3.1** `sam-3.1` (Meta Model API, hosted) |
| Verifier agent, checks every verdict | **Muse Spark Open** on **Baseten** (tool calling, no JSON mode) — eligible for the open-weights bonus |
| Fine-tune on auditor corrections (stretch) | **Muse Glimmer 30B** LoRA SFT on **Fireworks** (free until Nov 30) |
| Building the app | **Muse Code** / Claude Code on `muse-wonder-1.0` |
| App | Next.js on Vercel + FastAPI (Python) |

## Slices

| # | Day | Slice | Done when |
|---|---|---|---|
| 1 | Oct 29 | **Spike: SAM 3.1 + Muse Spark on one real plan.** Skeleton repo, `.env`, one script that sends a plan to both and saves the output. | We know if SAM can segment rooms on a line drawing. **Go / no-go** decides slice 3. |
| 2 | Oct 30 | **Plan intake.** Upload PDF or image → render page → store. Muse Spark returns room labels, positions and scale as JSON. | Upload a plan, see labelled rooms listed |
| 3 | Oct 30 | **Rooms.** SAM masks seeded with Muse Spark label points (fallback: vector walls from the PDF) → room polygons in metres. | Each room has an outline and an area |
| 4 | Oct 31 | **Turning circle check.** Largest inscribed circle per room vs Ø1.50 m. Green / red circle drawn on the plan. | Tests pass on hand-checked rooms |
| 5 | Nov 1 | **Doors.** Detect doors, measure clear width, check it. | Each door has a width and a verdict |
| 6 | Nov 1 | **Walk the plan.** Rooms + doors as a graph; a wheelchair icon moves through the home and stops where it gets stuck. | The demo moment works end to end |
| 7 | Nov 2 | **Explain + verify.** Muse Spark writes the plain-language reason and fix; Muse Spark Open on Baseten double-checks each verdict and flags doubtful ones. | Each failure has a human sentence and a confidence |
| 8 | Nov 2 | **Auditor corrections.** Click a room or door, override the verdict; every correction saved as a JSONL label (Fireworks fine-tune format). | A correction survives a reload |
| 9 | Nov 3 | **Report PDF + deploy.** Export the report; deploy to Vercel; README with an eval table. | Live URL |
| 10 | Nov 4 | **Demo video (3 min) + submission.** X post for the Most Viral track. | Submitted |

Cut order if late: 8 → 5 → 7's verifier. Never cut 4 or 6.

## Demo video (3 min)

1. **0:00** A wheelchair stopped at a doorway that is too narrow. No words.
2. **0:20** The problem: homes are approved on paper; the people who can't get in find out after moving in.
3. **0:40** Drop a plan in → rooms found → wheelchair walks the plan → gets stuck → plain-language reason → the fix.
4. **2:00** The Meta stack: Muse Spark, SAM 3.1, Muse Spark Open verifier, built with Muse Code.
5. **2:30** Why I built this — in my own words.

Only real stories, used with permission; every statistic sourced in the README.
