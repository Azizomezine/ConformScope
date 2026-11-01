"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";
import styles from "./page.module.css";
import { DEMO_ROOMS, DEMO_STEPS, PLAN_H, PLAN_W, STORY_INTRO, TURNING_DIAMETER_M, chapterAt, chapterRange } from "./demo-plan";

const BuildingScene = dynamic(
  () => import("./building-scene").then((m) => m.BuildingScene),
  { ssr: false, loading: () => <div className={styles.sceneFallback}>Chargement du plan…</div> },
);

const FEATURES = [
  { title: "Lecture du plan", text: "Muse Spark lit les étiquettes du plan et reconnaît le type de chaque pièce." },
  { title: "Découpe des pièces", text: "SAM 3.1 découpe chaque pièce sur l'image du plan, recoin par recoin." },
  { title: "Mesure en mètres", text: "Surfaces et dimensions sont calculées par la géométrie, jamais estimées par un modèle." },
  { title: "Cercle de retournement", text: "Le plus grand cercle libre de chaque pièce est comparé au Ø1,50 m exigé." },
  { title: "Corrections à la souris", text: "Un renfoncement mal découpé, un mur manquant : cliquez pour fusionner un recoin ou tracer le mur absent. Chaque correction est stockée avec le plan." },
  { title: "Avant de signer", text: "Les logements sont approuvés sur papier. ConformScope montre qui ne pourra pas y entrer tant que c'est encore du papier." },
];

function FallbackPlan() {
  const sx = 100;
  return (
    <svg viewBox={`0 0 ${PLAN_W * sx} ${PLAN_H * sx}`} className={styles.fallbackSvg} role="img" aria-label="Plan 2D de démonstration">
      {DEMO_ROOMS.map((room) => (
        <g key={room.name}>
          <polygon points={room.polygon.map(([x, y]) => `${x * sx},${y * sx}`).join(" ")}
            fill={room.color} fillOpacity={0.55} stroke="#1d3557" strokeWidth={3} />
          <circle cx={room.circle.center[0] * sx} cy={room.circle.center[1] * sx} r={(room.circle.diameterM / 2) * sx}
            fill={room.circle.conforme ? "#2e7d32" : "#c62828"} fillOpacity={0.25}
            stroke={room.circle.conforme ? "#2e7d32" : "#c62828"} strokeWidth={4} />
          <text x={room.circle.center[0] * sx} y={room.circle.center[1] * sx - (room.circle.diameterM / 2) * sx - 12}
            textAnchor="middle" fontSize={26} fill="#1d3557" fontWeight={600}>{room.name}</text>
        </g>
      ))}
    </svg>
  );
}

