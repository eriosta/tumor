#!/usr/bin/env bash
set -euo pipefail
python -m tumor.synth.gen_cap --out_dir data/synth --n ${N:-500} --seed 42 --style structured --include_negatives
python -m tumor.preprocess.run --in_dir data/synth/reports --out_dir data/processed --schema configs/tnm_schema.json
python -m tumor.training.train --train data/processed/train.jsonl --val data/processed/val.jsonl --config configs/train_lora.yaml
python -m tumor.eval.run --preds models/latest/preds.jsonl --gold data/processed/test.jsonl --config configs/metrics.yaml
