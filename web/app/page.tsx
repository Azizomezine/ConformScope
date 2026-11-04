"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";
import styles from "./page.module.css";
import { DEMO_ROOMS, DEMO_STEPS, DEMO_STEPS_EN, PLAN_H, PLAN_W, STORY_INTRO, TURNING_DIAMETER_M, chapterAt, chapterRange } from "./demo-plan";
import { PreferenceControls, usePreferences } from "./preferences";
import type { I18nKey } from "@/lib/i18n";
import { NEXT_RULES, RULES } from "@/lib/rules";

const BuildingScene = dynamic(
  () => import("./building-scene").then((m) => m.BuildingScene),
  { ssr: false, loading: () => <div className={styles.sceneFallback}>Loading the plan…</div> },
);

const FEATURE_KEYS: [I18nKey, I18nKey][] = [
  ["f1.title", "f1.text"], ["f2.title", "f2.text"], ["f3.title", "f3.text"],
  ["f4.title", "f4.text"], ["f5.title", "f5.text"], ["f6.title", "f6.text"],
];

function FallbackPlan() {
  const { locale, t } = usePreferences();
  const sx = 100;
  return (
    <svg viewBox={`0 0 ${PLAN_W * sx} ${PLAN_H * sx}`} className={styles.fallbackSvg} role="img" aria-label={t("scene.fallbackAria")}>
      {DEMO_ROOMS.map((room) => (
        <g key={room.name}>
          <polygon points={room.polygon.map(([x, y]) => `${x * sx},${y * sx}`).join(" ")}
            fill={room.color} fillOpacity={0.55} stroke="#1d3557" strokeWidth={3} />
          <circle cx={room.circle.center[0] * sx} cy={room.circle.center[1] * sx} r={(room.circle.diameterM / 2) * sx}
            fill={room.circle.conforme ? "#2e7d32" : "#c62828"} fillOpacity={0.25}
            stroke={room.circle.conforme ? "#2e7d32" : "#c62828"} strokeWidth={4} />
          <text x={room.circle.center[0] * sx} y={room.circle.center[1] * sx - (room.circle.diameterM / 2) * sx - 12}
            textAnchor="middle" fontSize={26} fill="#1d3557" fontWeight={600}>{locale === "fr" ? room.nameFr : room.name}</text>
        </g>
      ))}
    </svg>
  );
}

const fmt = (locale: string, v: number, decimals: number) =>
  v.toLocaleString(locale === "fr" ? "fr-FR" : "en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/** A number that counts up the first time it scrolls into view. */
function CountUp({ value, decimals = 0, reduced }: { value: number; decimals?: number; reduced: boolean }) {
  const { locale } = usePreferences();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) { if (el) el.textContent = fmt(locale, value, decimals); return; }
    el.textContent = fmt(locale, 0, decimals);
    let raf = 0;
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / 1200);
        el.textContent = fmt(locale, value * (1 - (1 - t) ** 3), decimals);
        if (t < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }, { threshold: 0.6 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [value, decimals, reduced, locale]);
  return <span ref={ref}>{fmt(locale, value, decimals)}</span>;
}