const fr = (v: number, decimals: number) =>
  v.toLocaleString("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/** A number that counts up the first time it scrolls into view. */
function CountUp({ value, decimals = 0, reduced }: { value: number; decimals?: number; reduced: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    el.textContent = fr(0, decimals);
    let raf = 0;
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / 1200);
        el.textContent = fr(value * (1 - (1 - t) ** 3), decimals);
        if (t < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }, { threshold: 0.6 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [value, decimals, reduced]);
  return <span ref={ref}>{fr(value, decimals)}</span>;
}

export default function Home() {
  const trackRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef(0);
  const [step, setStep] = useState(-1);
  const [failed, setFailed] = useState(false);
  const reduced = useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );

  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const total = Math.max(1, rect.height - window.innerHeight);
        const p = Math.min(1, Math.max(0, -rect.top / total));
        progressRef.current = p;
        // CSS reads these directly, so the hero fade and rail fill skip React renders.
        stageRef.current?.style.setProperty("--intro", String(Math.min(1, p / STORY_INTRO)));
        stageRef.current?.style.setProperty("--story", String(Math.max(0, (p - STORY_INTRO) / (1 - STORY_INTRO))));
        setStep(chapterAt(p));
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, []);

  const goTo = (i: number) => {
    const el = trackRef.current;
    if (!el) return;
    const total = el.offsetHeight - window.innerHeight;
    const [a, b] = chapterRange(i);
    const top = el.getBoundingClientRect().top + window.scrollY + total * (a + (b - a) * 0.6);
    window.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
  };

  const shown = Math.max(0, step);
  const totalArea = DEMO_ROOMS.reduce((sum, r) => sum + r.areaM2, 0);
  const failing = DEMO_ROOMS.filter((r) => !r.circle.conforme).length;

  return (
    <main className={styles.landing}>
      <header className={styles.topbar}>
        <div className={styles.topbarInner}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <nav className={styles.topnav} aria-label="Sections">
            <a href="#verdict">Verdict</a>
            <a href="#fonctionnalites">Fonctionnalités</a>
          </nav>
          <Link href="/check" className={styles.navCta}>Vérifier un plan</Link>
        </div>
      </header>

      <div ref={trackRef} className={styles.story}>
        <div ref={stageRef} className={styles.stage} data-reduced={reduced}>
          <div className={styles.sceneLayer}>
            {failed ? <FallbackPlan /> : (
              <BuildingScene progressRef={progressRef} reducedMotion={reduced} onFallback={() => setFailed(true)} />
            )}
          </div>
          <div className={styles.veil} aria-hidden />

          <section className={styles.intro} data-gone={step >= 0} aria-labelledby="hero-title">
            <span className={styles.badge} style={{ "--d": 0 } as CSSProperties}><i />Accessibilité PMR</span>
            <h1 id="hero-title" style={{ "--d": 1 } as CSSProperties}>
              Can a wheelchair <span className={styles.accent}>live in this home?</span>
            </h1>
            <p style={{ "--d": 2 } as CSSProperties}>
              ConformScope lit un plan, mesure chaque pièce en mètres, et vérifie si un cercle de retournement de Ø1,50 m y tient. Faites défiler : le plan devient le bâtiment.
            </p>
            <div className={styles.actions} style={{ "--d": 3 } as CSSProperties}>
              <Link href="/check" className={styles.cta}>Essayer avec votre plan →</Link>
              <button type="button" className={styles.ctaGhost} onClick={() => goTo(0)}>Voir comment ça marche</button>
            </div>
            <p className={styles.exampleNote} style={{ "--d": 4 } as CSSProperties}>
              Exemple — appartement de démonstration, pas un logement audité.
            </p>
            <span className={styles.scrollHint} aria-hidden style={{ "--d": 5 } as CSSProperties}><span />Défiler</span>
          </section>

          <div className={styles.card} data-on={step >= 0}>
            <div className={styles.counter} aria-hidden>
              <span className={styles.counterWindow}>
                <span className={styles.counterTrack} style={{ transform: `translateY(-${(shown * 100) / DEMO_STEPS.length}%)` }}>
                  {DEMO_STEPS.map((_, i) => <span key={i}>{String(i + 1).padStart(2, "0")}</span>)}
                </span>
              </span>
              <span className={styles.counterTotal}>/ {String(DEMO_STEPS.length).padStart(2, "0")}</span>
            </div>
            <div className={styles.captions} aria-live="polite">
              {DEMO_STEPS.map((s, i) => (
                <article key={s.title} className={styles.caption} data-on={i === shown} aria-hidden={i !== shown}>
                  <span className={styles.eyebrow}>{s.eyebrow}</span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  <ul className={styles.tags}>{s.tags.map((t) => <li key={t}>{t}</li>)}</ul>
                </article>
              ))}
            </div>
            <span className={styles.dots}>{DEMO_STEPS.map((s, i) => <i key={s.title} data-on={i === shown} />)}</span>
            {failed && <p className={styles.exampleNote}>Votre navigateur ne lance pas WebGL : voici le même plan en 2D.</p>}
          </div>

          <nav className={styles.rail} data-on={step >= 0} aria-label="Étapes de la démonstration">
            <span className={styles.railLine}><span className={styles.railFill} /></span>
            <ol>
              {DEMO_STEPS.map((s, i) => (
                <li key={s.title}>
                  <button type="button" onClick={() => goTo(i)} data-state={i === step ? "on" : i < step ? "done" : "todo"}
                    aria-current={i === step ? "step" : undefined}>
                    <i />{s.eyebrow}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        </div>
      </div>

      <section id="verdict" className={styles.band}>
        <div className={styles.wrap}>
          <div className={styles.split}>
            <div className={styles.sectionHead}>
              <span className={styles.eyebrow}>La démo, en chiffres</span>
              <h2>Le verdict vient de la géométrie</h2>
              <p>Muse Spark lit les étiquettes du plan et SAM 3.1 découpe les pièces sur les images. Ensuite, la géométrie mesure : le plus grand cercle libre de chaque pièce est comparé à Ø1,50 m. Aucune sortie de modèle ne décide du verdict.</p>
            </div>
            <ul className={styles.verdictList}>
              {DEMO_ROOMS.map((room) => (
                <li key={room.name}>
                  <span className={styles.swatch} style={{ background: room.color }} />
                  <strong>{room.name}</strong>
                  <span className={styles.area}>{fr(room.areaM2, 1)} m²</span>
                  <span className={room.circle.conforme ? styles.pillOk : styles.pillBad}>{room.verdict}</span>
                </li>
              ))}
            </ul>
          </div>
          <dl className={styles.stats}>
            <div><dt>Pièces découpées</dt><dd><CountUp value={DEMO_ROOMS.length} reduced={reduced} /></dd></div>
            <div><dt>Surface mesurée</dt><dd><CountUp value={totalArea} decimals={1} reduced={reduced} /><small> m²</small></dd></div>
            <div><dt>Cercle exigé</dt><dd><small>Ø</small><CountUp value={TURNING_DIAMETER_M} decimals={2} reduced={reduced} /><small> m</small></dd></div>
            <div data-bad><dt>Pièce qui ne passe pas</dt><dd><CountUp value={failing} reduced={reduced} /></dd></div>
          </dl>
          <p className={styles.exampleNote}>Appartement de démonstration, pas un logement audité.</p>
        </div>
      </section>

      <section id="fonctionnalites" className={`${styles.wrap} ${styles.featuresSection}`}>
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>Fonctionnalités</span>
          <h2>Du plan papier au verdict PMR</h2>
          <p>Lire, découper, mesurer, corriger : chaque étape reste visible et vérifiable.</p>
        </div>
        <div className={styles.features}>
          {FEATURES.map((f, i) => (
            <article key={f.title} className={styles.feature}>
              <span className={styles.featureNum}>{String(i + 1).padStart(2, "0")}</span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.wrap}>
        <div className={styles.ctaBand}>
          <h2>Avant de signer, sachez si ça passe</h2>
          <p>Les personnes qui ne peuvent pas entrer dans un logement le découvrent après l&apos;emménagement. Déposez un plan et voyez-le tant que c&apos;est encore du papier.</p>
          <Link href="/check" className={styles.ctaLight}>Vérifier un plan →</Link>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.wrap}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <p>Lecture par Muse Spark, segmentation par SAM 3.1, verdict par la géométrie.</p>
        </div>
      </footer>
    </main>
  );
}
