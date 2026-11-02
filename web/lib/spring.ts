/**
 * Apple-style spring physics for direct manipulation (WWDC 2018, "Designing
 * Fluid Interfaces"), translated to plain TypeScript so no animation library
 * is needed. A spring has no fixed duration: damping ratio + response (s)
 * define how it settles, it starts from the current (presentation) value,
 * and it carries velocity through a re-target — so a gesture can grab and
 * reverse it at any instant without a jump or a "brick wall".
 */

/** Critically damped by default: graceful, no overshoot. Add bounce only
 *  when the gesture itself carried momentum (a flick / throw). */
export const SPRING_UI = { damping: 1, response: 0.35 } as const;
export const SPRING_MOMENTUM = { damping: 0.86, response: 0.42 } as const;

export type SpringState = { x: number; v: number };

/**
 * Advance one spring axis by `dt` seconds (semi-implicit Euler, sub-stepped
 * so a long frame cannot destabilise it). Independent X/Y/(log-)zoom axes
 * are stepped separately, as Apple recommends for 2D motion.
 */
export function stepSpring(
  s: SpringState,
  target: number,
  dt: number,
  damping: number = SPRING_UI.damping,
  response: number = SPRING_UI.response,
): SpringState {
  const omega = (2 * Math.PI) / Math.max(response, 0.01);
  const stiffness = omega * omega;
  const dampingCoeff = 2 * damping * omega;
  let { x, v } = s;
  const steps = Math.max(1, Math.min(8, Math.ceil(dt / (1 / 240))));
  const h = dt / steps;
  for (let i = 0; i < steps; i++) {
    const a = -stiffness * (x - target) - dampingCoeff * v;
    v += a * h;
    x += v * h;
  }
  return { x, v };
}

export const settled = (s: SpringState, target: number, eps = 0.001, velEps = eps * 50) =>
  Math.abs(s.x - target) < eps && Math.abs(s.v) < velEps;

/**
 * Where a flick is *going*: exponential-decay projection, exactly as Apple
 * ships it — not the physics-textbook v²/(2·decel). `velocity` is units/s,
 * the result is in the same units as position.
 * decelerationRate ≈ 0.998 for normal scroll feel, 0.99 for snappier.
 */
export function projectMomentum(velocity: number, decelerationRate = 0.998): number {
  return (velocity / 1000) * (decelerationRate / (1 - decelerationRate));
}

/** Soft boundary: resistance grows the further past the bound you drag. */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  if (overshoot === 0 || dimension <= 0) return 0;
  const mag = (Math.abs(overshoot) * dimension * constant) / (dimension + constant * Math.abs(overshoot));
  return Math.sign(overshoot) * mag;
}

/** Apply {@link rubberband} to any amount `value` sits outside [min, max]. */
export function rubberClamp(value: number, min: number, max: number, dimension: number): number {
  if (value < min) return min + rubberband(value - min, dimension);
  if (value > max) return max + rubberband(value - max, dimension);
  return value;
}

export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