export default function Home() {
  const { locale, theme, t } = usePreferences();
  const steps = locale === "fr" ? DEMO_STEPS : DEMO_STEPS_EN;
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
  const roomName = (r: (typeof DEMO_ROOMS)[number]) => (locale === "fr" ? r.nameFr : r.name);
  const roomVerdict = (r: (typeof DEMO_ROOMS)[number]) =>
    locale === "fr" ? r.verdictFr : r.circle.conforme ? t("verdict.pass") : t("verdict.failWc");

  return (
    <main className={styles.landing}>
      <header className={styles.topbar}>
        <div className={styles.topbarInner}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <nav className={styles.topnav} aria-label="Sections">
            <a href="#verdict">{t("nav.verdict")}</a>
            <a href="#fonctionnalites">{t("nav.features")}</a>
          </nav>
          <PreferenceControls />
          <Link href="/check" className={styles.navCta}>{t("nav.check")}</Link>
        </div>
      </header>

      <div ref={trackRef} className={styles.story}>
        <div ref={stageRef} className={styles.stage} data-reduced={reduced}>
          <div className={styles.sceneLayer}>
            {failed ? <FallbackPlan /> : (
              <BuildingScene progressRef={progressRef} reducedMotion={reduced} locale={locale} dark={theme === "dark"} onFallback={() => setFailed(true)} />
            )}
          </div>
          <div className={styles.veil} aria-hidden />

          <section className={styles.intro} data-gone={step >= 0} aria-labelledby="hero-title">
            <span className={styles.badge} style={{ "--d": 0 } as CSSProperties}><i />{t("hero.badge")}</span>
            <h1 id="hero-title" style={{ "--d": 1 } as CSSProperties}>
              {t("hero.title1")} <span className={styles.accent}>{t("hero.titleAccent")}</span>
            </h1>
            <p style={{ "--d": 2 } as CSSProperties}>{t("hero.lede")}</p>
            <div className={styles.actions} style={{ "--d": 3 } as CSSProperties}>
              <Link href="/check" className={styles.cta}>{t("hero.try")}</Link>
              <button type="button" className={styles.ctaGhost} onClick={() => goTo(0)}>{t("hero.how")}</button>
            </div>
            <p className={styles.exampleNote} style={{ "--d": 4 } as CSSProperties}>{t("hero.example")}</p>
            <span className={styles.scrollHint} aria-hidden style={{ "--d": 5 } as CSSProperties}><span />{t("hero.scroll")}</span>
          </section>

          <div className={styles.card} data-on={step >= 0}>
            <div className={styles.counter} aria-hidden>
              <span className={styles.counterWindow}>
                <span className={styles.counterTrack} style={{ transform: `translateY(-${(shown * 100) / steps.length}%)` }}>
                  {steps.map((_, i) => <span key={i}>{String(i + 1).padStart(2, "0")}</span>)}
                </span>
              </span>
              <span className={styles.counterTotal}>/ {String(steps.length).padStart(2, "0")}</span>
            </div>
            <div className={styles.captions} aria-live="polite">
              {steps.map((s, i) => (
                <article key={s.title} className={styles.caption} data-on={i === shown} aria-hidden={i !== shown}>
                  <span className={styles.eyebrow}>{s.eyebrow}</span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  <ul className={styles.tags}>{s.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>
                </article>
              ))}
            </div>
            <span className={styles.dots}>{steps.map((s, i) => <i key={s.title} data-on={i === shown} />)}</span>
            {failed && <p className={styles.exampleNote}>{t("scene.webgl")}</p>}
          </div>

          <nav className={styles.rail} data-on={step >= 0} aria-label={t("scene.railAria")}>
            <span className={styles.railLine}><span className={styles.railFill} /></span>
            <ol>
              {steps.map((s, i) => (
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
              <span className={styles.eyebrow}>{t("verdict.eyebrow")}</span>
              <h2>{t("verdict.title")}</h2>
              <p>{t("verdict.body")}</p>
            </div>
            <ul className={styles.verdictList}>
              {DEMO_ROOMS.map((room) => (
                <li key={room.name}>
                  <span className={styles.swatch} style={{ background: room.color }} />
                  <strong>{roomName(room)}</strong>
                  <span className={styles.area}>{fmt(locale, room.areaM2, 1)} m²</span>
                  <span className={room.circle.conforme ? styles.pillOk : styles.pillBad}>{roomVerdict(room)}</span>
                </li>
              ))}
            </ul>
          </div>
          <dl className={styles.stats}>
            <div><dt>{t("stats.rooms")}</dt><dd><CountUp value={DEMO_ROOMS.length} reduced={reduced} /></dd></div>
            <div><dt>{t("stats.area")}</dt><dd><CountUp value={totalArea} decimals={1} reduced={reduced} /><small> m²</small></dd></div>
            <div><dt>{t("stats.required")}</dt><dd><small>Ø</small><CountUp value={TURNING_DIAMETER_M} decimals={2} reduced={reduced} /><small> m</small></dd></div>
            <div data-bad><dt>{t("stats.failing")}</dt><dd><CountUp value={failing} reduced={reduced} /></dd></div>
          </dl>
          <p className={styles.exampleNote}>{t("hero.example")}</p>
        </div>
      </section>

      <section id="fonctionnalites" className={`${styles.wrap} ${styles.featuresSection}`}>
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>{t("features.eyebrow")}</span>
          <h2>{t("features.title")}</h2>
          <p>{t("features.body")}</p>
        </div>
        <div className={styles.features}>
          {FEATURE_KEYS.map(([title, text], i) => (
            <article key={title} className={styles.feature}>
              <span className={styles.featureNum}>{String(i + 1).padStart(2, "0")}</span>
              <h3>{t(title)}</h3>
              <p>{t(text)}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="regles" className={`${styles.wrap} ${styles.featuresSection}`}>
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>{t("rules.eyebrow")}</span>
          <h2>{t("rules.title")}</h2>
          <p>{t("rules.body")}</p>
        </div>
        <h3 className={styles.rulesKicker}>{t("rules.checked")}</h3>
        <div className={styles.rules}>
          {RULES.map((rule) => (
            <article key={rule.id} className={styles.rule}>
              <span className={styles.ruleValue}>{rule.value}</span>
              <h3>{t(rule.name)}</h3>
              <p>{t(rule.text)}</p>
              <span className={styles.ruleSource} data-confirm={rule.id === "washbasin" || undefined}>{t(rule.source)}</span>
            </article>
          ))}
        </div>
        <p className={styles.rulesImpact}>{t("rules.impact", { rules: RULES.length })}</p>
        <h3 className={styles.rulesKicker}>{t("rules.next")}</h3>
        <ul className={styles.rulesNext}>
          {NEXT_RULES.map((key) => <li key={key}>{t(key)}</li>)}
        </ul>
      </section>

      <section className={styles.wrap}>
        <div className={styles.ctaBand}>
          <h2>{t("cta.title")}</h2>
          <p>{t("cta.body")}</p>
          <Link href="/check" className={styles.ctaLight}>{t("cta.button")}</Link>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.wrap}>
          <span className={styles.brand}><span className={styles.brandMark} aria-hidden />ConformScope</span>
          <p>{t("footer.line")}</p>
        </div>
      </footer>
    </main>
  );
}
