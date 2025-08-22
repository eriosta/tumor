// src/App.tsx
import React, { useMemo, useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  BarChart, Bar, Legend
} from 'recharts';
import type { DotProps } from 'recharts';

// ⬇️ add grid CSS (required for dragging/resizing handles)
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { Responsive, WidthProvider, type Layouts, type Layout } from 'react-grid-layout';

const ResponsiveGridLayout = WidthProvider(Responsive);

/** ---------- Types (supports per-lesion details) ---------- */

type Lesion = {
  lesion_id: string;
  kind: 'primary'|'ln'|'met';
  organ: string;
  location?: string;
  station?: string;
  rule: 'longest'|'short_axis';
  baseline_mm?: number | null;
  follow_mm?: number | null;
  size_mm_current?: number | null;
  margin?: string;
  enhancement?: string;
  necrosis?: boolean;
  suspicious?: boolean;
  target?: boolean;
};

type RecistMeta = {
  patient_id: string;
  timepoint: number;
  study_date: string; // YYYY-MM-DD
  recist: {
    baseline_sld_mm: number | null;
    current_sld_mm: number | null;
    nadir_sld_mm: number | null;
    overall_response: string;
  };
  lesions?: Lesion[];
};

type PatientSeries = {
  patientId: string;
  rows: Array<RecistMeta & {
    sld_mm: number;
    pct_from_baseline: number | null;
    pct_from_nadir: number | null;
  }>;
};

type LesionRow = {
  lesion: {
    id: string;
    label: string;
    organ: string;
    rule: 'longest'|'short_axis';
    target: boolean;
  };
  sizesByDate: Record<string, number | null>;
  sldByDate: Record<string, number | null>;
};

/** ---------- Helpers ---------- */

function parseJsonSafe<T>(text: string): T | null {
  try { return JSON.parse(text) as T; } catch { return null; }
}

async function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(r.error);
    r.onload = () => resolve(String(r.result || ''));
    r.readAsText(file);
  });
}

function groupByPatient(rows: RecistMeta[]): PatientSeries[] {
  const map = new Map<string, RecistMeta[]>();
  rows.forEach(r => {
    const key = r.patient_id;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  });
  const series: PatientSeries[] = [];
  for (const [patientId, arr] of map.entries()) {
    arr.sort((a,b) => a.study_date.localeCompare(b.study_date));
    const baseline = arr.find(r => r.timepoint === 0) || arr[0];
    const baselineSLD = baseline?.recist.baseline_sld_mm ?? null;
    let nadir = baselineSLD ?? null;
    const rows2 = arr.map(r => {
      const sld = r.timepoint === 0
        ? (r.recist.baseline_sld_mm ?? 0)
        : (r.recist.current_sld_mm ?? r.recist.baseline_sld_mm ?? 0);
      if (nadir === null) nadir = sld; else nadir = Math.min(nadir, sld);
      const pctFromBaseline = baselineSLD ? ((sld - baselineSLD) / baselineSLD) * 100 : null;
      const pctFromNadir = (nadir && nadir > 0) ? ((sld - nadir) / nadir) * 100 : null;
      return { ...r, sld_mm: sld, pct_from_baseline: pctFromBaseline, pct_from_nadir: pctFromNadir };
    });
    series.push({ patientId, rows: rows2 });
  }
  series.sort((a,b) => a.patientId.localeCompare(b.patientId));
  return series;
}

function formatPct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const s = x >= 0 ? `+${x.toFixed(1)}` : x.toFixed(1);
  return `${s}%`;
}

function responseChip(resp?: string) {
  const base = 'px-2 py-0.5 rounded-full text-xs font-medium';
  switch (resp) {
    case 'CR': return <span className={`${base} bg-emerald-900/60 text-emerald-200 ring-1 ring-emerald-700/50`}>CR</span>;
    case 'PR': return <span className={`${base} bg-sky-900/60 text-sky-200 ring-1 ring-sky-700/50`}>PR</span>;
    case 'SD': return <span className={`${base} bg-zinc-800 text-zinc-200 ring-1 ring-zinc-700/60`}>SD</span>;
    case 'PD': return <span className={`${base} bg-rose-900/60 text-rose-200 ring-1 ring-rose-700/50`}>PD</span>;
    default: return <span className={`${base} bg-zinc-900/60 text-zinc-300 ring-1 ring-zinc-700/50`}>{resp || '—'}</span>;
  }
}

