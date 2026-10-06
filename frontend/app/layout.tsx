import type { Metadata } from 'next';

import Nav from '@/components/Nav';

import './globals.css';

export const metadata: Metadata = {
  title: 'Symbio — Waste Reuse Matchmaking',
  description:
    'Symbio identifies what a waste stream actually is, finds who could use it, and ranks the reuse opportunities with an explainable score.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ink-950 text-slate-200">
        <Nav />
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 pt-2 text-[11px] leading-relaxed text-slate-600">
          Symbio MVP · demonstration build. All companies, prices and emission factors are seeded demo data and are
          labelled as estimates. Match scores are produced by a deterministic engine over a material knowledge base —
          the language model only identifies the material.
        </footer>
      </body>
    </html>
  );
}
