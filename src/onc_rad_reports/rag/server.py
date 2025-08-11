import argparse, os, json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Query(BaseModel):
    question: str

# In-memory "retrieval" index placeholder
DOCS = [
    {"id": "fleschner2017", "text": "Fleischner Society 2017: Solid 6 mm nodule, low-risk -> optional CT at 12 months."},
    {"id": "acr_liver", "text": "ACR incidental liver lesion: hyperenhancing lesion > 1.5 cm requires MRI in high-risk."}
]

def retrieve(q: str, k=3):
    ql = q.lower()
    scored = [(doc, sum(w in doc["text"].lower() for w in ql.split())) for doc in DOCS]
    return [d for d, s in sorted(scored, key=lambda x: -x[1])[:k]]

@app.post("/rag")
def rag(query: Query):
    hits = retrieve(query.question)
    # Normally: construct prompt for LLM; here we just echo retrieved docs
    return JSONResponse({"question": query.question, "contexts": hits, "answer": "Placeholder answer grounded in retrieved snippets."})

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
