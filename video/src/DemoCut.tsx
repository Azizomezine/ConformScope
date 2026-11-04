import {loadFont as loadBody} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';
import React from 'react';
import {AbsoluteFill, Easing, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const body = loadBody('normal', {weights: ['500', '600'], subsets: ['latin']}).fontFamily;
const mono = loadMono('normal', {weights: ['500'], subsets: ['latin']}).fontFamily;

const C = {ink: '#0d1a2e', navy: '#1d3557', sky: '#4ea8de', paper: '#f4f7fb', muted: '#9fb0c4', bad: '#e53935'};

/**
 * Section 5: the screen recording with punch-ins. Put the clip in
 * public/rec/demo.mp4 (see DEMO.md), set `file`, then fill PUNCHES with the
 * moments to zoom on — times in seconds of the clip, x / y as fractions of the
 * frame (open the clip in Remotion Studio and read them off).
 */
export const DEMO: {file: string | null; seconds: number} = {file: null, seconds: 50};

/**
 * Your face, recorded as its own file while you narrate over the screen clip
 * (OBS + NVIDIA Broadcast, see SCRIPT.md). `offset` = seconds into the cam
 * file where the screen clip's frame 0 is (clap your hands at the start to
 * find it). It stays put while the screen zooms.
 */
export const CAM: {file: string | null; offset: number} = {file: null, offset: 0};

type Punch ={from: number; to: number; x: number; y: number; zoom: number; label?: string; bad?: boolean};
export const PUNCHES: Punch[] = [
  // Example, the money shot: the red circle and its Ø label.
  // {from: 22, to: 27, x: 0.42, y: 0.55, zoom: 2.4, label: 'Ø1.20 m — needs Ø1.50 m', bad: true},
];

const EASE = Easing.inOut(Easing.cubic);
const RAMP = 0.5; // seconds in and out of each punch

const useCamera = (t: number) => {
  for (const p of PUNCHES) {
    if (t < p.from - RAMP || t > p.to + RAMP) continue;
    const k = interpolate(t, [p.from - RAMP, p.from, p.to, p.to + RAMP], [0, 1, 1, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: EASE,
    });
    return {zoom: 1 + (p.zoom - 1) * k, x: p.x, y: p.y, k, punch: p};
  }
  return {zoom: 1, x: 0.5, y: 0.5, k: 0, punch: null};
};

export const DemoCut: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const cam = useCamera(t);

  if (!DEMO.file) {
    return (
      <AbsoluteFill style={{background: C.ink, justifyContent: 'center', alignItems: 'center', gap: 24}}>
        <div style={{fontFamily: mono, fontSize: 30, color: C.sky, letterSpacing: 3}}>SECTION 5 · SCREEN RECORDING</div>
        <div style={{fontFamily: body, fontSize: 52, color: C.paper}}>Drop the clip in video/public/rec/demo.mp4</div>
        <div style={{fontFamily: mono, fontSize: 26, color: C.muted}}>then set DEMO.file in src/DemoCut.tsx</div>
      </AbsoluteFill>
    );
  }

  // Zoom about the punch's point, clamped so the frame never shows an edge.
  const ox = Math.min(Math.max(cam.x * width, width / (2 * cam.zoom)), width - width / (2 * cam.zoom));
  const oy = Math.min(Math.max(cam.y * height, height / (2 * cam.zoom)), height - height / (2 * cam.zoom));
  const tx = width / 2 - ox;
  const ty = height / 2 - oy;

  return (
    <AbsoluteFill style={{background: C.ink, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `scale(${cam.zoom}) translate(${tx * cam.k}px, ${ty * cam.k}px)`}}>
        <OffthreadVideo src={staticFile(DEMO.file)} muted style={{width: '100%', height: '100%'}} />
      </AbsoluteFill>
      {CAM.file && (
        <div
          style={{
            position: 'absolute',
            right: 48,
            bottom: 48,
            width: 300,
            height: 300,
            borderRadius: '50%',
            overflow: 'hidden',
            border: `6px solid ${C.paper}`,
            boxShadow: '0 20px 50px #0008',
            // Shrinks a little during a punch-in so the zoomed detail wins.
            transform: `scale(${1 - 0.25 * cam.k})`,
            transformOrigin: 'bottom right',
          }}
        >
          <OffthreadVideo
            src={staticFile(CAM.file)}
            trimBefore={Math.round(CAM.offset * fps)}
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </div>
      )}
      {cam.punch?.label && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 90,
            display: 'flex',
            justifyContent: 'center',
            opacity: cam.k,
            transform: `translateY(${(1 - cam.k) * 20}px)`,
          }}
        >
          <div
            style={{
              fontFamily: body,
              fontWeight: 600,
              fontSize: 44,
              color: C.paper,
              background: cam.punch.bad ? C.bad : C.navy,
              padding: '14px 30px',
              borderRadius: 12,
              boxShadow: '0 20px 50px #0007',
            }}
          >
            {cam.punch.label}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
