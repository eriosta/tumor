import argparse, os, json
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

def format_example(ex, input_key, target_key, tmpl_path=None):
    prompt = ex[input_key]
    if tmpl_path and os.path.exists(tmpl_path):
        template = open(tmpl_path).read()
        prompt = template.replace("{{report_text}}", ex[input_key])
    target = json.dumps(ex[target_key], ensure_ascii=False)
    return {"prompt": prompt, "target": target}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    import yaml
    cfg = yaml.safe_load(open(args.config))
    model_name = cfg["model_name"]
    input_key = cfg["data"]["input_key"]
    target_key = cfg["data"]["target_key"]
    prompt_tmpl = "configs/prompt_template.txt"

    # Load model/tokenizer
    tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForCausalLM.from_pretrained(model_name, device_map="auto", trust_remote_code=True)

    if cfg["method"] == "lora":
        lora = LoraConfig(r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=cfg["lora_dropout"], target_modules=["q_proj","v_proj","k_proj","o_proj"])
        model = get_peft_model(model, lora)

    # Build datasets
    def ds_from_jsonl(path):
        data = [json.loads(l) for l in open(path)]
        formatted = [format_example(ex, input_key, target_key, prompt_tmpl) for ex in data]
        return formatted

    train_data = ds_from_jsonl(args.train)
    val_data = ds_from_jsonl(args.val)

    # Tokenize
    def tokenize(ex):
        text = ex["prompt"] + "\n\n" + ex["target"]
        out = tok(text, truncation=True, max_length=2048)
        out["labels"] = out["input_ids"].copy()
        return out

    train_tok = list(map(tokenize, train_data))
    val_tok = list(map(tokenize, val_data))

    # Trainer
    out_dir = "models/latest"
    os.makedirs(out_dir, exist_ok=True)
    targs = TrainingArguments(
        output_dir=out_dir,
        per_device_train_batch_size=cfg["train"]["per_device_train_batch_size"],
        per_device_eval_batch_size=cfg["train"]["per_device_eval_batch_size"],
        learning_rate=cfg["train"]["learning_rate"],
        num_train_epochs=cfg["train"]["epochs"],
        bf16=cfg["train"].get("bf16", False),
        evaluation_strategy="epoch",
        save_strategy="epoch",
        logging_steps=10
    )

    trainer = Trainer(model=model, args=targs, train_dataset=train_tok, eval_dataset=val_tok)
    trainer.train()

    # Dummy predictions file
    with open(os.path.join(out_dir, "preds.jsonl"), "w") as f:
        for ex in val_data[:5]:
            f.write(json.dumps({"report_text": ex["prompt"], "prediction": ex["target"]}) + "\n")

if __name__ == "__main__":
    main()
