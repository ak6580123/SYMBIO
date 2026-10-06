'use client';

import { useCallback, useRef, useState } from 'react';

import { api } from '@/lib/api';
import type { UploadResponse } from '@/lib/types';

const ACCEPTED = '.pdf,.txt,.docx';

export default function FileDrop({
  onExtracted,
}: {
  onExtracted: (result: UploadResponse | null) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = useCallback(
    async (file: File) => {
      setBusy(true);
      try {
        const res = await api.upload(file);
        setResult(res);
        onExtracted(res.ok ? res : null);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        const failed: UploadResponse = {
          filename: file.name,
          extracted_text: '',
          char_count: 0,
          ok: false,
          message: `${message} Please type the description instead.`,
        };
        setResult(failed);
        onExtracted(null);
      } finally {
        setBusy(false);
      }
    },
    [onExtracted],
  );

  const clear = () => {
    setResult(null);
    onExtracted(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handle(file);
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-md border border-dashed px-4 py-5 text-center transition-colors ${
          dragging ? 'border-accent bg-accent/5' : 'border-ink-600 bg-ink-900 hover:border-ink-500'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handle(file);
          }}
        />
        {busy ? (
          <p className="text-xs text-slate-400">Reading file…</p>
        ) : (
          <>
            <p className="text-xs font-medium text-slate-300">Drop a waste or material report</p>
            <p className="mt-1 text-[11px] text-slate-600">PDF, TXT or DOCX · optional · text is sent to the classifier</p>
          </>
        )}
      </div>

      {result && (
        <div
          className={`mt-2 rounded-md border px-3 py-2 text-[11px] leading-relaxed ${
            result.ok
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <span>
              <span className="font-medium">{result.filename}</span> — {result.message}
            </span>
            <button onClick={clear} className="shrink-0 text-slate-400 underline hover:text-slate-200">
              remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
