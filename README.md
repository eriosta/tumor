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
