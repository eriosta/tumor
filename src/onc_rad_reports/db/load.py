import argparse, json, os
import psycopg2
from psycopg2.extras import execute_batch

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_file", required=True)
    ap.add_argument("--dsn", required=True)
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    cur = conn.cursor()

    preds = [json.loads(l) for l in open(args.in_file)]
    # Minimal loader storing only report_text as example
    execute_batch(cur, "INSERT INTO report (source_file, report_text) VALUES (%s, %s)", [
        ("val", p.get("report_text","")) for p in preds
    ])
    conn.commit()
    print("Loaded reports.")

if __name__ == "__main__":
    main()
