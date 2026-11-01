# Hackathon notes from Discord

Read 2026-10-30 from the Meta Global AI Developer Hackathon Discord (#announcements, #faqs,
#office-hours) and the participant guide it links. Only what `docs/research/meta-hackathon-stack.md`
doesn't already cover.

## Action items for ConformScope

1. **Open the demo video with one line on what is pre-existing vs. built this week.** CV's
   #faqs answer on prior work: the repo must be "a standalone extract" with only event work,
   and the 3-minute video should open by stating what existed before and what was built.
2. **Check the Glimmer fine-tune plan against the Model API Terms §10.1(ix).** Another builder
   asked Meta in #office-hours whether training Muse Glimmer on Muse Spark API outputs is
   allowed under that section, or needs written authorization. No answer yet (2026-10-29).
   `SUBMISSION.md` plans a Glimmer fine-tune; train on **auditor corrections**, not raw Spark
   outputs, or wait for Meta's answer.
3. **Watch the Agents 102 recording, "Best Practices for Verifiable Agents"**
   (Yash Khare, 2026-10-28): https://vimeo.com/1239918451. It maps onto the Muse Spark Open
   verifier agent, and using the vocabulary Meta itself teaches helps the 25% tooling score.
4. **Look at Meta's workshop repo** https://github.com/meta-models/legal-agent-workshop
   (Agents 101, multimodal agent). It's a compliance-flavoured agent, close to ConformScope's
   shape, and shows the agent pattern Meta presents. Recording: https://vimeo.com/1239550947.
5. **Fireworks live session today, Fri Oct 30, 12:00 ET** (17:00 Tunisia): "Building
   Specialized Intelligence on Fireworks: From Inference to Training with Muse Open Models".
   Relevant for the Glimmer SFT and the $10K open-weight bonus.
6. **Most Viral ($20K):** CV confirmed the X post can be a *shorter* clip than the 3-minute
   demo. Only engagement on that single post counts, until Nov 8 EOD.
7. **Ask in #office-hours** (weekdays 10–11 ET, 15:00–16:00 Tunisia until Nov 1, then
   16:00–17:00). Threads are answered there by Meta staff. Post-your-project threads get
   feedback too (one team posted their pitch and asked "what would you cut?").

## Judging, as CV restated it in #office-hours

The video is judged under **Demo (25%)** ("a working, impressive demo whose product holds up
live and is genuinely cool to watch") and **Use of Meta AI Tooling (25%)** ("beyond a basic
integration"). Technical Depth is another 20% and Impact 30%. Judges use the video, the code
and the live product.

## Other useful bits

- Kickoff recording: https://vimeo.com/1238909940/6d91bab1b2
- Livestream page: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/live
- Everyone who worked on the project must be an approved participant; no new approvals.
- API key creation bug ("Failed to create API key", then logged out) is being reported by
  several people. If it hits you, file at https://dev.meta.ai/support with Team ID and the
  exact error, and never paste keys or card details in Discord.
- Baseten model ID for the event: `meta-models/muse-spark-open-1026` (already in the research doc).
