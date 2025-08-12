import argparse
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

class Query(BaseModel):
    question: str

DOCS = [
    {"id": "fleschner2017", "text": "Fleischner 2017: Solid 6 mm nodule, low-risk -> optional CT at 12 months."},
    {"id": "acr_incidental_liver", "text": "ACR incidental liver lesion: >1.5 cm hyperenhancing -> MRI in high-risk."}
]

def retrieve(q: str, k=3):
    ql = q.lower().split()
    scored = [(d, sum(w in d["text"].lower() for w in ql)) for d in DOCS]
    return [d for d, _ in sorted(scored, key=lambda x: -x[1])[:k]]

@app.post("/rag")
def rag(query: Query):
    hits = retrieve(query.question)
    return JSONResponse({"question": query.question, "contexts": hits, "answer": "Placeholder grounded answer."})

if __name__ == "__main__":
    import uvicorn, argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
