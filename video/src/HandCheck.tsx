import {loadFont as loadDisplay} from '@remotion/google-fonts/ArchivoNarrow';
import {loadFont as loadBody} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';
import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {DEMO_ROOMS, PLAN_H, PLAN_W, TURNING_DIAMETER_M} from '../../web/app/demo-plan';

const display = loadDisplay('normal', {weights: ['700'], subsets: ['latin']}).fontFamily;
const body = loadBody('normal', {weights: ['500', '600'], subsets: ['latin']}).fontFamily;
const mono = loadMono('normal', {weights: ['500'], subsets: ['latin']}).fontFamily;

// Brand tokens, from web/app/page.module.css (same as Problem.tsx).
const C = {
  ink: '#0d1a2e',
  navy: '#1d3557',
  sky: '#4ea8de',
  paper: '#f4f7fb',
  muted: '#9fb0c4',
  bad: '#e53935',
  concrete: '#8d939a',
};

// Section 3, "Why it happens" (0:45–1:00): a check by hand, room by room, on
// the app's demo apartment. Tired, the checker ticks the WC, which fails
// (Ø1.40 m) — and the plan is poured in concrete with the mistake in it.
export const HAND_CHECK_DURATION = 450;
const PER_ROOM = 48; // frames per room, slow on purpose
const FIRST = 20;
const WC = DEMO_ROOMS.findIndex((r) => r.roomType === 'wc');
const MISSED = FIRST + DEMO_ROOMS.length * PER_ROOM + 20;
const POUR = MISSED + 60;

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const S = 78; // px per plan metre
const pt = ([x, y]: [number, number]) => `${x * S},${y * S}`;

const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const visiting = Math.floor((frame - FIRST) / PER_ROOM);
  const pour = interpolate(frame, [POUR, POUR + 45], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const missed = spring({frame: frame - MISSED, fps, config: {damping: 14}});
  return (
    <svg width={PLAN_W * S + 80} height={PLAN_H * S + 80} viewBox={`-40 -40 ${PLAN_W * S + 80} ${PLAN_H * S + 80}`}>
      <rect x={-40} y={-40} width={PLAN_W * S + 80} height={PLAN_H * S + 80} rx={18} fill={C.paper} />
      {DEMO_ROOMS.map((r, i) => {
        const local = frame - FIRST - i * PER_ROOM;
        const active = i === visiting && local >= 0;
        const done = local >= PER_ROOM;
        const [bx0, by0] = r.polygon[0];
        const [bx1] = r.polygon[1];
        // The ruler runs across the room's first wall, then the tick lands.
        const ruler = interpolate(local, [6, PER_ROOM - 14], [0, 1], {...clamp, easing: Easing.inOut(Easing.quad)});
        const tick = spring({frame: local - (PER_ROOM - 10), fps, config: {damping: 200}});
        const [cx, cy] = r.circle.center;
        return (
          <g key={r.name}>
            <polygon
              points={r.polygon.map(pt).join(' ')}
              fill={active ? `${C.sky}33` : 'transparent'}
              stroke={C.navy}
              strokeWidth={5}
              strokeLinejoin="round"
            />
            {active && (
              <g>
                <line
                  x1={bx0 * S}
                  y1={by0 * S + 24}
                  x2={(bx0 + (bx1 - bx0) * ruler) * S}
                  y2={by0 * S + 24}
                  stroke={C.sky}
                  strokeWidth={4}
                />
                <circle cx={(bx0 + (bx1 - bx0) * ruler) * S} cy={by0 * S + 24} r={9} fill={C.sky} />
              </g>
            )}
            {(done || tick > 0) && (
              <text
                x={cx * S}
                y={cy * S + 22}
                textAnchor="middle"
                fontFamily={display}
                fontSize={64}
                fill={C.navy}
                opacity={done ? 1 : tick}
              >
                ✓
              </text>
            )}
            {i === WC && missed > 0 && (
              <g opacity={1 - pour * 0.6}>
                <circle
                  cx={cx * S}
                  cy={cy * S}
                  r={((r.circle.diameterM / 2) * S) * (0.6 + 0.4 * missed)}
                  fill="none"
                  stroke={C.bad}
                  strokeWidth={6}
                />
                <circle
                  cx={cx * S}
                  cy={cy * S}
                  r={(TURNING_DIAMETER_M / 2) * S}
                  fill="none"
                  stroke={C.bad}
                  strokeWidth={3}
                  strokeDasharray="10 8"
                  opacity={missed}
                />
              </g>
            )}
          </g>
        );
      })}
      <rect
        x={-40}
        y={-40}
        width={PLAN_W * S + 80}
        height={(PLAN_H * S + 80) * pour}
        rx={18}
        fill={C.concrete}
        opacity={0.85}
      />
    </svg>
  );
};

