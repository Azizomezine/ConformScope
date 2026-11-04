"use client";

import { useEffect, useRef, type MutableRefObject } from "react";
import * as THREE from "three";
import { DEMO_DOORS, DEMO_PATH, DEMO_PATH_END, DEMO_ROOMS, PLAN_H, PLAN_W, TURNING_DIAMETER_M, WALL_H, chapterAt, chapterRange } from "./demo-plan";
import { stepSpring } from "../lib/spring";

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smooth = (v: number) => { const t = clamp01(v); return t * t * (3 - 2 * t); };
// Progress across chapter i: 0 at its start, 1 at its end.
const inChapter = (p: number, i: number, share = 1) => {
  const [a, b] = chapterRange(i);
  return clamp01((p - a) / ((b - a) * share));
};

const RED = new THREE.Color(0xc62828);
const GREEN = new THREE.Color(0x2e7d32);
const PAPER = new THREE.Color(0xf7f9fb);
const INK = new THREE.Color(0x1d3557);
const WHITE = new THREE.Color(0xffffff);

function roomShape(polygon: [number, number][]) {
  const shape = new THREE.Shape();
  polygon.forEach(([x, y], i) => {
    const sx = x - PLAN_W / 2;
    const sy = -(y - PLAN_H / 2);
    if (i === 0) shape.moveTo(sx, sy); else shape.lineTo(sx, sy);
  });
  shape.closePath();
  return shape;
}

function labelSprite(text: string, color = "#1d3557") {
  const canvas = document.createElement("canvas");
  canvas.width = 512; canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.beginPath(); ctx.roundRect(56, 24, 400, 80, 28); ctx.fill();
    ctx.fillStyle = color; ctx.font = "600 44px Arial, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, 256, 66);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(2.4, 0.6, 1);
  return sprite;
}

// A flat cote: a bar with an end tick at each side, lying on the ground.
function dimensionBar(length: number, mat: THREE.Material) {
  const group = new THREE.Group();
  const bar = new THREE.Mesh(new THREE.PlaneGeometry(length, 0.045), mat);
  bar.rotation.x = -Math.PI / 2;
  group.add(bar);
  for (const side of [-1, 1]) {
    const tick = new THREE.Mesh(new THREE.PlaneGeometry(0.045, 0.36), mat);
    tick.rotation.x = -Math.PI / 2;
    tick.position.x = (side * length) / 2;
    group.add(tick);
  }
  return group;
}

