import {loadFont as loadDisplay} from '@remotion/google-fonts/ArchivoNarrow';
import {loadFont as loadBody} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';
import {linearTiming, TransitionSeries} from '@remotion/transitions';
import {slide} from '@remotion/transitions/slide';
import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const display = loadDisplay('normal', {weights: ['600', '700'], subsets: ['latin']}).fontFamily;
const body = loadBody('normal', {weights: ['400', '500', '600'], subsets: ['latin']}).fontFamily;
const mono = loadMono('normal', {weights: ['500'], subsets: ['latin']}).fontFamily;

// Brand tokens, from web/app/page.module.css.
const C = {
  ink: '#0d1a2e',
  navy: '#1d3557',
  sea: '#2a6f97',
  sky: '#4ea8de',
  paper: '#f4f7fb',
  muted: '#9fb0c4',
  ok: '#43a047',
  bad: '#e53935',
};

// Beat lengths in frames (30 fps). Retime these to match your voice-over.
const BEATS = {people: 240, ageing: 180, law: 300, homes: 180};
const FADE = 15;
export const PROBLEM_DURATION =
  BEATS.people + BEATS.ageing + BEATS.law + BEATS.homes - 3 * FADE;

/* ---------- motion helpers ---------- */

const useEnter = (delay: number) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping: 200}, durationInFrames: 24});
};

const Rise: React.FC<{delay?: number; children: React.ReactNode; style?: React.CSSProperties}> = ({
  delay = 0,
  children,
  style,
}) => {
  const p = useEnter(delay);
  return (
    <div style={{opacity: p, transform: `translateY(${(1 - p) * 40}px)`, ...style}}>{children}</div>
  );
};

const useCount = (to: number, delay: number, duration = 45) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [delay, delay + duration], [0, to], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
};

/* ---------- shared pieces ---------- */

const Big: React.FC<{children: React.ReactNode; color?: string; size?: number}> = ({
  children,
  color = C.paper,
  size = 260,
}) => (
  <div
    style={{
      fontFamily: display,
      fontWeight: 700,
      fontSize: size,
      lineHeight: 0.95,
      letterSpacing: -4,
      color,
      fontVariantNumeric: 'tabular-nums',
    }}
  >
    {children}
  </div>
);

const Line: React.FC<{children: React.ReactNode; size?: number; color?: string}> = ({
  children,
  size = 56,
  color = C.paper,
}) => (
  <div style={{fontFamily: body, fontWeight: 500, fontSize: size, lineHeight: 1.2, color}}>
    {children}
  </div>
);

const Source: React.FC<{children: React.ReactNode}> = ({children}) => {
  const p = useEnter(30);
  return (
    <div
      style={{
        position: 'absolute',
        left: 120,
        bottom: 80,
        opacity: p * 0.75,
        fontFamily: mono,
        fontWeight: 500,
        fontSize: 24,
        color: C.muted,
        letterSpacing: 1,
      }}
    >
      SOURCE · {children}
    </div>
  );
};

const Person: React.FC<{color: string; size: number}> = ({color, size}) => (
  <svg width={size} height={size * 1.6} viewBox="0 0 50 80">
    <circle cx="25" cy="13" r="11" fill={color} />
    <path d="M6 76 V44 a19 19 0 0 1 38 0 V76 Z" fill={color} />
  </svg>
);

/** Six figures pop in one by one; the highlighted one lights up afterwards. */
const SixPeople: React.FC<{delay: number; highlight: string}> = ({delay, highlight}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const lit = spring({frame: frame - delay - 40, fps, config: {damping: 14}});
  return (
    <div style={{display: 'flex', gap: 34, alignItems: 'flex-end'}}>
      {Array.from({length: 6}).map((_, i) => {
        const p = spring({frame: frame - delay - i * 4, fps, config: {damping: 200}});
        const isLit = i === 5;
        return (
          <div
            key={i}
            style={{
              opacity: p,
              transform: `translateY(${(1 - p) * 30}px) scale(${isLit ? 1 + lit * 0.18 : 1})`,
              transformOrigin: 'bottom center',
            }}
          >
            <Person color={isLit && lit > 0.5 ? highlight : 'rgba(244,247,251,0.22)'} size={78} />
          </div>
        );
      })}
    </div>
  );
};

const Stage: React.FC<{children: React.ReactNode}> = ({children}) => (
  <AbsoluteFill style={{padding: '0 120px', justifyContent: 'center'}}>{children}</AbsoluteFill>
);

/* ---------- beats ---------- */

// "Around the world, 1.3 billion people, about 1 in 6, live with a significant disability."
const PeopleBeat: React.FC = () => {
  const n = useCount(1.3, 6, 50);
  return (
    <Stage>
      <Rise delay={0}>
        <Line size={44} color={C.sky}>
          Around the world
        </Line>
      </Rise>
      <Rise delay={4}>
        <Big>{n.toFixed(1)} billion</Big>
      </Rise>
      <Rise delay={40}>
        <Line>people live with a significant disability.</Line>
      </Rise>
      <div style={{display: 'flex', alignItems: 'center', gap: 60, marginTop: 70}}>
        <SixPeople delay={80} highlight={C.sky} />
        <Rise delay={125}>
          <Big size={120} color={C.sky}>
            1 in 6
          </Big>
        </Rise>
      </div>
      <Source>WHO, Global report on health equity for persons with disabilities, 2022</Source>
    </Stage>
  );
};