function downloadCSV(filename: string, rows: Array<Record<string, any>>) {
  const headers = Object.keys(rows[0] || {});
  const csv = [headers.join(',')]
    .concat(rows.map(r => headers.map(h => JSON.stringify(r[h] ?? '')).join(',')))
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function colorForIndex(i: number): string {
  const hue = (i * 47) % 360;
  return `hsl(${hue} 70% 60%)`;
}

function buildLesionMatrix(selected?: PatientSeries): { dates: string[], rows: LesionRow[] } {
  if (!selected) return { dates: [], rows: [] };

  const dates = selected.rows.map(r => r.study_date);
  const lesionIds: string[] = [];
  const rowsMap = new Map<string, LesionRow>();

  selected.rows.forEach((tp, tpIdx) => {
    const date = tp.study_date;
    const lesions = (tp as any).lesions ?? [];
    lesions.forEach((lsn: Lesion) => {
      const id = lsn.lesion_id || `${lsn.kind}:${lsn.organ}:${lsn.station || lsn.location || ''}`;
      if (!rowsMap.has(id)) {
        lesionIds.push(id);
        const label = `L${lesionIds.length}`;
        rowsMap.set(id, {
          lesion: {
            id, label,
            organ: lsn.organ,
            rule: lsn.rule,
            target: !!lsn.target
          },
          sizesByDate: {},
          sldByDate: {}
        });
      }
      const row = rowsMap.get(id)!;
      row.sizesByDate[date] = (lsn.size_mm_current ?? null);
      if (lsn.target) {
        row.sldByDate[date] = (tpIdx === 0) ? (lsn.baseline_mm ?? null) : (lsn.follow_mm ?? null);
      } else {
        row.sldByDate[date] = null;
      }
    });
  });

  const rows = Array.from(rowsMap.values())
    .sort((a,b) => Number(b.lesion.target) - Number(a.lesion.target) || a.lesion.organ.localeCompare(b.lesion.organ));

  return { dates, rows };
}

/** ---------- Grid layout helpers ---------- */

const LAYOUT_KEY = 'recist-rgl-layout-v1';

const defaultLayouts: Layouts = {
  lg: [
    // i: item key, x/y: position, w/h: width/height (grid units)
    { i: 'upload',      x: 0,  y: 0,  w: 6, h: 8 },
    { i: 'controls',    x: 6,  y: 0,  w: 6, h: 6 },
    { i: 'sldLine',     x: 0,  y: 8,  w: 12, h: 16 },
    { i: 'sldStack',    x: 0,  y: 24, w: 12, h: 14 },
    { i: 'tpTable',     x: 0,  y: 38, w: 12, h: 16 },
    { i: 'lesionMatrix',x: 0,  y: 54, w: 12, h: 20 },
  ],
  md: [
    { i: 'upload',      x: 0,  y: 0,  w: 6, h: 8 },
    { i: 'controls',    x: 6,  y: 0,  w: 6, h: 6 },
    { i: 'sldLine',     x: 0,  y: 8,  w: 12, h: 16 },
    { i: 'sldStack',    x: 0,  y: 24, w: 12, h: 14 },
    { i: 'tpTable',     x: 0,  y: 38, w: 12, h: 16 },
    { i: 'lesionMatrix',x: 0,  y: 54, w: 12, h: 20 },
  ],
  sm: [
    { i: 'upload',      x: 0,  y: 0,  w: 1, h: 8 },
    { i: 'controls',    x: 0,  y: 8,  w: 1, h: 6 },
    { i: 'sldLine',     x: 0,  y: 14, w: 1, h: 16 },
    { i: 'sldStack',    x: 0,  y: 30, w: 1, h: 14 },
    { i: 'tpTable',     x: 0,  y: 44, w: 1, h: 16 },
    { i: 'lesionMatrix',x: 0,  y: 60, w: 1, h: 20 },
  ],
};

function loadLayouts(): Layouts {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return defaultLayouts;
    const parsed = JSON.parse(raw);
    return parsed;
  } catch {
    return defaultLayouts;
  }
}

function saveLayouts(ls: Layouts) {
  localStorage.setItem(LAYOUT_KEY, JSON.stringify(ls));
}

function Panel({
  title,
  children,
  actions,
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="h-full rounded-2xl border border-zinc-800 bg-zinc-900/40 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800">
        <div className="drag-handle cursor-move text-zinc-400 select-none">≡</div>
        <h2 className="text-sm font-medium text-zinc-200">{title}</h2>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      <div className="p-4 flex-1 min-h-0">{children}</div>
    </div>
  );
}

