import argparse, os, json, glob

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_path", required=True)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out_path), exist_ok=True)
    with open(args.out_path, "w") as out:
        for fp in glob.glob(os.path.join(args.in_dir, "*.jsonl")):
            for line in open(fp):
                ex = json.loads(line)
                out.write(json.dumps({"report_text": ex.get("report_text",""), "label": ex.get("schema_json",{})}) + "\n")

if __name__ == "__main__":
    main()
