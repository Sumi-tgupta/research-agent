import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces, Newsreader } from "next/font/google";
import { cn } from "@/lib/utils";
import { Providers } from "./providers";
import { HorizonBackground } from "@/components/horizon/horizon-background";
import { SiteHeader } from "@/components/layout/site-header";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
  axes: ["opsz", "SOFT", "WONK"],
});

const newsreader = Newsreader({
  subsets: ["latin"],
  variable: "--font-newsreader",
  display: "swap",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: {
    default: "Aurelia — Deep Research Studio",
    template: "%s · Aurelia",
  },
  description:
    "A multi-agent research studio that plans, searches the open web and academic literature, fact-checks its claims, and writes a cited report you can trust.",
  applicationName: "Aurelia",
  keywords: [
    "research assistant",
    "multi-agent",
    "academic search",
    "fact checking",
    "cited reports",
  ],
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e8f2ec" },
    { media: "(prefers-color-scheme: dark)", color: "#031a12" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        GeistSans.variable,
        GeistMono.variable,
        fraunces.variable,
        newsreader.variable
      )}
    >
      <body className="min-h-dvh">
        {/* First tab stop: lets keyboard users jump past the header. */}
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <Providers>
          {/* Fixed WebGL field behind everything. Renders a static
              gradient fallback until (and unless) Three.js mounts. */}
          <HorizonBackground />

          <div className="relative z-10 flex min-h-dvh flex-col">
            <SiteHeader />
            <main
              id="main-content"
              tabIndex={-1}
              className="flex-1 focus:outline-none"
            >
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
