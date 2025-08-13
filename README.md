Here’s an updated README with a clean **App (dashboard) development** section added. Replace your README with this (or copy the new section in).

---

# tumor — CT CAP TNM Extraction (Consolidated)

End-to-end pipeline for **synthetic → preprocess → train (LoRA) → eval → DB load → RAG** using the `tumor` package.
Reports follow radiology conventions with **FINDINGS by organ** and a clear **IMPRESSION**.

## Quickstart

```bash
# 0) Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Generate synthetic CT CAP reports
python -m tumor.synth.gen_cap --out_dir data/synth --n 500 --seed 42 --style structured --include_negatives --timepoints 2

# 2) Preprocess into JSONL splits
python -m tumor.preprocess.run --in_dir data/synth/reports --out_dir data/processed --schema configs/tnm_schema.json

# 3) (Optional) seed labels
python -m tumor.preprocess.bootstrap_labels --in_dir data/processed --out_path data/labels/seed_labels.jsonl

# 4) Train (LoRA)
python -m tumor.training.train --train data/processed/train.jsonl --val data/processed/val.jsonl --config configs/train_lora.yaml

# 5) Evaluate
python -m tumor.eval.run --preds models/latest/preds.jsonl --gold data/processed/test.jsonl --config configs/metrics.yaml

# 6) (Optional) Postgres + load predictions
docker compose up -d
python -m tumor.db.load --in_file models/latest/preds.jsonl --dsn postgresql://onc:onc@localhost:5432/onc

# 7) (Optional) RAG server
python -m tumor.rag.server --port 8080
```

---

## Longitudinal cohort + notes (for RECIST + oncology timelines)

Generate multi-timepoint patients (subfolders per patient/date) with RECIST tracking:

```bash
# baseline + follow-ups with nadir-based PD logic
python -m tumor.synth.gen_cohort \
  --out_dir data/synth_patients \
  --n_patients 50 \
  --min_tp 3 --max_tp 6 \
  --seed 42 \
  --style structured \
  --include_negatives

# restrict primaries (examples)
# lung only
python -m tumor.synth.gen_cohort --out_dir data/synth_patients --n_patients 25 --min_tp 3 --max_tp 6 --seed 42 --style structured --include_negatives --primary_mix lung
# GI (colon+stomach+pancreas+liver)
python -m tumor.synth.gen_cohort --out_dir data/synth_patients --n_patients 25 --min_tp 3 --max_tp 6 --seed 42 --style structured --include_negatives --primary_mix colon stomach pancreas liver
```

Generate synthetic **oncology progress notes** aligned to imaging (regimens, CxDy dates, line of therapy):

```bash
python -m tumor.synth.gen_onc_notes \
  --patients_root data/synth_patients/patients \
  --out_dir data/synth_patients \
  --seed 42 \
  --notes_per_tp 1
```

Outputs:

```
data/synth_patients/
  cohort_labels.jsonl
  patients/
    PID000000/
      2023-03-15/ report.txt, meta.json
      2023-05-08/ report.txt, meta.json
      notes/
        2023-03-15/ note.txt, note.json
        2023-05-08/ note.txt, note.json
    ...
```

---

## App (RECIST dashboard) — local development

A small React app to visualize **SLD over time** and a table of metrics.
You’ll upload `patients/*/*/meta.json` or `cohort_labels.jsonl` from the generator above.

### Prereqs

* **Node.js LTS** (Windows: `winget install OpenJS.NodeJS.LTS --silent`, then reopen PowerShell)
* If PowerShell blocks npm scripts: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### Create the app (Vite + React + TS)

```powershell
cd C:\Users\erios\tumor
npm create vite@latest recist-dashboard -- --template react-ts
cd .\recist-dashboard
npm install
```

### Install deps

```powershell
npm i recharts
npm i -D tailwindcss @tailwindcss/postcss
```

### Tailwind v4 config (no `npx init` needed)

Create/overwrite **postcss.config.js**:

```js
export default {
  plugins: {
    '@tailwindcss/postcss': {},   // Tailwind v4 PostCSS plugin
  },
}
```

Create/overwrite **src/index.css**:

```css
@import "tailwindcss";
```

Ensure **src/main.tsx** imports the CSS:

```ts
import './index.css'
```

> Optional: delete template CSS if present (prevents conflicts)
>
> ```
> if (Test-Path .\src\App.css) { Remove-Item .\src\App.css -Force }
> ```

### Paste the dashboard UI

Open **src/App.tsx** and replace its contents with your dashboard component (the RECIST dashboard code in this repo/README).

Tip: set the outer div to include `font-sans`:

```tsx
<div className="min-h-screen bg-zinc-950 text-zinc-200 font-sans">
```

### Run

```powershell
npm run dev
```

Open the URL shown (e.g., `http://localhost:5173`), then:

* **Upload** multiple `meta.json` files (multi-select) **or**
* Upload `cohort_labels.jsonl`.

### Troubleshooting

* **Tailwind v4 error about PostCSS** → You didn’t install/use `@tailwindcss/postcss`. Fix `postcss.config.js` exactly as above.
* **Plain styles** → Confirm `src/main.tsx` includes `import './index.css'`. Restart with `npm run dev -- --force`.
* **Recharts missing** → `npm i recharts` and restart dev server.

---

## License / Notes

* Synthetic data only; no PHI.
* RECIST logic implemented for training/testing pipelines; extend as needed for Choi/PERCIST.
