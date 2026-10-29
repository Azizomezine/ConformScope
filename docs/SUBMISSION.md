# Submission draft

Fields of the Cerebral Valley submission form (seen 2026-10-29). Fill the `TODO`s at the end.

**Team name:** ConformScope
**Team members:** Omezine Mohamed Aziz (azizomezine)
**Track:** Indie
**Problem statement:** Build for Your World
**Most Viral track (X post link):** TODO — post the demo clip on X, tag the event

## Project description

Homes are approved on paper, and the people in wheelchairs who can't get in only find out
after moving in. ConformScope reads a building plan, finds every room and door, and checks it
against French accessibility (PMR) rules with real geometry: can a 1.50 m wheelchair turning
circle fit, is each door wide enough. A virtual wheelchair then walks through the plan, stops
where it gets stuck, and explains in plain language why and how to fix it — while the fix still
costs an eraser instead of a renovation. An auditor can correct any verdict, and every
correction is kept.

**Public GitHub repository:** https://github.com/Azizomezine/ConformScope
**3-minute demo video:** TODO

## Use of Meta products

- **Muse Spark** reads the plan image: room names, room types, scale and door symbols, returned
  as schema-constrained JSON with positions on the image. It also writes the plain-language
  explanation and fix for each failure.
- **SAM 3.1** segments the rooms and doors, prompted with the label positions Muse Spark found.
- **Muse Spark Open** (open weights, served on Baseten) is a verifier agent that re-checks every
  verdict through tool calls and flags the doubtful ones for the auditor.
- **Muse Code** and Muse Wonder were the coding agents used to build the project.
- TODO: Muse Glimmer fine-tune on Fireworks, if shipped.

## Why Meta's models are important

TODO after building — say what each model made possible that geometry alone could not
(reading hand-labelled plans, segmenting scanned plans, explaining to non-experts), with one
concrete number from the eval table.

## Feedback on Meta products

TODO — keep notes while building (what worked, what broke, docs gaps).

## Feedback on partner technologies (Fireworks, Modal, Baseten)

TODO — keep notes while building.
