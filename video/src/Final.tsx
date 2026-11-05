import {loadFont as loadBody} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Freeze,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {Intro} from './Intro';

const body = loadBody('normal', {weights: ['600'], subsets: ['latin']}).fontFamily;
const mono = loadMono('normal', {weights: ['500'], subsets: ['latin']}).fontFamily;
const C = {ink: '#0d1a2e', navy: '#1d3557', sky: '#4ea8de', paper: '#f4f7fb', bad: '#e53935'};
const FPS = 30;
const TALK = 1.2; // the live narration, sped up slightly (pitch kept)
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const EASE = Easing.inOut(Easing.cubic);

type Punch = {from: number; to: number; x: number; y: number; zoom: number; label: string; bad?: boolean};
type Seg =
  | {kind: 'hook'; from: number; to: number}
  | {kind: 'live'; from: number; to: number; rate?: number; punches?: Punch[]; matchIn?: boolean}
  | {kind: 'ff'; from: number; to: number; seconds: number; label: string}
  | {kind: 'handcheck'; from: number; to: number}
  | {kind: 'problem'; from: number; to: number; rate: number}
  | {kind: 'gen'; file: string; from: number; to: number; rate: number}
  | {kind: 'outro'; seconds: number};

// Source times in seconds of rec/live.mp4 (snapped to silences in the narration).
const SEGS: Seg[] = [
  // Opening shot (Gemini Omni): a wheelchair POV rolling toward a bathroom door.
  {kind: 'gen', file: 'rec/genA.mp4', from: 0, to: 4.6, rate: 1},
  {kind: 'hook', from: 0, to: 13.6}, // "This toilet is 55 cm wide … someone signed off this plan."
  // Gemini Omni: the real bathroom rises into a blueprint with a red circle…
  {kind: 'gen', file: 'rec/genB.mp4', from: 1.8, to: 10.0, rate: 1.3},
  {kind: 'live', from: 63.0, to: 70.2, rate: 1, matchIn: true}, // MATCH CUT: "the WC only fits 1.40"
  {kind: 'problem', from: 0, to: 8.2, rate: 1.25},
  {kind: 'problem', from: 20.4, to: 27.6, rate: 1.25},
  {kind: 'handcheck', from: 0.9, to: 7.4}, // "I'm Aziz … checked by hand with a ruler"
  {kind: 'live', from: 7.4, to: 20.0}, // "Can a wheelchair live in this home?"
  {kind: 'live', from: 23.3, to: 48.8}, // steps 1–3
  {kind: 'live', from: 71.0, to: 81.2}, // step 6, the fix
  {kind: 'live', from: 89.4, to: 93.95}, // "a real apartment plan"
  {kind: 'ff', from: 93.95, to: 231.2, seconds: 3.5,label: 'FAST-FORWARD · the full check ran 2 min 17 s'},
  {
    kind: 'live',
    from: 231.2,
    to: 262.3,
    punches: [{from: 253, to: 262, x: 0.62, y: 0.6, zoom: 2.2, label: 'Room 12 · WC: Ø1.26 m — needs Ø1.50 m', bad: true}],
  },
  {kind: 'live', from: 291.99, to: 298.31}, // "can a wheelchair reach every room?"
  {kind: 'ff', from: 298.31, to: 313.8, seconds: 3.1, label: 'FAST-FORWARD ×5'},
  {
    kind: 'live',
    from: 313.8,
    to: 337.25,
    punches: [{from: 316, to: 328, x: 0.78, y: 0.57, zoom: 2, label: 'The wheelchair reaches 10 of 30 rooms', bad: true}],
  },
  {kind: 'ff', from: 337.25, to: 356.05, seconds: 3.8, label: 'FAST-FORWARD ×5'},
  {
    kind: 'live',
    from: 356.05,
    to: 367.1,
    punches: [{from: 358, to: 366, x: 0.88, y: 0.45, zoom: 1.7, label: 'Every failure re-checked by Muse Spark Open'}],
  },
  {kind: 'live', from: 392.2, to: 398.3}, // export the report
  {kind: 'live', from: 409.9, to: 414.6}, // the PDF
  {kind: 'outro', seconds: 3.6},
];

