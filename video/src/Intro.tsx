import {loadFont as loadDisplay} from '@remotion/google-fonts/ArchivoNarrow';
import {loadFont as loadBody} from '@remotion/google-fonts/IBMPlexSans';
import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

const display = loadDisplay('normal', {weights: ['700'], subsets: ['latin']}).fontFamily;
const body = loadBody('normal', {weights: ['500'], subsets: ['latin']}).fontFamily;

const C = {ink: '#0d1a2e', navy: '#1d3557', sky: '#4ea8de', paper: '#f4f7fb', muted: '#9fb0c4'};

// Section 4 → 5: the name, then a paper-coloured wipe that hands over to the
// screen recording.
export const INTRO_DURATION = 120;
const WIPE = 84;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  // The Ø1.50 m turning circle is the mark: drawn on, then the name rises.
  const draw = interpolate(frame, [0, 24], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const name = spring({frame: frame - 14, fps, config: {damping: 200}});
  const line = spring({frame: frame - 32, fps, config: {damping: 200}});
  const wipe = interpolate(frame, [WIPE, INTRO_DURATION], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const r = 70;
  return (
    <AbsoluteFill style={{background: `radial-gradient(1200px 800px at 50% 40%, ${C.navy} 0%, ${C.ink} 70%)`}}>
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', gap: 34}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 40}}>
          <svg width={2 * r + 20} height={2 * r + 20} viewBox={`${-r - 10} ${-r - 10} ${2 * r + 20} ${2 * r + 20}`}>
            <circle
              r={r}
              fill="none"
              stroke={C.sky}
              strokeWidth={12}
              pathLength={1}
              strokeDasharray="1 1"
              strokeDashoffset={1 - draw}
              transform="rotate(-90)"
            />
            {/* A dimension line across the diameter, ticked at both ends. */}
            <g stroke={C.paper} strokeWidth={6} strokeLinecap="round" opacity={draw}>
              <line x1={-r + 18} y1={0} x2={r - 18} y2={0} />
              <line x1={-r + 18} y1={-14} x2={-r + 18} y2={14} />
              <line x1={r - 18} y1={-14} x2={r - 18} y2={14} />
            </g>
          </svg>
          <div
            style={{
              fontFamily: display,
              fontWeight: 700,
              fontSize: 150,
              letterSpacing: -2,
              color: C.paper,
              opacity: name,
              transform: `translateY(${(1 - name) * 40}px)`,
            }}
          >
            Conform<span style={{color: C.sky}}>Scope</span>
          </div>
        </div>
        <div
          style={{
            fontFamily: body,
            fontWeight: 500,
            fontSize: 50,
            color: C.muted,
            opacity: line,
            transform: `translateY(${(1 - line) * 24}px)`,
          }}
        >
          Can a wheelchair live in this home?
        </div>
      </AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: width * wipe,
          background: C.paper,
        }}
      />
    </AbsoluteFill>
  );
};