/** A wall clock whose hands speed up as the check drags on. */
const Clock: React.FC = () => {
  const frame = useCurrentFrame();
  const turns = 0.02 * frame + 0.00018 * frame * frame; // hours, accelerating
  const minute = (turns % 1) * 360;
  const hour = ((turns / 12) % 1) * 360;
  const r = 230;
  return (
    <svg width={2 * r + 40} height={2 * r + 40} viewBox={`${-r - 20} ${-r - 20} ${2 * r + 40} ${2 * r + 40}`}>
      <circle r={r} fill="none" stroke={C.paper} strokeWidth={10} />
      {Array.from({length: 12}, (_, i) => (
        <line
          key={i}
          x1={0}
          y1={-r + 18}
          x2={0}
          y2={-r + (i % 3 === 0 ? 58 : 38)}
          stroke={C.muted}
          strokeWidth={i % 3 === 0 ? 8 : 4}
          transform={`rotate(${i * 30})`}
        />
      ))}
      <line x1={0} y1={0} x2={0} y2={-r * 0.5} stroke={C.paper} strokeWidth={14} strokeLinecap="round" transform={`rotate(${hour})`} />
      <line x1={0} y1={0} x2={0} y2={-r * 0.8} stroke={C.sky} strokeWidth={8} strokeLinecap="round" transform={`rotate(${minute})`} />
      <circle r={14} fill={C.paper} />
    </svg>
  );
};

const Caption: React.FC<{children: React.ReactNode; color?: string; from: number; to?: number}> = ({
  children,
  color = C.muted,
  from,
  to = HAND_CHECK_DURATION,
}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [from, from + 12, to - 12, to], [0, 1, 1, 0], clamp);
  return (
    <div style={{opacity: o, fontFamily: mono, fontWeight: 500, fontSize: 30, letterSpacing: 2, color}}>{children}</div>
  );
};

export const HandCheck: React.FC = () => {
  const frame = useCurrentFrame();
  const room = Math.min(DEMO_ROOMS.length, Math.max(0, Math.floor((frame - FIRST) / PER_ROOM) + 1));
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1400px 900px at 30% 20%, ${C.navy} 0%, ${C.ink} 70%)`,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-evenly',
        fontFamily: body,
      }}
    >
      <div style={{display: 'flex', flexDirection: 'column', gap: 28}}>
        <Caption from={0} to={MISSED}>
          BY HAND · ROOM {room} / {DEMO_ROOMS.length}
        </Caption>
        <Plan />
        <div style={{height: 40}}>
          <Caption from={MISSED} to={POUR} color={C.bad}>
            MISSED · WC Ø{DEMO_ROOMS[WC].circle.diameterM.toFixed(2)} m &lt; Ø{TURNING_DIAMETER_M.toFixed(2)} m
          </Caption>
          <div style={{marginTop: -40}}>
            <Caption from={POUR + 10} color={C.paper}>
              BUILT. THE MISTAKE IS IN THE CONCRETE.
            </Caption>
          </div>
        </div>
      </div>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 36}}>
        <Clock />
        <div style={{fontFamily: display, fontWeight: 700, fontSize: 64, color: C.paper}}>Room by room, by hand</div>
      </div>
    </AbsoluteFill>
  );
};