const segSeconds = (s: Seg) => {
  switch (s.kind) {
    case 'hook':
      return s.to - s.from;
    case 'live':
      return (s.to - s.from) / (s.rate ?? TALK);
    case 'handcheck':
      return (s.to - s.from) / TALK;
    case 'ff':
      return s.seconds;
    case 'problem':
    case 'gen':
      return (s.to - s.from) / s.rate;
    case 'outro':
      return s.seconds;
  }
};

const TIMELINE = (() => {
  let at = 0;
  return SEGS.map((s) => {
    const frames = Math.round(segSeconds(s) * FPS);
    const item = {seg: s, start: at, frames};
    at += frames;
    return item;
  });
})();
export const FINAL_DURATION = TIMELINE[TIMELINE.length - 1].start + TIMELINE[TIMELINE.length - 1].frames;

// Short volume ramps at every cut, so nothing clicks.
const edge = (f: number, n: number) => interpolate(f, [0, 3, n - 3, n], [0, 1, 1, 0], clamp);

const Chip: React.FC<{label: string; bad?: boolean; k: number}> = ({label, bad, k}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      right: 0,
      bottom: 160,
      display: 'flex',
      justifyContent: 'center',
      opacity: k,
      transform: `translateY(${(1 - k) * 20}px)`,
    }}
  >
    <div
      style={{
        fontFamily: body,
        fontWeight: 600,
        fontSize: 46,
        color: C.paper,
        background: bad ? C.bad : C.navy,
        padding: '14px 32px',
        borderRadius: 12,
        boxShadow: '0 20px 50px #0007',
      }}
    >
      {label}
    </div>
  </div>
);

const Live: React.FC<{seg: Extract<Seg, {kind: 'live'}>; frames: number}> = ({seg, frames}) => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const rate = seg.rate ?? TALK;
  const t = seg.from + (f / FPS) * rate; // source time
  let zoom = 1;
  let x = 0.5;
  let y = 0.5;
  let k = 0;
  let chip: Punch | null = null;
  for (const p of seg.punches ?? []) {
    if (t < p.from - 0.6 || t > p.to + 0.6) continue;
    k = interpolate(t, [p.from - 0.6, p.from, p.to, p.to + 0.6], [0, 1, 1, 0], {...clamp, easing: EASE});
    zoom = 1 + (p.zoom - 1) * k;
    x = p.x;
    y = p.y;
    chip = p;
  }
  if (seg.matchIn) {
    // Lands on the red WC circle as tight as the hook's last frame, then opens up.
    const m = interpolate(f, [0, 26], [1, 0], {...clamp, easing: Easing.out(Easing.cubic)});
    zoom = 1 + 1.8 * m;
    x = 1505 / 1920;
    y = 700 / 1080;
    k = m;
  }
  const ox = Math.min(Math.max(x * width, width / (2 * zoom)), width - width / (2 * zoom));
  const oy = Math.min(Math.max(y * height, height / (2 * zoom)), height - height / (2 * zoom));
  return (
    <AbsoluteFill style={{background: C.ink, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `scale(${zoom}) translate(${(width / 2 - ox) * Math.min(1, k * 4)}px, ${(height / 2 - oy) * Math.min(1, k * 4)}px)`}}>
        <OffthreadVideo
          src={staticFile('rec/live.mp4')}
          trimBefore={Math.round(seg.from * FPS)}
          playbackRate={rate}
          volume={(vf) => edge(vf, frames)}
          style={{width: '100%', height: '100%'}}
        />
      </AbsoluteFill>
      {chip && <Chip label={chip.label} bad={chip.bad} k={k} />}
    </AbsoluteFill>
  );
};

