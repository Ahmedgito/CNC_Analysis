import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Navbar } from "@/components/site/navbar";
import { THEME_SCRIPT } from "@/lib/theme";
import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "CNC Part Analyzer", template: "%s · CNC Part Analyzer" },
  description:
    "Evidence-grounded answers about CNC parts from their manufacturing records and drawings. Every answer cites the exact spreadsheet cell or drawing callout it used.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script adds the `dark` class before hydration, hence the suppression.
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        {/* Static, first-party script: sets the theme class before first paint (no flash). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-dvh flex-col bg-zinc-50 font-sans text-zinc-900 antialiased selection:bg-cyan-500/25 dark:bg-zinc-950 dark:text-zinc-100">
        <a
          href="#content"
          className="sr-only z-50 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3 dark:bg-white dark:text-zinc-900"
        >
          Skip to content
        </a>
        <Providers>
          <Navbar />
          <main id="content" className="flex w-full flex-1 flex-col">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
