"use client";

import { Moon, Sun } from "lucide-react";
import { createContext, useCallback, useContext, useSyncExternalStore } from "react";
import { translate, type I18nKey, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

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
  const seg = (active: boolean) =>
    cn(
      "px-2 py-1 text-xs font-semibold transition-[color,background-color,transform] duration-150 active:scale-[0.96]",
      active ? "bg-[var(--navy,#1d3557)] text-white shadow-sm" : "text-current opacity-60 hover:opacity-100",
    );
  return (
    <div className={cn("flex flex-none items-center gap-2", className)}>
      <div role="group" aria-label={t("pref.language")}
           className="flex items-center overflow-hidden rounded-full border border-current/25 bg-white/40 backdrop-blur-sm dark:bg-white/10">
        <button type="button" aria-pressed={locale === "en"} title={t("pref.toEnglish")}
                onClick={() => setLocale("en")} className={seg(locale === "en")}>EN</button>
        <button type="button" aria-pressed={locale === "fr"} title={t("pref.toFrench")}
                onClick={() => setLocale("fr")} className={seg(locale === "fr")}>FR</button>
      </div>
      <button type="button"
              aria-pressed={theme === "dark"}
              aria-label={theme === "dark" ? t("pref.toLight") : t("pref.toDark")}
              title={theme === "dark" ? t("pref.toLight") : t("pref.toDark")}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="grid size-8 place-items-center rounded-full border border-current/25 bg-white/40 backdrop-blur-sm transition-[background-color,transform] duration-150 hover:bg-white/60 active:scale-[0.94] dark:bg-white/10 [&_svg]:size-4">
        {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
      </button>
    </div>
  );
}