const Hook: React.FC<{seg: Extract<Seg, {kind: 'hook'}>; frames: number}> = ({seg, frames}) => {
  const f = useCurrentFrame();
  // Final second: push into the toilet, so the cut lands on the plan's WC.
  const push = interpolate(f, [frames - 30, frames], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  const video = (style: React.CSSProperties, muted: boolean) => (
    <OffthreadVideo
      src={staticFile('rec/hook.mp4')}
      trimBefore={Math.round(seg.from * FPS)}
      muted={muted}
      volume={(vf) => edge(vf, frames)}
      style={{position: 'absolute', width: 1920, height: 1080, ...style}}
    />
  );
  return (
    <AbsoluteFill style={{background: C.ink, overflow: 'hidden'}}>
      {/* Blurred fill from the phone footage, behind the sharp panel. */}
      <AbsoluteFill style={{transform: 'scale(3.2)', transformOrigin: '960px 540px', filter: 'blur(30px) brightness(0.45)'}}>
        {video({clipPath: 'inset(0 657px 0 657px)'}, true)}
      </AbsoluteFill>
      <AbsoluteFill style={{transform: `scale(${1 + 1.8 * push})`, transformOrigin: '910px 640px'}}>
        {video({clipPath: 'inset(0 657px 0 657px)'}, false)}
      </AbsoluteFill>
      {/* Face, cropped from the bottom-left of the same recording. */}
      <div
        style={{
          position: 'absolute',
          left: 120,
          bottom: 80,
          width: 360,
          height: 360,
          borderRadius: '50%',
          overflow: 'hidden',
          border: `6px solid ${C.paper}`,
          boxShadow: '0 20px 50px #0009',
          opacity: 1 - push,
        }}
      >
        <div style={{position: 'absolute', left: -95, top: -700}}>{video({}, true)}</div>
      </div>
    </AbsoluteFill>
  );
};

const HandCheckSeg: React.FC<{seg: Extract<Seg, {kind: 'handcheck'}>; frames: number}> = ({seg, frames}) => (
  <AbsoluteFill style={{background: C.ink}}>
    <OffthreadVideo
      src={staticFile('rec/handcheck.mp4')}
      playbackRate={15 / (frames / FPS)}
      muted
      style={{width: '100%', height: '100%'}}
    />
    {/* Voice from the live take; its face as a bubble. */}
    <div
      style={{
        position: 'absolute',
        left: 60,
        bottom: 60,
        width: 300,
        height: 300,
        borderRadius: '50%',
        overflow: 'hidden',
        border: `6px solid ${C.paper}`,
        boxShadow: '0 20px 50px #0009',
      }}
    >
      <OffthreadVideo
        src={staticFile('rec/live.mp4')}
        trimBefore={Math.round(seg.from * FPS)}
        playbackRate={TALK}
        volume={(vf) => edge(vf, frames)}
        style={{position: 'absolute', width: 1920, height: 1080, left: -120, top: -800}}
      />
    </div>
  </AbsoluteFill>
);

const FastForward: React.FC<{seg: Extract<Seg, {kind: 'ff'}>; frames: number}> = ({seg, frames}) => {
  const f = useCurrentFrame();
  const k = interpolate(f, [0, 8, frames - 8, frames], [0, 1, 1, 0], clamp);
  return (
    <AbsoluteFill style={{background: C.ink}}>
      <OffthreadVideo
        src={staticFile('rec/live.mp4')}
        trimBefore={Math.round(seg.from * FPS)}
        playbackRate={(seg.to - seg.from) / seg.seconds}
        muted
        style={{width: '100%', height: '100%'}}
      />
      <div style={{position: 'absolute', top: 120, left: 0, right: 0, display: 'flex', justifyContent: 'center', opacity: k}}>
        <div
          style={{
            fontFamily: mono,
            fontSize: 34,
            letterSpacing: 2,
            color: C.paper,
            background: `${C.navy}ee`,
            padding: '12px 28px',
            borderRadius: 10,
          }}
        >
          ⏩ {seg.label}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Problem: React.FC<{seg: Extract<Seg, {kind: 'problem'}>}> = ({seg}) => (
  <OffthreadVideo
    src={staticFile('rec/problem.mp4')}
    trimBefore={Math.round(seg.from * FPS)}
    playbackRate={seg.rate}
    muted
    style={{width: '100%', height: '100%'}}
  />
);

const Gen: React.FC<{seg: Extract<Seg, {kind: 'gen'}>}> = ({seg}) => (
  <AbsoluteFill>
  <OffthreadVideo
    src={staticFile(seg.file)}
    trimBefore={Math.round(seg.from * FPS)}
    playbackRate={seg.rate}
    muted
    style={{width: '100%', height: '100%', objectFit: 'cover'}}
  />
    <div style={{position: 'absolute', top: 36, right: 44, fontFamily: mono, fontSize: 20, letterSpacing: 2, color: '#ffffffaa'}}>
      AI-GENERATED ILLUSTRATION
    </div>
  </AbsoluteFill>
);

const Outro: React.FC = () => (
  <AbsoluteFill>
    <Sequence durationInFrames={80}>
      <Intro />
    </Sequence>
    <Sequence from={80}>
      <Freeze frame={80}>
        <Intro />
      </Freeze>
    </Sequence>
  </AbsoluteFill>
);

// Subtitles: what is said, in source seconds of each recording (Gemini
// transcript, lightly cleaned). Mapped through the edit below.
const CAPS: {src: 'hook' | 'live'; from: number; to: number; text: string}[] = [
  {src: 'hook', from: 0, to: 2.9, text: 'This toilet is 55 centimetres wide.'},
  {src: 'hook', from: 2.9, to: 4.9, text: 'I can walk in…'},
  {src: 'hook', from: 4.9, to: 8.5, text: "someone in a wheelchair can't even fit inside."},
  {src: 'hook', from: 8.5, to: 13.6, text: 'And the worst part? Someone signed off on this plan.'},
  {src: 'live', from: 0.9, to: 7.4, text: "Hi, I'm Aziz, a civil engineer and AI engineer. I've seen how plans get checked by hand, with a ruler, and it takes hours."},
  {src: 'live', from: 7.4, to: 15.0, text: 'Welcome to ConformScope, where we ask one fundamental question:'},
  {src: 'live', from: 15.0, to: 20.0, text: 'Can a wheelchair live in this home?'},
  {src: 'live', from: 23.4, to: 32.4, text: "Step one: reading the plan. Muse Spark, Meta's model, reads the room names and the scale."},
  {src: 'live', from: 32.4, to: 43.7, text: 'Step two: each room is cut out using SAM 3.1, and we get its type and its area, corner by corner.'},
  {src: 'live', from: 43.7, to: 48.8, text: "Step three: the walls go up. Now it's a home, not a drawing."},
  {src: 'live', from: 63.1, to: 67.4, text: 'The verdict: the WC here only fits Ø1.40 m.'},
  {src: 'live', from: 67.4, to: 70.2, text: "A wheelchair can't turn in it."},
  {src: 'live', from: 71.0, to: 81.2, text: "Step six: the fix. Move one wall 10 cm. On paper, it's free. In concrete, it's a renovation."},
  {src: 'live', from: 83.3, to: 88.0, text: "Next, let's go and check a plan."},
  {src: 'live', from: 89.4, to: 93.95, text: "Here I'll put in a real apartment plan."},
  {src: 'live', from: 231.2, to: 235.7, text: 'OK, it finished. Every room is measured.'},
  {src: 'live', from: 235.7, to: 240.2, text: 'Green is where a wheelchair can turn.'},
  {src: 'live', from: 240.2, to: 244.1, text: "Red means it can't."},
  {src: 'live', from: 244.1, to: 252.7, text: 'Take this room, which was correctly detected as a WC.'},
  {src: 'live', from: 252.7, to: 262.3, text: "The issue: the 1.50 m rule isn't met here. It's only 1.26 m."},
  {src: 'live', from: 292.0, to: 298.3, text: 'Here we check if a person in a wheelchair can reach every room.'},
  {src: 'live', from: 314.0, to: 329.8, text: "In this example, the wheelchair reaches only 10 of the 30 rooms. It stops in the WC, because it's missing four centimetres."},
  {src: 'live', from: 329.8, to: 337.25, text: 'Next: it explains the failures and proposes fixes.'},
  {src: 'live', from: 356.05, to: 367.1, text: 'It uses an open model, Muse Spark Open, to double-check each non-compliant room.'},
  {src: 'live', from: 392.2, to: 398.3, text: 'Finally, we can export the report and give it straight to the auditor.'},
  {src: 'live', from: 409.9, to: 414.6, text: "It has every room, the doors, what's accessible and what's not."},
];

// Long lines are split into chunks of ≤ 8 words, timed by length.
const CHUNKS = CAPS.flatMap((c) => {
  const words = c.text.split(' ');
  const n = Math.ceil(words.length / 8);
  const per = Math.ceil(words.length / n);
  const parts = Array.from({length: n}, (_, i) => words.slice(i * per, (i + 1) * per).join(' '));
  const total = parts.reduce((a, p) => a + p.length, 0);
  let at = c.from;
  return parts.map((p) => {
    const d = ((c.to - c.from) * p.length) / total;
    const chunk = {src: c.src, from: at, to: at + d, text: p};
    at += d;
    return chunk;
  });
});

const Subtitles: React.FC = () => {
  const frame = useCurrentFrame();
  const item = TIMELINE.find(({start, frames}) => frame >= start && frame < start + frames);
  if (!item) return null;
  const {seg, start} = item;
  const local = (frame - start) / FPS;
  let src: 'hook' | 'live';
  let t: number;
  if (seg.kind === 'hook') {
    src = 'hook';
    t = seg.from + local;
  } else if (seg.kind === 'live') {
    src = 'live';
    t = seg.from + local * (seg.rate ?? TALK);
  } else if (seg.kind === 'handcheck') {
    src = 'live';
    t = seg.from + local * TALK;
  } else return null;
  const c = CHUNKS.find((k) => k.src === src && t >= k.from && t < k.to);
  if (!c) return null;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 46, display: 'flex', justifyContent: 'center', pointerEvents: 'none'}}>
      <div
        style={{
          maxWidth: 1400,
          textAlign: 'center',
          fontFamily: body,
          fontWeight: 600,
          fontSize: 44,
          lineHeight: 1.25,
          color: '#fff',
          background: '#0d1a2ecc',
          padding: '10px 26px',
          borderRadius: 10,
        }}
      >
        {c.text}
      </div>
    </div>
  );
};

