'use client';

import { useEffect, useMemo, useState } from 'react';

import { DemoTag, Empty, Notice, Panel, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, REUSE_TYPE_LABEL, reuseTypeTone, SAFETY_LABEL, safetyTone, titleCase } from '@/lib/format';
import type { MaterialRecord, Recipient } from '@/lib/types';

type Tab = 'materials' | 'recipients';

export default function KnowledgeBasePage() {
  const [tab, setTab] = useState<Tab>('materials');
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [sectors, setSectors] = useState<{ sector: string; label: string }[]>([]);
  const [search, setSearch] = useState('');
  const [sector, setSector] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.materials(), api.recipients()])
      .then(([m, r]) => {
        setMaterials(m.materials);
        setRecipients(r.recipients);
        setSectors(r.sectors);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load the knowledge base'))
      .finally(() => setLoading(false));
  }, []);

  const filteredMaterials = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return materials.filter(
      (m) =>
        !needle ||
        m.name.toLowerCase().includes(needle) ||
        m.category.toLowerCase().includes(needle) ||
        m.reuse_categories.some((r) => r.toLowerCase().includes(needle)),
    );
  }, [materials, search]);

  const filteredRecipients = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return recipients.filter(
      (r) =>
        (!sector || r.sector === sector) &&
        (!needle ||
          r.company_name.toLowerCase().includes(needle) ||
          r.sector.toLowerCase().includes(needle) ||
          r.accepted_materials.some((m) => m.toLowerCase().includes(needle))),
    );
  }, [recipients, search, sector]);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">Knowledge Base</h1>
          <p className="mt-1 text-sm text-slate-500">
            The facts the matching engine is allowed to use. The language model can never add to this.
          </p>
        </div>
        <DemoTag />
      </header>

      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <div className="flex rounded-md border border-ink-600 p-0.5">
          {(['materials', 'recipients'] as Tab[]).map((value) => (
            <button
              key={value}
              onClick={() => {
                setTab(value);
                setSearch('');
                setSector('');
              }}
              className={`rounded px-3 py-1 text-xs ${
                tab === value ? 'bg-ink-700 text-slate-100' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {value === 'materials' ? `Materials (${materials.length})` : `Recipients (${recipients.length})`}
            </button>
          ))}
        </div>

        <input
          className="input w-auto min-w-[220px] flex-1"
          placeholder={tab === 'materials' ? 'Search materials, categories, routes…' : 'Search companies, sectors…'}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        {tab === 'recipients' && (
          <select className="input w-auto" value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {sectors.map((s) => (
              <option key={s.sector} value={s.sector}>
                {s.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <Notice tone="danger">{error}</Notice>}

      {loading ? (
        <div className="panel panel-pad">
          <Spinner label="Loading knowledge base…" />
        </div>
      ) : tab === 'materials' ? (
        filteredMaterials.length === 0 ? (
          <div className="panel">
            <Empty title="No materials match that search" />
          </div>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {filteredMaterials.map((material) => {
              const open = openId === material.id;
              return (
                <li key={material.id} className="panel p-4">
                  <button
                    className="flex w-full items-start justify-between gap-3 text-left"
                    onClick={() => setOpenId(open ? null : material.id)}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-100">{material.name}</p>
                      <p className="mt-0.5 text-[11px] text-slate-500">{titleCase(material.category)}</p>
                    </div>
                    <span className={`chip shrink-0 ${safetyTone(material.safety_level)}`}>
                      {SAFETY_LABEL[material.safety_level]}
                    </span>
                  </button>

                  <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{material.description}</p>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {material.reuse_categories.slice(0, open ? undefined : 3).map((route) => (
                      <span key={route} className="chip border-ink-600 bg-ink-800 text-slate-400">
                        {titleCase(route)}
                      </span>
                    ))}
                    {!open && material.reuse_categories.length > 3 && (
                      <span className="chip border-ink-600 bg-ink-800 text-slate-600">
                        +{material.reuse_categories.length - 3}
                      </span>
                    )}
                  </div>

                  {open && (
                    <div className="mt-3 space-y-3 border-t border-ink-700 pt-3">
                      <dl className="grid grid-cols-2 gap-2 text-[11px]">
                        <Cell label="Default reuse type" value={REUSE_TYPE_LABEL[material.default_reuse_type]} />
                        <Cell label="Requires processing" value={material.requires_processing ? 'Yes' : 'No'} />
                        <Cell label="Reference price" value={`${inr(material.typical_price_inr_per_tonne)}/t (demo)`} />
                        <Cell
                          label="CO₂e avoided"
                          value={`${material.co2e_avoided_t_per_tonne} t/t (demo)`}
                        />
                      </dl>
                      <div>
                        <p className="label mb-1.5">Compatible sectors</p>
                        <div className="flex flex-wrap gap-1.5">
                          {material.compatible_sectors.map((s) => (
                            <span key={s} className="chip border-ink-600 bg-ink-800 text-slate-400">
                              {titleCase(s)}
                            </span>
                          ))}
                        </div>
                      </div>
                      {material.notes && (
                        <p className="text-[11px] leading-relaxed text-amber-200/80">{material.notes}</p>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => setOpenId(open ? null : material.id)}
                    className="mt-3 text-[11px] text-slate-500 underline hover:text-slate-300"
                  >
                    {open ? 'Show less' : 'Show all properties'}
                  </button>
                </li>
              );
            })}
          </ul>
        )
      ) : filteredRecipients.length === 0 ? (
        <div className="panel">
          <Empty title="No recipients match those filters" />
        </div>
      ) : (
        <Panel title={`${filteredRecipients.length} recipients`} action={<span className="text-[11px] text-slate-500">fictional demo companies</span>}>
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead>
                <tr className="border-b border-ink-700 text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-2 font-medium">Company</th>
                  <th className="px-2 py-2 font-medium">Sector</th>
                  <th className="px-2 py-2 font-medium">Location</th>
                  <th className="px-2 py-2 text-right font-medium">Range (t/mo)</th>
                  <th className="px-2 py-2 text-right font-medium">Est. ₹/t</th>
                  <th className="px-2 py-2 font-medium">Reuse type</th>
                  <th className="px-4 py-2 font-medium">Accepts</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecipients.map((recipient) => (
                  <tr key={recipient.id} className="border-b border-ink-800 last:border-0 hover:bg-ink-800/40">
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-slate-200">{recipient.company_name}</p>
                      <p className="text-[10px] text-slate-600">{recipient.processing_capability.join(', ')}</p>
                    </td>
                    <td className="px-2 py-2.5 text-slate-400">{titleCase(recipient.sector)}</td>
                    <td className="px-2 py-2.5 text-slate-500">{recipient.location}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-slate-300">
                      {recipient.min_quantity_t_per_month}–{recipient.max_quantity_t_per_month}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-slate-300">
                      {inr(recipient.estimated_price_inr_per_tonne)}
                    </td>
                    <td className="px-2 py-2.5">
                      <span className={`chip ${reuseTypeTone(recipient.reuse_type)}`}>
                        {REUSE_TYPE_LABEL[recipient.reuse_type]}
                      </span>
                    </td>
                    <td className="max-w-[220px] px-4 py-2.5">
                      <p className="truncate text-[10px] text-slate-500" title={recipient.accepted_materials.join(', ')}>
                        {recipient.accepted_materials.map((m) => titleCase(m)).join(', ')}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-600">{label}</dt>
      <dd className="text-slate-300">{value}</dd>
    </div>
  );
}
