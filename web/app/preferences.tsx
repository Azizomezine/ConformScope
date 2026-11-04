"use client";

import { Moon, Sun } from "lucide-react";
import { createContext, useCallback, useContext, useSyncExternalStore } from "react";
import { translate, type I18nKey, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import styles from "./preferences.module.css";

export type Theme = "light" | "dark";
export type { Locale };

const LOCALE_KEY = "conforms-locale";
const THEME_KEY = "conforms-theme";

type Prefs = {
  locale: Locale;
  theme: Theme;
  setLocale: (l: Locale) => void;
  setTheme: (t: Theme) => void;
  t: (key: I18nKey, vars?: Record<string, string | number>) => string;
};

const Ctx = createContext<Prefs | null>(null);

function applyToDocument(locale: Locale, theme: Theme) {
  const el = document.documentElement;
  el.lang = locale;
  el.dataset.theme = theme;
  el.dataset.locale = locale;
  el.classList.toggle("dark", theme === "dark");
  el.style.colorScheme = theme;
}

/**
 * Language (English by default, Français as the alternative) and night mode,
 * remembered across visits. The inline script in the root layout stamps the
 * stored choice on <html> before first paint; this provider adopts it on
 * mount, so there is no flash of the wrong theme.
 */
type PrefsState = { locale: Locale; theme: Theme };
const SERVER_STATE: PrefsState = { locale: "en", theme: "light" };
let cache: { key: string; state: PrefsState } | null = null;

function getSnapshot(): PrefsState {
  const l: Locale = window.localStorage.getItem(LOCALE_KEY) === "fr"
    || document.documentElement.dataset.locale === "fr" ? "fr" : "en";
  const t: Theme = window.localStorage.getItem(THEME_KEY) === "dark"
    || document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const key = `${l}/${t}`;
  if (!cache || cache.key !== key) cache = { key, state: { locale: l, theme: t } };
  return cache.state;
}

function subscribe(onChange: () => void) {
  window.addEventListener("conforms-prefs", onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener("conforms-prefs", onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const { locale, theme } = useSyncExternalStore(subscribe, getSnapshot, () => SERVER_STATE);

  const setLocale = useCallback((l: Locale) => {
    window.localStorage.setItem(LOCALE_KEY, l);
    applyToDocument(l, document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    window.dispatchEvent(new Event("conforms-prefs"));
  }, []);

  const setTheme = useCallback((t: Theme) => {
    window.localStorage.setItem(THEME_KEY, t);
    applyToDocument(document.documentElement.lang === "fr" ? "fr" : "en", t);
    window.dispatchEvent(new Event("conforms-prefs"));
  }, []);

  const t = useCallback(
    (key: I18nKey, vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );

  return <Ctx.Provider value={{ locale, theme, setLocale, setTheme, t }}>{children}</Ctx.Provider>;
}

export function usePreferences(): Prefs {
  const ctx = useContext(Ctx);
  if (ctx) return ctx;
  // Outside the provider (should not happen): English, day, inert setters.
  return {
    locale: "en",
    theme: "light",
    setLocale: () => {},
    setTheme: () => {},
    t: (key, vars) => translate("en", key, vars),
  };
}

/** EN | FR segmented control plus a day/night toggle, for either page's header. */
export function PreferenceControls({ className }: { className?: string }) {
  const { locale, theme, setLocale, setTheme, t } = usePreferences();
  const dark = theme === "dark";
  return (
    <div className={cn(styles.controls, className)}>
      <div role="group" aria-label={t("pref.language")} className={styles.segmented}>
        <button type="button" lang="en" aria-pressed={locale === "en"} title={t("pref.toEnglish")}
                onClick={() => setLocale("en")} className={styles.seg}>EN</button>
        <button type="button" lang="fr" aria-pressed={locale === "fr"} title={t("pref.toFrench")}
                onClick={() => setLocale("fr")} className={styles.seg}>FR</button>
      </div>
      <button type="button"
              aria-pressed={dark}
              aria-label={t("pref.dark")}
              title={dark ? t("pref.toLight") : t("pref.toDark")}
              onClick={() => setTheme(dark ? "light" : "dark")}
              className={styles.toggle}>
        {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
      </button>
    </div>
  );
}
