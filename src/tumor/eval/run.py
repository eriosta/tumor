import argparse, json, re, yaml

def fuzzy(a, b):
    norm = lambda x: re.sub(r'\W+', '', str(x)).lower()
    return norm(a) == norm(b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    preds = [json.loads(l) for l in open(args.preds)]
    golds = [json.loads(l) for l in open(args.gold)]

    exact = 0; total = min(len(preds), len(golds))
    for p, g in zip(preds, golds):
        exact += int(p.get("prediction") == g.get("schema_json"))
    print(f"Exact Match (placeholder): {exact}/{total}")

if __name__ == "__main__":
    main()
