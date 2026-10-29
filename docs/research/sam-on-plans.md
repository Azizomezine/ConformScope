# SAM 3.1 on architectural plans — go / no-go

Issue #1. **Status: pending the first live run.**

## How to run

```powershell
Copy-Item .env.example .env   # then put your MODEL_API_KEY in .env
uv run conformscope-spike path\to\plan.pdf
```

Outputs land in `.data/spike/<plan name>/` (git-ignored, so client plans never reach GitHub):

| File | What it shows |
|---|---|
| `rooms.json` | Muse Spark's raw reply: labels, room types, scale |
| `sam_concept.txt`, `overlay_concept.png` | SAM 3.1 with the concept prompt `room` |
| `sam_points.txt`, `overlay_points.png` | SAM 3.1 with one point per Muse Spark label |
| `summary.json` | Counts: labels found, masks from each prompt |

## What to judge on each overlay

- Does each room get **one** mask that stops at the walls, or does it leak through door openings into the next room?
- Does the concept prompt `room` find anything at all on a line drawing?
- Do the red label dots from Muse Spark land on the actual labels?

## Results

| Plan | Labels | Concept masks | Point masks | Masks stop at walls? | Notes |
|---|---|---|---|---|---|
| TODO | | | | | |

## Decision

TODO — **go** (slice #3 uses SAM point masks) or **no-go** (slice #3 uses vector walls from the PDF; SAM kept for scans only).
