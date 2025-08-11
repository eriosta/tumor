# Onc Rad Reports LLM — Starter

**Goal:** Extract TNM-relevant, structured features from radiology reports (CT/MRI/PET-CT), output JSON, load to Postgres, and optionally use RAG for guideline-aware outputs.

## Quickstart

```bash
# 0) Clone & enter
unzip onc-rad-reports-llm.zip && cd onc-rad-reports-llm

# 1) Create env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Optional: start Postgres (Docker)
docker compose up -d

# 3) Put de-identified reports into data/raw/. One report per .txt file.

# 4) Preprocess -> data/processed/
python -m onc_rad_reports.preprocess.run --in_dir data/raw --out_dir data/processed --schema configs/tnm_schema.json

# 5) Bootstrap labels (optional) -> data/labels/
python -m onc_rad_reports.preprocess.bootstrap_labels --in_dir data/processed --out_path data/labels/seed_labels.jsonl

# 6) Train (LoRA by default)
python -m onc_rad_reports.training.train --train data/processed/train.jsonl --val data/processed/val.jsonl --config configs/train_lora.yaml

# 7) Evaluate
python -m onc_rad_reports.eval.run --preds models/latest/preds.jsonl --gold data/processed/test.jsonl --config configs/metrics.yaml

# 8) Load to DB
python -m onc_rad_reports.db.load --in_file models/latest/preds.jsonl --dsn postgresql://onc:onc@localhost:5432/onc

# 9) RAG server (guideline-aware extraction)
python -m onc_rad_reports.rag.server --port 8080
```

## Repo layout
- `src/onc_rad_reports/preprocess`: sectioning, normalization, unit conversion, PHI scrubbing
- `src/onc_rad_reports/training`: SFT/LoRA/QLoRA pipelines (HuggingFace)
- `src/onc_rad_reports/eval`: exact match, span-F1, adjudication support
- `src/onc_rad_reports/schema`: TNM JSON schema and ontology mappings (RadLex/SNOMED placeholders)
- `src/onc_rad_reports/db`: Postgres DDL + loader
- `src/onc_rad_reports/rag`: retrieval over templates/guidelines; HTTP server for inference
- `configs`: YAML/JSON config for training, metrics, and schema
- `data`: place de-identified inputs here

## Notes
- Keep everything in **mm**. Normalizer converts cm↔mm.
- Treat uncertain language explicitly: `certainty: possible|probable|definite`.
- Each lesion/node gets a unique `lesion_id` for longitudinal tracking.
