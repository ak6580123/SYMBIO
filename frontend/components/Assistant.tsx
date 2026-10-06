'use client';

import { useState } from 'react';

import { Notice, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import type { ChatResponse } from '@/lib/types';

const SUGGESTIONS = [
  'What can I do with this material?',
  'Why was this company recommended?',
  'Does this material require processing?',
  'Are there other sectors that could use it?',
  'What is the estimated impact?',
];

interface Message {
  role: 'user' | 'assistant';
  text: string;
  grounded?: string[];
  engine?: string;
}

export default function Assistant({ analysisId, matchId }: { analysisId: string; matchId?: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setQuestion('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setBusy(true);
    try {
      const res: ChatResponse = await api.chat(analysisId, trimmed, matchId);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: res.answer, grounded: res.grounded_in, engine: res.engine },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The assistant is unavailable');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-200">Assistant</h2>
        <span className="text-[10px] text-slate-600">grounded in this analysis only</span>
      </header>

      <div className="space-y-3 p-4">
        {messages.length === 0 && (
          <>
            <p className="text-xs leading-relaxed text-slate-500">
              Ask about this material or this match. The assistant answers only from the analysis record and the
              knowledge base — if the data is not there, it says so.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => void ask(suggestion)}
                  className="rounded-md border border-ink-600 bg-ink-900 px-2 py-1 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </>
        )}

        {messages.map((message, index) => (
          <div key={index} className={message.role === 'user' ? 'text-right' : ''}>
            <div
              className={`inline-block max-w-full whitespace-pre-wrap rounded-md px-3 py-2 text-left text-xs leading-relaxed ${
                message.role === 'user'
                  ? 'bg-ink-700 text-slate-100'
                  : 'border border-ink-700 bg-ink-900 text-slate-300'
              }`}
            >
              {message.text}
              {message.grounded && message.grounded.length > 0 && (
                <p className="mt-2 border-t border-ink-700 pt-1.5 font-mono text-[10px] text-slate-600">
                  from: {message.grounded.join(', ')}
                </p>
              )}
            </div>
          </div>
        ))}

        {busy && <Spinner label="Looking that up…" />}
        {error && <Notice tone="danger">{error}</Notice>}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
          className="flex gap-2 pt-1"
        >
          <input
            className="input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about this match…"
          />
          <button type="submit" className="btn-ghost shrink-0 text-xs" disabled={busy || !question.trim()}>
            Ask
          </button>
        </form>
      </div>
    </section>
  );
}
