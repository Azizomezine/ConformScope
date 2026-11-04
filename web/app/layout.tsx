import type { Metadata, Viewport } from "next";
import { Archivo_Narrow, Geist, Geist_Mono, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { PreferencesProvider } from "./preferences";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/* The check screen's faces (from pmr-checker): ISO 3098 — the narrow, spaced lettering
   on an architect's drawing — and monospaced dimensions, since every number on a plan
   is one. */
const letters = Archivo_Narrow({
  subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-letters",
});
const body = IBM_Plex_Sans({
  subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-body",
});
const dim = IBM_Plex_Mono({
  subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-dim",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f7fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1621" },
  ],
};

export const metadata: Metadata = {
  title: "ConformScope",
  description: "Can a wheelchair live in this home?",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning
          className={`${geistSans.variable} ${geistMono.variable} ${letters.variable} ${body.variable} ${dim.variable}`}>
      <body>
        {/* Stamp the stored language/theme on <html> before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('conforms-theme');if(t==='dark'){document.documentElement.dataset.theme='dark';document.documentElement.classList.add('dark')}var l=localStorage.getItem('conforms-locale');if(l==='fr'){document.documentElement.lang='fr';document.documentElement.dataset.locale='fr'}}catch(e){}" }} />
        <PreferencesProvider>{children}</PreferencesProvider>
      </body>
    </html>
  );
}
