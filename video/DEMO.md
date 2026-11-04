# Recording the demo (section 5)

One screen recording, ~60 s of keepers, edited into `DemoCut`. Narration is
recorded separately afterwards, reading the lines below while the clip plays.

## Before you press record

- **Clean state:** fresh browser profile or incognito, English UI, day mode,
  no other tabs, bookmarks bar hidden, Windows notifications off (Focus).
- **Window:** Chrome full screen (F11), page zoom 125 % so labels read on a phone.
- **OBS:** 1920×1080, 60 fps, MP4, capture the browser window only. Cursor visible.
- **Plan:** the plan you will show, checked once beforehand so you know its real
  numbers. Clear its old corrections first (*Clear every correction*). Make sure you
  are allowed to show it on a public video.
- **Keys:** the verifier key is set, so the explanations say *Verified by Muse
  Spark Open* and not *Not verified (no verifier key)*.
- **Time the check** with a stopwatch during the take. Your intro line says
  "in under a minute": keep it only if that is what the stopwatch says;
  otherwise say the real time ("in two minutes").

## The take, click by click

Move slowly. Before and after each click, keep the mouse still for 1 s: that's
where the cuts and the zooms go.

| # | Do | Narration (yours) | Zoom in `PUNCHES` |
|---|---|---|---|
| 0 | *(optional, 6 s)* On the landing page, scroll slowly: the 2D plan becomes the 3D building and the wheelchair stops at the WC door. | — music only, or: "Here's the idea." | — |
| 1 | **Check a plan →**, then drag the PDF onto *Open a plan*. | "I drop in a real apartment plan, as a PDF or even a photo." | — |
| 2 | Let the progress run: *Muse Spark is reading the plan…*, *Measuring the rooms…*, *SAM 3.1 is outlining…*. Don't touch anything. | "Meta's Muse Spark reads the room names and the scale, and SAM 3.1 outlines the rooms on scanned plans." | On the progress line, ×1.6 |
| 3 | Rooms appear. Hold 2 s, then **Whole sheet**. | "Then the geometry decides. For every room we measure the largest free circle. Green, a 1.50 m turn fits. Red, it doesn't, and we show by how much." | — |
| 4 | In *Rooms*, filter **Fail**, click the red room. | "This [room] tops out at Ø[x.xx] m, so it fails." — **read the number off the screen**. | **Money shot:** red circle + its Ø label, ×2.4, label `Ø x.xx m — needs Ø1.50 m` in red |
| 5 | Open **Report** → *Walk the plan* → **Play the walk**. Let it stop. | "Then we walk the plan: the wheelchair goes room by room, and stops exactly where a real person would." | On the stop, ×2 |
| 6 | Click **Fix it: …** at the stop (or **Explain the failures**). | "It tells you why, and how to fix it, and a second model, Muse Spark Open, double-checks every verdict." | On the reason + *Verified by Muse Spark Open*, ×1.8 |
| 7 | **Merge a nook into a room** (or **Draw a missing wall**): click, click → *corrected by hand*. | "If the plan is ambiguous, the engineer fixes it in one click, and the correction is saved with the plan." | On the re-measured room, ×1.8 |
| 8 | **Export the report (PDF)**, open the PDF, scroll one page. | "And one click gives a PDF report, ready for the client or the inspector." | On the PDF's first page, ×1.4 |

Steps 5 and 6 aren't in the draft script; add them. *Walk the plan* is the
moment that makes people feel the problem, and *Muse Spark Open* is the
open-weights model.

## Then

1. Save as `video/public/rec/demo.mp4` (git-ignored).
2. In `src/DemoCut.tsx`, set `DEMO.file = 'rec/demo.mp4'` and `DEMO.seconds`
   to the clip length.
3. `npx remotion studio`, open **DemoCut**, scrub to each moment in the table,
   and add a line to `PUNCHES` (time in seconds, x / y as fractions of the frame).
4. Cut the long waits in your editor: jump-cut, or speed them up with a small
   "×4" label. Don't hide how long it took.
5. Render: `npx remotion render src/index.ts DemoCut out/demo.mp4`.

The other pieces, rendered the same way: `Problem` / `ProblemOverlay`
(section 2), `HandCheck` (section 3), `Intro` (section 4 → 5).