/** ---------- Component ---------- */

export default function App() {
  const [series, setSeries] = useState<PatientSeries[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<'sld'|'pct'>('sld');
  const [filter, setFilter] = useState<string>('ALL');
  const [layouts, setLayouts] = useState<Layouts>(loadLayouts());

  useEffect(() => { saveLayouts(layouts); }, [layouts]);

  const selected = useMemo(
    () => series.find(s => s.patientId === (selectedId ?? series[0]?.patientId)),
    [series, selectedId]
  );

  const chartData = useMemo(() => {
    if (!selected) return [] as any[];
    const rows = selected.rows.filter(r => filter === 'ALL' ? true : r.recist.overall_response === filter);
    return rows.map(r => ({
      date: r.study_date,
      sld: r.sld_mm,
      pct: r.pct_from_baseline,
      resp: r.recist.overall_response,
    }));
  }, [selected, filter]);

  const { dates, rows: lesionRows } = useMemo(() => buildLesionMatrix(selected), [selected]);

  const sldStackData = useMemo(() => {
    if (!selected) return [] as any[];
    return dates.map(d => {
      const entry: Record<string, any> = { date: d };
      lesionRows.forEach((lr) => {
        const v = lr.sldByDate[d];
        if (v != null) entry[lr.lesion.label] = v;
      });
      return entry;
    });
  }, [dates, lesionRows, selected]);

  async function handleCohortJsonl(file: File | null) {
    if (!file) return;
    const text = await readFileText(file);
    const rows: RecistMeta[] = [];
    for (const line of text.split(/\r?\n/)) {
      if (!line.trim()) continue;
      const obj = parseJsonSafe<any>(line);
      if (!obj) continue;

      const lesions: Lesion[] | undefined =
        obj.lesions ??
        obj.extras?.lesions ??
        undefined;

      rows.push({
        patient_id: obj.patient_id,
        timepoint: obj.timepoint ?? 0,
        study_date: obj.study_date,
        recist: {
          baseline_sld_mm: obj.baseline_sld_mm ?? obj.recist?.baseline_sld_mm ?? null,
          current_sld_mm: obj.current_sld_mm ?? obj.recist?.current_sld_mm ?? null,
          nadir_sld_mm: obj.nadir_sld_mm ?? obj.recist?.nadir_sld_mm ?? null,
          overall_response: obj.overall_response ?? obj.recist?.overall_response ?? '—',
        },
        lesions,
      });
    }
    const grouped = groupByPatient(rows);
    setSeries(grouped);
    setSelectedId(grouped[0]?.patientId ?? null);
  }

  function exportCurrentAsCSV() {
    if (!selected) return;
    const rows = selected.rows.map(r => ({
      patient_id: r.patient_id,
      study_date: r.study_date,
      timepoint: r.timepoint,
      sld_mm: r.sld_mm,
      pct_from_baseline: r.pct_from_baseline?.toFixed(1) ?? '',
      pct_from_nadir: r.pct_from_nadir?.toFixed(1) ?? '',
      overall_response: r.recist.overall_response,
      baseline_sld_mm: r.recist.baseline_sld_mm ?? '',
      nadir_sld_mm: r.recist.nadir_sld_mm ?? '',
    }));
    downloadCSV(`${selected.patientId}_timeline.csv`, rows);
  }

  const dotRenderer = (props: DotProps) => {
    const resp = (props as any).payload?.resp as string | undefined;
    const fill = resp === 'PD' ? '#f43f5e' : resp === 'PR' ? '#38bdf8' : resp === 'CR' ? '#34d399' : '#a1a1aa';
    return <circle cx={props.cx} cy={props.cy} r={4} fill={fill} opacity={0.95} />;
  };

  const cols = { lg: 12, md: 12, sm: 1, xs: 1, xxs: 1 };
  const breakpoints = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200">
      <div className="mx-auto max-w-7xl px-4 py-6">
        <header className="mb-4 flex items-center justify-between">
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Onc RECIST Dashboard</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setLayouts(defaultLayouts)}
              className="rounded-xl px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"
              title="Reset panel layout"
            >
              Reset layout
            </button>
            <button
              onClick={exportCurrentAsCSV}
              className="rounded-xl px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"
            >
              Export CSV
            </button>
          </div>
        </header>

        <ResponsiveGridLayout
          className="layout"
          layouts={layouts}
          breakpoints={breakpoints}
          cols={cols}
          rowHeight={8}                 // 8px per grid row; panels set their own heights via h
          margin={[12, 12]}             // gap between panels
          containerPadding={[0, 0]}
          draggableHandle=".drag-handle" // only the header grip is draggable
          onLayoutsChange={(ls) => setLayouts(ls)}
          
          isBounded
          compactType="vertical"
        >
          {/* Upload JSONL */}
          <div key="upload">
            <Panel title="Load cohort_labels.jsonl">
              <input
                onChange={e => handleCohortJsonl(e.target.files?.[0] ?? null)}
                type="file"
                accept=".jsonl,.txt,application/jsonl,text/plain"
                className="block w-full text-sm file:mr-4 file:rounded-xl file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-zinc-200 hover:file:bg-zinc-700"
              />
              <p className="mt-2 text-xs text-zinc-400">
                Each line should include <code>patient_id</code>, <code>study_date</code>, <code>timepoint</code>, RECIST fields, and optionally <code>lesions</code> (or <code>extras.lesions</code>).
              </p>
            </Panel>
          </div>

          {/* Controls */}
          <div key="controls">
            <Panel title="Controls">
              <div className="flex flex-col md:flex-row gap-3 md:items-end">
                <div className="flex-1">
                  <label className="block text-xs text-zinc-400 mb-1">Patient</label>
                  <select value={selectedId ?? ''} onChange={e => setSelectedId(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 text-sm">
                    {series.map(s => (<option key={s.patientId} value={s.patientId}>{s.patientId}</option>))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Y-axis</label>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setMode('sld')} className={`px-3 py-1.5 rounded-xl text-sm ${mode==='sld' ? 'bg-zinc-800' : 'bg-zinc-900 border border-zinc-700'}`}>SLD (mm)</button>
                    <button onClick={() => setMode('pct')} className={`px-3 py-1.5 rounded-xl text-sm ${mode==='pct' ? 'bg-zinc-800' : 'bg-zinc-900 border border-zinc-700'}`}>Δ from baseline (%)</button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Filter by response</label>
                  <div className="flex gap-2 text-sm">
                    {(['ALL','CR','PR','SD','PD'] as const).map(k => (
                      <button key={k} onClick={() => setFilter(k)} className={`px-3 py-1.5 rounded-xl ${filter===k ? 'bg-zinc-800' : 'bg-zinc-900 border border-zinc-700'}`}>{k}</button>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>
          </div>

          {/* Overall SLD line */}
          <div key="sldLine">
            <Panel title={`Overall SLD ${selected ? `• ${selected.patientId}` : ''}`}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
                    <XAxis dataKey="date" tick={{ fill: '#a1a1aa' }} tickLine={false} axisLine={{ stroke: '#27272a' }} />
                    <YAxis tick={{ fill: '#a1a1aa' }} tickLine={false} axisLine={{ stroke: '#27272a' }} domain={['auto','auto']} />
                    <Tooltip
                      contentStyle={{
                        background: '#09090b',
                        border: '1px solid #27272a',
                        borderRadius: 12,
                        color: '#e4e4e7',
                      }}
                      formatter={(v:any, n:any) =>
                        n === 'pct' ? [formatPct(v), 'Δ from baseline'] : [v, 'SLD (mm)']
                      }
                    />
                    {mode === 'sld'
                      ? <Line type="monotone" dataKey="sld" stroke="#e4e4e7" strokeWidth={2} dot={dotRenderer} />
                      : <Line type="monotone" dataKey="pct" stroke="#e4e4e7" strokeWidth={2} dot={dotRenderer} />
                    }
                    {selected && selected.rows.length > 0 && (
                      <ReferenceLine y={selected.rows[0].sld_mm} stroke="#52525b" strokeDasharray="3 3" />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>

          {/* SLD composition (stacked by target lesion) */}
          <div key="sldStack">
            <Panel title="SLD composition (targets)">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sldStackData} margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
                    <XAxis dataKey="date" tick={{ fill: '#a1a1aa' }} tickLine={false} axisLine={{ stroke: '#27272a' }} />
                    <YAxis tick={{ fill: '#a1a1aa' }} tickLine={false} axisLine={{ stroke: '#27272a' }} />
                    <Tooltip contentStyle={{ background: '#09090b', border: '1px solid #27272a', borderRadius: 12, color: '#e4e4e7' }} />
                    {lesionRows.filter(r => r.lesion.target).map((r, idx) => (
                      <Bar key={r.lesion.id} dataKey={r.lesion.label} stackId="sld" fill={colorForIndex(idx)} />
                    ))}
                    <Legend wrapperStyle={{ color: '#a1a1aa' }} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {lesionRows.length > 0 && (
                <div className="mt-3 text-xs text-zinc-400 flex flex-wrap gap-3">
                  {lesionRows.filter(r => r.lesion.target).map((r, idx) => (
                    <div key={r.lesion.id} className="flex items-center gap-2">
                      <span className="inline-block w-3 h-3 rounded-sm" style={{ background: colorForIndex(idx) }} />
                      <span className="text-zinc-300">{r.lesion.label}</span>
                      <span>• {r.lesion.organ} ({r.lesion.rule === 'short_axis' ? 'LN SA' : 'LD'})</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          {/* Per timepoint summary table */}
          <div key="tpTable">
            <Panel title="Per-timepoint summary">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-zinc-400">
                      <th className="py-2 text-left font-medium">Date</th>
                      <th className="py-2 text-left font-medium">TP</th>
                      <th className="py-2 text-left font-medium">SLD (mm)</th>
                      <th className="py-2 text-left font-medium">Δ from baseline</th>
                      <th className="py-2 text-left font-medium">Δ from nadir</th>
                      <th className="py-2 text-left font-medium">Overall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected?.rows.map((r, idx) => (
                      <tr key={idx} className="border-t border-zinc-800">
                        <td className="py-2">{r.study_date}</td>
                        <td className="py-2">{r.timepoint}</td>
                        <td className="py-2">{r.sld_mm}</td>
                        <td className="py-2">{formatPct(r.pct_from_baseline)}</td>
                        <td className="py-2">{formatPct(r.pct_from_nadir)}</td>
                        <td className="py-2">{responseChip(r.recist.overall_response)}</td>
                      </tr>
                    ))}
                    {!selected && (
                      <tr><td className="py-6 text-zinc-500" colSpan={6}>Upload <code>cohort_labels.jsonl</code> to begin.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          {/* Lesion Matrix */}
          <div key="lesionMatrix">
            <Panel title="Lesion matrix (sizes in mm)">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-zinc-400">
                      <th className="py-2 text-left font-medium">Lesion</th>
                      <th className="py-2 text-left font-medium">Organ</th>
                      <th className="py-2 text-left font-medium">Measure</th>
                      <th className="py-2 text-left font-medium">Target</th>
                      {dates.map(d => (
                        <th key={d} className="py-2 text-left font-medium">{d}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {lesionRows.map((r, idx) => (
                      <tr key={r.lesion.id} className="border-t border-zinc-800">
                        <td className="py-2">
                          <span className="inline-flex items-center gap-2">
                            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: colorForIndex(idx) }} />
                            <span className="text-zinc-100">{r.lesion.label}</span>
                          </span>
                        </td>
                        <td className="py-2">{r.lesion.organ}</td>
                        <td className="py-2">{r.lesion.rule === 'short_axis' ? 'LN short-axis' : 'Longest diameter'}</td>
                        <td className="py-2">
                          {r.lesion.target
                            ? <span className="px-2 py-0.5 rounded-full text-xs bg-sky-900/60 text-sky-200 ring-1 ring-sky-700/50">Target</span>
                            : <span className="px-2 py-0.5 rounded-full text-xs bg-zinc-800 text-zinc-300 ring-1 ring-zinc-700/60">Non-target</span>}
                        </td>
                        {dates.map(d => {
                          const v = r.sizesByDate[d];
                          const isTargetContribution = r.lesion.target && (r.sldByDate[d] != null);
                          return (
                            <td key={d} className={`py-2 ${isTargetContribution ? 'font-semibold text-zinc-100' : 'text-zinc-300'}`}>
                              {v == null ? '—' : v}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    {lesionRows.length === 0 && (
                      <tr><td className="py-6 text-zinc-500" colSpan={4 + dates.length}>No lesion-level data in the JSONL.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </ResponsiveGridLayout>

        <footer className="mt-6 text-xs text-zinc-500">Prototype • Drag panels by the ≡ handle • Resize from corner</footer>
      </div>
    </div>
  );
}