// "And by 2050, 1 in 6 people will be over 65."
const AgeingBeat: React.FC = () => {
  const year = Math.round(useCount(2050 - 2024, 0, 40)) + 2024;
  return (
    <Stage>
      <Rise delay={0}>
        <Line size={44} color={C.sky}>
          And by
        </Line>
      </Rise>
      <Rise delay={2}>
        <Big>{year}</Big>
      </Rise>
      <div style={{display: 'flex', alignItems: 'center', gap: 60, marginTop: 50}}>
        <SixPeople delay={30} highlight="#f2b84b" />
        <Rise delay={70}>
          <Line size={64}>
            <span style={{color: '#f2b84b', fontWeight: 600}}>1 in 6</span> people
            <br />
            will be over 65.
          </Line>
        </Rise>
      </div>
      <Source>UN DESA, World Population Ageing</Source>
    </Stage>
  );
};

// "In France, the law demanded accessible public buildings back in 2005.
//  Twenty years later, only about 900,000 of nearly 2 million are compliant."
const LawBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const fill = interpolate(frame, [130, 200], [0, 0.46], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });
  const compliant = Math.round(useCount(900, 130, 70));
  const barIn = useEnter(110);
  const restIn = useEnter(215);
  return (
    <Stage>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 50}}>
        <Rise delay={0}>
          <Big size={200}>2005</Big>
        </Rise>
        <Rise delay={14} style={{paddingBottom: 24}}>
          <Line size={48}>
            France passes a law:
            <br />
            <span style={{color: C.sky}}>every public building must be accessible.</span>
          </Line>
        </Rise>
      </div>

      <Rise delay={75} style={{marginTop: 80}}>
        <Line size={44} color={C.muted}>
          20 years later…
        </Line>
      </Rise>

      <div style={{marginTop: 30, opacity: barIn, transform: `scaleX(${0.96 + barIn * 0.04})`, transformOrigin: 'left'}}>
        <div
          style={{
            position: 'relative',
            height: 64,
            borderRadius: 14,
            overflow: 'hidden',
            background: `rgba(229,57,53,${0.25 + restIn * 0.55})`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: 0,
              width: `${fill * 100}%`,
              background: C.ok,
              borderRadius: 14,
            }}
          />
        </div>
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 22}}>
          <Line size={46}>
            <span style={{color: C.ok, fontWeight: 600, fontFamily: display, fontSize: 64}}>
              ≈ {compliant.toLocaleString('en-US')},000
            </span>{' '}
            compliant
          </Line>
          <div style={{opacity: restIn, transform: `translateY(${(1 - restIn) * 20}px)`}}>
            <Line size={46}>
              of nearly <b>2 million</b> —{' '}
              <span style={{color: C.bad, fontWeight: 600}}>over half still not.</span>
            </Line>
          </div>
        </div>
      </div>
      <Source>French Ministry for Disabled People, Aug. 2024 (via Public Sénat)</Source>
    </Stage>
  );
};

// "And it isn't only public buildings. Most homes are never checked at all."
const HomesBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const strike = interpolate(frame, [70, 95], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center'}}>
      <Rise delay={0}>
        <Line size={56} color={C.muted}>
          And it isn’t only public buildings.
        </Line>
      </Rise>
      <Rise delay={30} style={{marginTop: 30}}>
        <Big size={150}>
          Most homes are{' '}
          <span style={{position: 'relative', color: C.bad}}>
            never checked
            <span
              style={{
                position: 'absolute',
                left: 0,
                bottom: 6,
                height: 10,
                width: `${strike * 100}%`,
                background: C.bad,
                borderRadius: 5,
              }}
            />
          </span>
          .
        </Big>
      </Rise>
    </AbsoluteFill>
  );
};

/* ---------- scene ---------- */

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, PROBLEM_DURATION], [0, 120]);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1400px 900px at ${30 + drift / 10}% ${20 + drift / 20}%, ${C.navy} 0%, ${C.ink} 70%)`,
      }}
    />
  );
};

export const Problem: React.FC<{overlay: boolean}> = ({overlay}) => {
  const t = linearTiming({durationInFrames: FADE});
  return (
    <AbsoluteFill style={{fontFamily: body}}>
      {overlay ? (
        // Dark scrim instead of a solid fill, so the text stays readable over B-roll.
        <AbsoluteFill
          style={{background: 'linear-gradient(90deg, rgba(13,26,46,0.85) 0%, rgba(13,26,46,0.35) 100%)'}}
        />
      ) : (
        <Background />
      )}
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={BEATS.people} name="1.3 billion">
          <PeopleBeat />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition timing={t} presentation={slide({direction: 'from-right'})} />
        <TransitionSeries.Sequence durationInFrames={BEATS.ageing} name="2050">
          <AgeingBeat />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition timing={t} presentation={slide({direction: 'from-right'})} />
        <TransitionSeries.Sequence durationInFrames={BEATS.law} name="2005 law">
          <LawBeat />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition timing={t} presentation={slide({direction: 'from-right'})} />
        <TransitionSeries.Sequence durationInFrames={BEATS.homes} name="Homes">
          <HomesBeat />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