// Music (Lyria 3.5, generated for this film): low under the voice, up where nobody speaks.
const musicLevel = (frame: number) => {
  for (const {seg, start, frames} of TIMELINE) {
    if (frame >= start && frame < start + frames) {
      return seg.kind === 'problem' || seg.kind === 'ff' || seg.kind === 'outro' || seg.kind === 'gen' ? 0.45 : 0.1;
    }
  }
  return 0.1;
};

export const Final: React.FC = () => {
  const frame = useCurrentFrame();
  const end = interpolate(frame, [FINAL_DURATION - 30, FINAL_DURATION], [1, 0], clamp);
  return (
    <AbsoluteFill style={{background: C.ink}}>
      {TIMELINE.map(({seg, start, frames}, i) => (
        <Sequence key={i} from={start} durationInFrames={frames}>
          {seg.kind === 'hook' && <Hook seg={seg} frames={frames} />}
          {seg.kind === 'live' && <Live seg={seg} frames={frames} />}
          {seg.kind === 'handcheck' && <HandCheckSeg seg={seg} frames={frames} />}
          {seg.kind === 'ff' && <FastForward seg={seg} frames={frames} />}
          {seg.kind === 'problem' && <Problem seg={seg} />}
          {seg.kind === 'gen' && <Gen seg={seg} />}
          {seg.kind === 'outro' && <Outro />}
        </Sequence>
      ))}
      <Subtitles />
      <Audio
        src={staticFile('rec/music.mp3')}

        volume={(f) => {
          // Smooth the level changes over ~10 frames, and fade at the very end.
          let v = 0;
          for (let d = -5; d <= 5; d++) v += musicLevel(f + d);
          return (v / 11) * interpolate(f, [FINAL_DURATION - 30, FINAL_DURATION], [1, 0], clamp);
        }}
      />
      <AbsoluteFill style={{background: '#000', opacity: 1 - end, pointerEvents: 'none'}} />
    </AbsoluteFill>
  );
};
