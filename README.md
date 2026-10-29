# ConformScope

Can a wheelchair live in this home? ConformScope reads a building plan, finds every
room, and checks it against PMR accessibility rules with real geometry: does a
Ø1.50 m turning circle fit, and where does it not? An auditor can fix the room cut
by clicking — merge a nook into a room, or draw a missing wall — and every
correction is stored with the plan and replayed on the next measure.

Built for the Meta Global AI Developer Hackathon (Indie track, *Build for Your
World*). Roadmap and slice plan: [ROADMAP.md](ROADMAP.md).

## What works today

| Slice | Status |
| --- | --- |
| Spike: SAM 3.1 + Muse Spark on one plan | done |
| Plan intake (upload PDF/image → labelled rooms) | done |
| Rooms: polygons in metres (vector walls, SAM for pictures) | done — [#3](https://github.com/Azizomezine/ConformScope/issues/3) |
| Turning-circle check Ø1.50 m, green/red on the plan | done — [#4](https://github.com/Azizomezine/ConformScope/issues/4) |
| Room fixes by click (merge, drawn wall, stored per plan) | done — [#6](https://github.com/Azizomezine/ConformScope/issues/6) |

## Stack

- **Muse Spark** (`muse-spark-1.3`, Meta Model API) reads room labels, types and
  dimensions off the plan as schema-constrained JSON.
- **SAM 3.1** (`sam-3.1`, Meta Model API) segments rooms on pictures (scans/photos),
  prompted with Muse Spark's label points.
- **Geometry decides the verdict** (Python, OpenCV): rooms are cut from the drawn
  walls of a vector PDF, measured in metres, and the largest free circle is
  compared to Ø1.50 m. No model output decides a verdict.
- **FastAPI** backend + **Next.js** frontend. The browser only talks to `/api/*`;
  model keys stay on the server.

## Setup

```powershell
uv sync
Copy-Item .env.example .env   # then set MODEL_API_KEY in .env
```

`MODEL_API_KEY` is the Meta Model API key. `META_API_KEY`, `BASETEN_API_KEY` and
`FIREWORKS_API_KEY` are for Muse Code / later slices and can stay empty for now.

## Run it

Terminal 1 (backend, from the repo root):

```powershell
uv run uvicorn conformscope.api:app --reload   # http://127.0.0.1:8000
```

Terminal 2 (frontend):

```powershell
cd web
npm install
npm run dev                                     # http://localhost:3000
```

Open http://localhost:3000, drop a plan (PDF or image), and wait for Muse Spark to
read it. You should see the rooms outlined on the plan, each with its area, its
turning circle (green *Conforme PMR* / red *Non conforme PMR (max Ø…)*), and the
verdict list on the right.

### Test the corrections (slice 6)

1. Upload a vector PDF plan.
2. Click **Merge a nook into a room**, click the room that stays, then click the
   nook that belongs to it. The room is re-measured and marked *corrected by hand*.
3. Click **Draw a missing wall** and click two points across an opening. The rooms
   are re-cut on either side of the wall.
4. Reload the page and re-upload/fetch the plan: corrections are stored per plan
   (`corrections.json` next to its reading) and replayed on every re-measure.
5. **Clear corrections** removes them all.

## Test suite

```powershell
uv run pytest        # 98 tests
```

- Unit tests use fixed synthetic inputs — no network, no model calls, no private
  plans needed.
- The sample-plan tests (`Plan_Logement_Niveau_02`) run only when the private file
  exists at `samples/private/Plan_Logement_Niveau_02.pdf`; they skip cleanly
  without it. On that plan, 6 of 8 written areas land within 5% (the two known
  misses are exactly what slice 6's corrections are for).
- Frontend check: `cd web; npm run build`.

## API

| Endpoint | What it does |
| --- | --- |
| `POST /plans` | Upload a plan; returns labels, measured rooms, verdicts |
| `GET /plans/{id}` | The stored reading, with corrections applied |
| `GET /plans/{id}/image` | The rendered plan page |
| `GET /plans/{id}/corrections` | Stored corrections for the plan |
| `POST /plans/{id}/corrections` | Replace corrections; re-measures and replays them |

## Known limits

- Issue #6's sample acceptance is not fully met yet: merging the whole landing
  region into the 10.09 m² bedroom overshoots (+12.4% vs the 5% target) because
  the cupboard is a sub-region. Draw a wall to isolate it first, then merge.
- The verdict (`check_turning`, bare polygon) and the drawn circle
  (obstacle-aware) can disagree in cluttered rooms; the verdict is the bare-room
  rule on purpose.
- Corrections apply to vector PDFs; picture plans ignore them for now.

## Credits

Built with **Muse Code** on **Muse Wonder** (Meta, `muse-wonder-1.0`), credited as
co-author in the merge commits on `main`. Room reading by Muse Spark, segmentation
by SAM 3.1 (Meta Model API).
