import type { Metadata } from 'next';

import Nav from '@/components/Nav';
import { SessionProvider } from '@/lib/session';

import './globals.css';

export const metadata: Metadata = {
  title: 'Symbio — Industrial Symbiosis Intelligence',
  description:
    'Symbio identifies what a material stream actually is, finds who can use it, and ranks the reuse opportunities with an explainable score.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-canvas text-text">
        {/* One session check per load, read from context by every screen that cares. */}
        <SessionProvider>
          <Nav />
          <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>
        </SessionProvider>
        <footer className="mx-auto max-w-7xl border-t border-line px-4 pb-10 pt-5 text-[11px] leading-relaxed text-text-faint sm:px-6">
          Companies, prices and emission factors in this build are recorded reference values, not live commercial
          records; figures derived from them are estimates. Match scores are computed by a deterministic engine over a
          material knowledge base — the language model identifies the material and never scores a match.
        </footer>
      </body>
    </html>
  );
}