export function BuildingScene({
  progressRef, reducedMotion, locale = "en", dark = false, onFallback,
}: {
  progressRef: MutableRefObject<number>;
  reducedMotion: boolean;
  locale?: string;
  dark?: boolean;
  onFallback: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const fallbackRef = useRef(onFallback);
  useEffect(() => { fallbackRef.current = onFallback; }, [onFallback]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    } catch {
      fallbackRef.current();
      return;
    }
    if (!renderer.getContext()) { fallbackRef.current(); return; }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(dark ? 0x0d1622 : 0xe8edf2);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(8, 14, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -10; sun.shadow.camera.right = 10;
    sun.shadow.camera.top = 10; sun.shadow.camera.bottom = -10;
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0xdfeaff, 0.45);
    fill.position.set(-8, 6, -8);
    scene.add(fill);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(60, 60),
      new THREE.MeshStandardMaterial({ color: dark ? 0x16222f : 0xd7dee5, roughness: 0.95 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.06;
    ground.receiveShadow = true;
    scene.add(ground);

    // Half-metre graph paper under the plan.
    const grid = new THREE.GridHelper(40, 80, 0xc3ccd6, 0xc3ccd6);
    const gridMat = grid.material as THREE.Material;
    gridMat.transparent = true; gridMat.opacity = 0.55;
    grid.position.y = -0.05;
    scene.add(grid);

    const building = new THREE.Group();
    scene.add(building);
    const walls: THREE.Mesh[] = [];
    const wallMats: THREE.MeshStandardMaterial[] = [];
    const floors: { mat: THREE.MeshStandardMaterial; color: THREE.Color }[] = [];
    const circles: { disc: THREE.Mesh; ring: THREE.Mesh; mats: THREE.MeshBasicMaterial[]; ok: boolean }[] = [];
    const labelMats: THREE.SpriteMaterial[] = [];
    const labelSprites: THREE.Sprite[] = [];

    for (const room of DEMO_ROOMS) {
      const shape = roomShape(room.polygon);
      const floorGeo = new THREE.ShapeGeometry(shape);
      floorGeo.rotateX(-Math.PI / 2);
      const floorMat = new THREE.MeshStandardMaterial({ color: PAPER.clone(), roughness: 0.85, metalness: 0 });
      const floor = new THREE.Mesh(floorGeo, floorMat);
      floor.position.y = 0.02;
      floor.receiveShadow = true;
      building.add(floor);
      floors.push({ mat: floorMat, color: new THREE.Color(room.color) });

      const wallMat = new THREE.MeshStandardMaterial({ color: INK.clone(), roughness: 0.55 });
      wallMats.push(wallMat);
      for (let i = 0; i < room.polygon.length; i++) {
        const [x1, y1] = room.polygon[i];
        const [x2, y2] = room.polygon[(i + 1) % room.polygon.length];
        const len = Math.hypot(x2 - x1, y2 - y1);
        if (len < 0.01) continue;
        // Leave a 0.92 m gap where a door centre sits on this edge.
        let spans: [number, number][] = [[0, 1]];
        for (const [dx, dy] of DEMO_DOORS) {
          const t = ((dx - x1) * (x2 - x1) + (dy - y1) * (y2 - y1)) / (len * len);
          const px = x1 + t * (x2 - x1); const py = y1 + t * (y2 - y1);
          if (t > 0.1 && t < 0.9 && Math.hypot(dx - px, dy - py) < 0.01) {
            const half = 0.46 / len;
            spans = [[0, t - half], [t + half, 1]];
          }
        }
        for (const [a, b] of spans) {
          const sl = (b - a) * len;
          if (sl < 0.05) continue;
          const wall = new THREE.Mesh(new THREE.BoxGeometry(sl + 0.14, 1, 0.14), wallMat);
          wall.position.set(
            x1 + ((a + b) / 2) * (x2 - x1) - PLAN_W / 2, 0.5,
            y1 + ((a + b) / 2) * (y2 - y1) - PLAN_H / 2);
          wall.rotation.y = -Math.atan2(y2 - y1, x2 - x1);
          wall.castShadow = true; wall.receiveShadow = true;
          building.add(wall); walls.push(wall);
        }
      }

      const ok = room.circle.conforme;
      const cMat = new THREE.MeshBasicMaterial({
        color: ok ? 0x2e7d32 : 0xc62828, transparent: true, opacity: 0,
        side: THREE.DoubleSide, depthWrite: false,
      });
      const disc = new THREE.Mesh(new THREE.CircleGeometry(room.circle.diameterM / 2, 48), cMat);
      disc.rotation.x = -Math.PI / 2;
      disc.position.set(room.circle.center[0] - PLAN_W / 2, 0.07, room.circle.center[1] - PLAN_H / 2);
      building.add(disc);
      const rMat = new THREE.MeshBasicMaterial({
        color: ok ? 0x2e7d32 : 0xc62828, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false,
      });
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(room.circle.diameterM / 2 - 0.045, room.circle.diameterM / 2, 48), rMat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.copy(disc.position); ring.position.y = 0.08;
      building.add(ring);
      circles.push({ disc, ring, mats: [cMat, rMat], ok });

      const label = labelSprite(locale === "fr" ? room.nameFr : room.name);
      label.position.set(
        room.circle.center[0] - PLAN_W / 2,
        0.45,
        room.circle.center[1] - PLAN_H / 2 - 1.05,
      );
      (label.material as THREE.SpriteMaterial).opacity = 0;
      building.add(label); labelMats.push(label.material as THREE.SpriteMaterial); labelSprites.push(label);
    }

    // Overall cotes along the top and left edges of the plan.
    const dimMat = new THREE.MeshBasicMaterial({ color: 0x2a6f97, transparent: true, opacity: 0, depthWrite: false });
    const dims = new THREE.Group();
    const topDim = dimensionBar(PLAN_W, dimMat);
    topDim.position.set(0, 0.03, -PLAN_H / 2 - 0.7);
    const leftDim = dimensionBar(PLAN_H, dimMat);
    leftDim.rotation.y = Math.PI / 2;
    leftDim.position.set(-PLAN_W / 2 - 0.7, 0.03, 0);
    dims.add(topDim, leftDim);
    const dimLabels = [
      { sprite: labelSprite(`${PLAN_W.toFixed(2).replace(".", ",")} m`, "#2a6f97"), at: [0, -PLAN_H / 2 - 0.7] },
      { sprite: labelSprite(`${PLAN_H.toFixed(2).replace(".", ",")} m`, "#2a6f97"), at: [-PLAN_W / 2 - 0.7, 0] },
    ];
    for (const { sprite, at } of dimLabels) {
      sprite.scale.set(1.8, 0.45, 1);
      sprite.position.set(at[0], 0.3, at[1]);
      (sprite.material as THREE.SpriteMaterial).opacity = 0;
      dims.add(sprite);
    }
    scene.add(dims);

    // Minimal fixtures so WC, bathroom and kitchen read at close range.
    const fixtureMat = new THREE.MeshStandardMaterial({ color: 0xf2f5f8, roughness: 0.4 });
    const fixtures = new THREE.Group();
    const toilet = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.22, 0.42, 20), fixtureMat);
    toilet.position.set(7.9 - PLAN_W / 2, 0.23, 6.45 - PLAN_H / 2);
    toilet.castShadow = true;
    const basin = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.5, 0.45), fixtureMat);
    basin.position.set(5.0 - PLAN_W / 2, 0.27, 6.7 - PLAN_H / 2);
    basin.castShadow = true;
    const counter = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.55, 0.55), fixtureMat);
    counter.position.set(7.8 - PLAN_W / 2, 0.3, 0.32 - PLAN_H / 2);
    counter.castShadow = true;
    fixtures.add(toilet, basin, counter);
    building.add(fixtures);

    // A small wheelchair built from primitives: two big rear wheels, two
    // casters, seat, backrest and armrests. It faces +x in local space.
    const chair = new THREE.Group();
    const chairMats: THREE.MeshStandardMaterial[] = [];
    const chairMat = (color: number, roughness: number) => {
      const m = new THREE.MeshStandardMaterial({ color, roughness, transparent: true, opacity: 0 });
      chairMats.push(m);
      return m;
    };
    const rearWheels: THREE.Mesh[] = [];
    for (const side of [-1, 1]) {
      const wheel = new THREE.Mesh(new THREE.TorusGeometry(0.27, 0.035, 10, 28), chairMat(0x22282e, 0.6));
      wheel.position.set(-0.22, 0.27, side * 0.29);
      wheel.castShadow = true;
      chair.add(wheel); rearWheels.push(wheel);
      const caster = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.028, 8, 20), chairMat(0x22282e, 0.6));
      caster.position.set(0.3, 0.09, side * 0.24);
      chair.add(caster);
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.05, 0.05), chairMat(0x1d3557, 0.5));
      arm.position.set(-0.02, 0.68, side * 0.26);
      chair.add(arm);
    }
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.07, 0.46), chairMat(0x1d3557, 0.5));
    seat.position.set(0, 0.47, 0); seat.castShadow = true;
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.52, 0.46), chairMat(0x1d3557, 0.5));
    back.position.set(-0.27, 0.76, 0); back.castShadow = true;
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.04, 0.36), chairMat(0x5a6b7d, 0.4));
    foot.position.set(0.4, 0.12, 0);
    chair.add(seat, back, foot);
    chair.visible = false;
    building.add(chair);

    // Route in world space (same mapping as the circles): entrance of the
    // living room to the WC door, then one last stretch into the WC.
    const route = [...DEMO_PATH, DEMO_PATH_END].map(([x, y]) =>
      new THREE.Vector3(x - PLAN_W / 2, 0, y - PLAN_H / 2));
    const segLens: number[] = [];
    let routeLen = 0; let stopLen = 0;
    for (let i = 0; i < route.length - 1; i++) {
      const l = route[i].distanceTo(route[i + 1]);
      segLens.push(l); routeLen += l;
      if (i < route.length - 2) stopLen += l;
    }
    const routeAt = (dist: number, out: THREE.Vector3) => {
      let d = Math.min(Math.max(dist, 0), routeLen);
      for (let i = 0; i < segLens.length; i++) {
        if (d <= segLens[i] || i === segLens.length - 1) {
          out.lerpVectors(route[i], route[i + 1], segLens[i] === 0 ? 0 : d / segLens[i]);
          return Math.atan2(route[i + 1].z - route[i].z, route[i + 1].x - route[i].x);
        }
        d -= segLens[i];
      }
      out.copy(route[route.length - 1]);
      return 0;
    };

    // Green badge that appears over the WC once the fix lands.
    const fixBadge = labelSprite(locale === "fr" ? "\u00d8 1,50 m" : "\u00d8 1.50 m", "#2e7d32");
    fixBadge.scale.set(1.9, 0.48, 1);
    fixBadge.position.set(DEMO_PATH_END[0] - PLAN_W / 2, WALL_H + 0.75, DEMO_PATH_END[1] - PLAN_H / 2 - 0.9);
    (fixBadge.material as THREE.SpriteMaterial).opacity = 0;
    building.add(fixBadge);

    let raf = 0;
    let current = 0;
    let currentVel = 0;
    let lastNow: number | null = null;
    const topPos = new THREE.Vector3(0, 13, 7);
    const endPos = new THREE.Vector3(8, 10.5, 11);
    const target = new THREE.Vector3(0, 0.4, 0);
    // Close-up on the first room that fails, for the verdict chapter.
    const failing = DEMO_ROOMS.find((r) => !r.circle.conforme) ?? DEMO_ROOMS[0];
    const failAt = new THREE.Vector3(failing.circle.center[0] - PLAN_W / 2, 0.3, failing.circle.center[1] - PLAN_H / 2);
    // Steep enough that the walls do not hide the circle on the floor.
    const closePos = failAt.clone().add(new THREE.Vector3(1.4, 8.6, 4.2));
    const closeTarget = failAt.clone().lerp(target, 0.2);
    const tmp = new THREE.Vector3();
    const look = new THREE.Vector3();

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // On wide screens the copy sits on the left: slide the plan to the right.
      if (camera.aspect > 1.2) camera.setViewOffset(w, h, -w * 0.25, 0, w, h);
      // On portrait phones the intro/card cover the top and bottom: centre the plan between them.
      else if (camera.aspect < 0.8) camera.setViewOffset(w, h, 0, h * 0.3, w, h);
      else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let visible = true;
    const tick = (now: number) => {
      // Off-screen: stop the loop entirely (the observer restarts it).
      // Rendering at full DPR with shadows while the reader is elsewhere
      // on the page was a permanent GPU/CPU drain.
      if (!visible) { raf = 0; return; }
      raf = requestAnimationFrame(tick);
      const goal = clamp01(progressRef.current);
      const prevNow = lastNow; lastNow = now;
      if (reducedMotion) {
        // No scroll-linked motion: jump to the end state of the current chapter.
        const ch = chapterAt(goal);
        current = ch < 0 ? 0 : chapterRange(ch)[1]; currentVel = 0;
      } else if (Math.abs(goal - current) > 0.25) {
        currentVel = 0;
        // A rail click or jump scroll: land the model on the named chapter at once (vel. reset below).
        current = goal;
      } else {
        // Critically damped spring (response 0.45 s): starts from the current
        // value, carries velocity through scroll reversals, frame-rate independent.
        const dt = Math.min(0.05, Math.max(0.001, prevNow === null ? 1 / 60 : (now - prevNow) / 1000));
        const stepped = stepSpring({ x: current, v: currentVel }, goal, dt, 1, 0.45);
        current = stepped.x; currentVel = stepped.v;
        if (Math.abs(goal - current) < 0.0005) current = goal;
      }

      const dimT = clamp01((current - 0.04) / 0.08) * (1 - inChapter(current, 2, 0.4));
      const roomT = smooth(inChapter(current, 1, 0.45));
      const labelT = inChapter(current, 1);
      const wallT = smooth(inChapter(current, 2));
      const circleT = smooth(inChapter(current, 3, 0.45));
      const verdictT = smooth(inChapter(current, 4, 0.6));
      const fixT = smooth(inChapter(current, 5, 0.7));

      dimMat.opacity = dimT * 0.9;
      for (const { sprite } of dimLabels) (sprite.material as THREE.SpriteMaterial).opacity = dimT;
      for (const { mat, color } of floors) mat.color.lerpColors(PAPER, color, roomT);
      for (const mat of wallMats) mat.color.lerpColors(INK, WHITE, wallT);
      for (const wall of walls) {
        wall.scale.y = Math.max(0.02, wallT * WALL_H);
        // Sit on top of the floors so the flat plan still shows its inner walls.
        wall.position.y = wall.scale.y / 2 + 0.02;
      }
      const pulse = reducedMotion ? 1 : 0.75 + 0.25 * Math.sin(now / 260);
      // RED/GREEN are module constants: allocating them per frame churned GC.
      for (const c of circles) {
        // The fix: the failing circle grows to the required size and turns green.
        const grow = c.ok ? 1 : 1 + fixT * (TURNING_DIAMETER_M / failing.circle.diameterM - 1);
        const s = Math.max(0.001, circleT * grow);
        c.disc.scale.set(s, s, 1); c.ring.scale.set(s, s, 1);
        if (!c.ok) for (const m of c.mats) m.color.lerpColors(RED, GREEN, fixT);
        // In the verdict chapter, the rooms that pass step back and the failing one pulses.
        const emphasis = c.ok ? 1 - verdictT * 0.45 : 1 + verdictT * (pulse - 1);
        c.mats[0].opacity = circleT * 0.55 * emphasis;
        c.mats[1].opacity = circleT * 0.95 * emphasis;
      }
      labelMats.forEach((mat, i) => {
        mat.opacity = labelT * (circles[i].ok ? 1 - verdictT * 0.7 : 1);
      });
      for (const sprite of labelSprites) sprite.position.y = Math.max(0.45, wallT * WALL_H + 0.35);

      // Verdict chapter: the chair rolls to the WC door and stops there.
      // Fix chapter: it rolls the last stretch in, and the badge fades up.
      const chairDist = smooth(clamp01(inChapter(current, 4) / 0.65)) * stopLen
        + smooth(clamp01(inChapter(current, 5) / 0.5)) * (routeLen - stopLen);
      const chairFade = clamp01(inChapter(current, 4) / 0.12);
      chair.visible = chairFade > 0;
      if (chair.visible) {
        const heading = routeAt(chairDist, tmp);
        chair.position.set(tmp.x, 0.03, tmp.z);
        chair.rotation.y = -heading;
        for (const m of chairMats) m.opacity = chairFade;
        for (const w of rearWheels) w.rotation.z = -chairDist / 0.27;
      }
      (fixBadge.material as THREE.SpriteMaterial).opacity = fixT;
      fixBadge.position.y = WALL_H + 0.55 + fixT * 0.25;

      const camT = smooth((current - chapterRange(2)[0]) / (chapterRange(3)[1] - chapterRange(2)[0]));
      const closeW = verdictT * (1 - fixT);
      tmp.lerpVectors(topPos, endPos, camT).lerp(closePos, closeW);
      look.copy(target).lerp(closeTarget, closeW);
      // Portrait phones need to pull back so the whole plan stays in frame.
      if (camera.aspect < 0.8) tmp.sub(look).multiplyScalar(2.1).add(look);
      camera.position.copy(tmp);
      camera.lookAt(look);
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(tick);

    const io = new IntersectionObserver(([entry]) => {
      const was = visible;
      visible = entry.isIntersecting;
      if (visible && !was && !raf) { lastNow = null; raf = requestAnimationFrame(tick); }
    }, { threshold: 0.02 });
    io.observe(host);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
      ro.disconnect();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Sprite || obj instanceof THREE.LineSegments) {
          obj.geometry?.dispose();
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          for (const m of mats) {
            const withMap = m as THREE.SpriteMaterial;
            withMap.map?.dispose();
            m.dispose();
          }
        }
      });
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, [progressRef, reducedMotion, locale, dark]);

  return <div ref={hostRef} className="building-scene" aria-label={locale === "fr" ? "Plan 2D qui devient un bâtiment 3D" : "2D plan becoming a 3D building"} role="img" />;
}
