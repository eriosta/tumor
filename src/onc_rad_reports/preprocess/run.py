import argparse, json, os, re, uuid, glob
from datetime import datetime

def section_report(text: str):
    # Simple splitter; replace with robust parser if needed
    parts = re.split(r'\b(IMPRESSION|FINDINGS)\b[:\-]?', text, flags=re.I)
    return {"full": text, "findings": text, "impression": text} if len(parts) < 3 else {
        "full": text, "findings": parts[parts.index("FINDINGS")+1] if "FINDINGS" in parts else "",
        "impression": parts[parts.index("IMPRESSION")+1] if "IMPRESSION" in parts else ""
    }

def normalize_units(text: str):
    # Convert cm to mm
    text = re.sub(r'(\d+(\.\d+)?)\s*cm\b', lambda m: f"{int(round(float(m.group(1))*10))} mm", text, flags=re.I)
    return text

def to_example(record_text: str, schema: dict):
    # Minimal heuristic bootstrap to create train example
    ex = {"report_text": record_text.strip(), "schema_json": {}}
    m_size = re.search(r'(\d+)\s*mm\b.*?(mass|lesion)', record_text, flags=re.I)
    if m_size:
        ex["schema_json"]["primary_tumor"] = {"size_mm": int(m_size.group(1))}
    return ex

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--schema", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    schema = json.load(open(args.schema))

    files = sorted(glob.glob(os.path.join(args.in_dir, "*.txt")))
    out_train = open(os.path.join(args.out_dir, "train.jsonl"), "w")
    out_val = open(os.path.join(args.out_dir, "val.jsonl"), "w")
    out_test = open(os.path.join(args.out_dir, "test.jsonl"), "w")

    for i, fp in enumerate(files):
        text = open(fp).read()
        text = normalize_units(text)
        sections = section_report(text)
        ex = to_example(sections["full"], schema)
        line = json.dumps(ex)
        if i % 10 == 0:
            out_val.write(line + "\n")
        elif i % 10 == 1:
            out_test.write(line + "\n")
        else:
            out_train.write(line + "\n")

    for f in (out_train, out_val, out_test):
        f.close()

if __name__ == "__main__":
    main()
