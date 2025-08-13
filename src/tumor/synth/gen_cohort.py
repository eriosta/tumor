# src/tumor/synth/gen_cohort.py
"""
Generate a cohort of synthetic oncologic CT CAP reports with RECIST 1.1
tracked over multiple timepoints per patient, with controllable "complexity"
(artifacts/limitations, incidentals, post-treatment changes, hedging) and a
staging_relevance score to surface what matters for staging/response.

Creates subfolders:
  <out_dir>/patients/<PATIENT_ID>/<YYYY-MM-DD>/
    - report.txt  (organ-structured FINDINGS + IMPRESSION)
    - meta.json   (patient_id, study_date, timepoint, recist summary, complexity, relevance)

Also writes a cohort-level index:
  <out_dir>/cohort_labels.jsonl

Uses helpers from tumor.synth.gen_cap:
- gen_primary, gen_ln, gen_met
- recist_targets, apply_response_to_targets
- assemble_findings, assemble_recist_block, assemble_impression

Run:
  python -m tumor.synth.gen_cohort ^
    --out_dir data/synth_patients ^
    --n_patients 50 ^
    --min_tp 3 --max_tp 6 ^
    --seed 42 ^
    --style structured --include_negatives ^
    --complexity_config configs/complexity.json ^
    --complexity_level 3

Notes:
- PD uses RECIST 1.1 *nadir-based* rule (>=20% from nadir AND >=5 mm, or unequivocal new lesions).
- FINDINGS text updates sizes for targets each follow-up so prose matches the RECIST table.
- All file writes are UTF-8-safe.
"""

# src/tumor/synth/gen_cohort.py
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from tumor.synth.gen_cap import (
    gen_primary, gen_ln, gen_met,
    recist_targets, apply_response_to_targets,
    assemble_findings, assemble_impression, assemble_recist_block
)
from tumor.synth.complexity import load_complexity, compute_staging_relevance


# ------------------------- small utils -------------------------

def rbool(p: float) -> bool:
    return random.random() < p

def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def next_followup_date(d: datetime) -> datetime:
    # ~8 weeks +/- 2 weeks
    delta = 56 + random.randint(-14, 14)
    return d + timedelta(days=delta)

def recist_overall_from_nadir(
    base_sld: int,
    current_sld: int,
    nadir_sld: int,
    has_new_unequivocal: bool,
    all_targets_disappeared: bool,
    any_node_ge10: bool
) -> str:
    if all_targets_disappeared and not has_new_unequivocal and not any_node_ge10:
        return "CR"
    if has_new_unequivocal:
        return "PD"
    if base_sld == 0:
        return "SD"
    if (current_sld - base_sld) / base_sld <= -0.30:
        return "PR"
    if nadir_sld > 0 and (current_sld - nadir_sld) / nadir_sld >= 0.20 and (current_sld - nadir_sld) >= 5:
        return "PD"
    return "SD"

def update_structures_with_follow_targets(
    primary: Dict, lns: List[Dict], mets: List[Dict], follow_targets: Optional[List[Dict]]
) -> Tuple[Dict, List[Dict], List[Dict]]:
    p = dict(primary)
    ln_list = [dict(x) for x in lns]
    m_list = [dict(x) for x in mets]
    if not follow_targets:
        return p, ln_list, m_list
    for t in follow_targets:
        if t["kind"] == "primary":
            p["size_mm"] = t["follow_mm"]
        elif t["kind"] == "ln":
            for ln in ln_list:
                if ln.get("station") == t.get("station"):
                    ln["short_axis_mm"] = t["follow_mm"]
                    break
        elif t["kind"] == "met":
            for m in m_list:
                if m.get("site") == t.get("site"):
                    m["size_mm"] = t["follow_mm"]
                    break
    return p, ln_list, m_list

# ---- Lesion catalog helpers ----
def _lesion_key(t: dict) -> str:
    # stable key for matching baseline ↔ follow
    if t["kind"] == "ln":
        return f"ln:{t.get('station','?')}"
    if t["kind"] == "met":
        return f"met:{t.get('site','?')}"
    return f"primary:{t.get('organ','?')}"

def build_lesion_catalog(
    primary: dict,
    lns: list[dict],
    mets: list[dict],
    base_targets: list[dict],
    follow_targets: list[dict] | None,
) -> list[dict]:
    """Return per-lesion rows with baseline/follow sizes + characteristics."""
    catalog: list[dict] = []

    # index targets
    base_idx = { _lesion_key(t): t for t in base_targets }
    fol_idx  = { _lesion_key(t): t for t in (follow_targets or []) }

    # primary
    pri_key = f"primary:{primary['site']}"
    catalog.append({
        "lesion_id": pri_key,
        "kind": "primary",
        "organ": primary["site"],
        "location": primary.get("location"),
        "rule": "longest",
        "baseline_mm": base_idx.get(pri_key, {}).get("measure_mm"),   # None if not selected as target
        "follow_mm": fol_idx.get(pri_key, {}).get("follow_mm"),
        "size_mm_current": primary.get("size_mm"),
        "margin": primary.get("margin"),
        "enhancement": primary.get("enhancement"),
        "suspicious": True,                 # primary is malignant
        "target": pri_key in base_idx,      # whether used as RECIST target
    })

    # lymph nodes (report suspicious ones too: SA >= 10 mm)
    for ln in lns:
        key = f"ln:{ln['station']}"
        sa = ln["short_axis_mm"]
        catalog.append({
            "lesion_id": key,
            "kind": "ln",
            "organ": "lymph",
            "station": ln["station"],
            "rule": "short_axis",
            "baseline_mm": base_idx.get(key, {}).get("measure_mm"),
            "follow_mm": fol_idx.get(key, {}).get("follow_mm"),
            "size_mm_current": sa,
            "necrosis": bool(ln.get("necrosis")),
            "suspicious": sa >= 10,          # ≥10 mm short axis considered suspicious
            "target": key in base_idx,
        })

    # metastases
    for m in mets:
        key = f"met:{m['site']}"
        catalog.append({
            "lesion_id": key,
            "kind": "met",
            "organ": m["site"],
            "rule": "longest",
            "baseline_mm": base_idx.get(key, {}).get("measure_mm"),
            "follow_mm": fol_idx.get(key, {}).get("follow_mm"),
            "size_mm_current": m.get("size_mm"),
            "suspicious": True,              # mets are malignant/suspicious by definition here
            "target": key in base_idx,
        })

    return catalog

# ------------------------- FINDINGS merger -------------------------
# Map generator/org keys -> canonical FINDINGS headers in your prose
ORG_HEADER_MAP = {
    "lung": "Lungs",
    "lungs": "Lungs",
    "mediastinum": "Mediastinum",
    "pleura": "Pleura/Pleural spaces",
    "pleura.": "Pleura/Pleural spaces",
    "aorta_great_vessels": "Great vessels/Aorta",
    "liver": "Liver",
    "spleen": "Spleen",
    "pancreas": "Pancreas",
    "adrenals": "Adrenal glands",
    "adrenal": "Adrenal glands",
    "kidneys": "Kidneys",
    "kidney": "Kidneys",
    "bladder": "Urinary bladder",
    "gi": "GI tract/Bowel",
    "gi.stomach": "GI tract/Bowel",
    "gi.colon": "GI tract/Bowel",
    "stomach": "GI tract/Bowel",
    "colon": "GI tract/Bowel",
    "small_bowel": "GI tract/Bowel",
    "mesentery_peritoneum": "Mesentery/Omentum",
    "mesentery": "Mesentery/Omentum",
    "peritoneum": "Mesentery/Omentum",
    "mesenteric_vessels": "Mesenteric vessels (SMA/SMV)",
    "reproductive": "Reproductive organs",
    "ovary": "Reproductive organs",
    "ovaries": "Reproductive organs",
    "prostate": "Reproductive organs",
    "lymph_nodes": "Lymph nodes",
    "nodes": "Lymph nodes",
    "bones": "Bones/Osseous structures",
    "osseous": "Bones/Osseous structures",
}

def _normalize_key(k: str) -> str:
    k = k.lower().replace(" ", "_")
    return k

def _find_header_index(lines: List[str], header: str) -> Optional[int]:
    prefix = f"{header}:"
    for i, ln in enumerate(lines):
        if ln.strip().startswith(prefix):
            return i
    return None

def _append_sentence(base: str, sentence: str) -> str:
    base = base.rstrip()
    s = sentence.strip()
    if not s.endswith("."):
        s += "."
    # avoid duplicates
    if s[:-1].lower() in base.lower():
        return base
    if not base.endswith("."):
        base += "."
    return base + " " + s

def _infer_organ_for_post_treat(text: str, primary_site: Optional[str]) -> str:
    t = text.lower()
    if "lung" in t or "beam path" in t or "radiation change" in t:
        return "Lungs"
    if "liver" in t or "hepatic" in t or "sbrt" in t or "embolization" in t or "ablation" in t:
        return "Liver"
    if "kidney" in t or "renal" in t:
        return "Kidneys"
    if "pancreas" in t or "pancreatic" in t:
        return "Pancreas"
    if "prostate" in t or "hysterectomy" in t or "adnex" in t or "pelvis" in t or "brachy" in t:
        return "Reproductive organs"
    if "colon" in t or "anastomosis" in t:
        return "GI tract/Bowel"
    # fallback to primary organ if we have it
    if primary_site in ORG_HEADER_MAP:
        return ORG_HEADER_MAP[primary_site]
    return "Lymph nodes"  # safe default

def merge_into_findings_by_organ(
    raw_findings_text: str,
    incidentals: List[Dict[str, str]],
    negatives: List[Dict[str, str]],
    post_treat: List[str],
    primary_site: Optional[str],
    preface_lines: List[str]
) -> str:
    """
    Takes the string produced by assemble_findings() and appends incidental/negative/post-treatment
    content directly to the corresponding organ lines. Adds preface lines at the very top
    (e.g., comparison or limitations).
    """
    # split into lines, find headers like "Liver:", "Lungs:", etc.
    lines = [ln.rstrip() for ln in raw_findings_text.strip().splitlines() if ln.strip()]

    # Build a map header->index for quick writes
    header_to_idx: Dict[str, int] = {}
    for i, ln in enumerate(lines):
        if ":" in ln:
            head = ln.split(":", 1)[0].strip()
            header_to_idx[head] = i

    # integrate incidentals
    for it in incidentals:
        key = _normalize_key(it["organ"])
        header = ORG_HEADER_MAP.get(key, ORG_HEADER_MAP.get(key.split(".")[0], None))
        if not header: 
            continue
        idx = header_to_idx.get(header)
        if idx is None:
            continue
        lines[idx] = _append_sentence(lines[idx], it["text"])

    # integrate negatives
    for ng in negatives:
        key = _normalize_key(ng["organ"])
        header = ORG_HEADER_MAP.get(key, ORG_HEADER_MAP.get(key.split(".")[0], None))
        if not header:
            continue
        idx = header_to_idx.get(header)
        if idx is None:
            continue
        lines[idx] = _append_sentence(lines[idx], ng["text"])

    # integrate post-treatment / procedural changes
    for pt in post_treat:
        header = _infer_organ_for_post_treat(pt, primary_site)
        idx = header_to_idx.get(header)
        if idx is None:
            continue
        # normalize phrasing for inline use
        phr = pt.replace("Radiation change:", "Post-treatment change:").strip()
        lines[idx] = _append_sentence(lines[idx], phr)

    # preface (e.g., limitations, comparison) at the top of FINDINGS
    if preface_lines:
        pre_text = "\n".join(preface_lines) + "\n"
    else:
        pre_text = ""

    return pre_text + "\n".join(lines)


# ------------------------- trajectory -------------------------

def pick_trajectory() -> List[str]:
    choices = [
        ["PR", "PR", "SD"],
        ["SD", "PD", "PD"],
        ["PR", "SD", "PD"],
        ["SD", "SD", "SD"],
    ]
    return random.choice(choices)


# ------------------------- main cohort synth -------------------------

def synth_patient_course(
    pid: str,
    style: str,
    include_negatives: bool,
    met_rate: float,
    uncertainty_mix: float,  # kept for API compatibility; hedging now from complexity
    unit_mix: float,
    primary_mix: List[str],
    min_tp: int,
    max_tp: int,
    cx: Any
) -> Dict[str, Any]:
    # Baseline disease
    primary = gen_primary(random.choice(primary_mix))
    lns: List[Dict[str, Any]] = []
    if primary["site"] == "lung" or rbool(0.4):
        if rbool(0.6):
            lns.append(gen_ln("thoracic"))
    if primary["site"] in ["colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"] or rbool(0.5):
        if rbool(0.6):
            lns.append(gen_ln("abdominal"))
        if rbool(0.4):
            lns.append(gen_ln("pelvic"))

    mets: List[Dict[str, Any]] = []
    if rbool(met_rate):
        for _ in range(random.randint(1, 2)):
            mets.append(gen_met())

    # Baseline targets & SLD/nadir
    base_targets, _ = recist_targets(primary, lns, mets)
    base_sld = sum(t["measure_mm"] for t in base_targets)
    nadir_sld = base_sld

    # Timepoints
    n_tp = random.randint(min_tp, max_tp)
    day0 = datetime(2023, random.randint(1, 12), random.randint(1, 28))
    dates = [day0] + [next_followup_date(day0)]
    for _ in range(n_tp - 2):
        dates.append(next_followup_date(dates[-1]))

    traj = pick_trajectory()
    studies: List[Dict[str, Any]] = []

    for i, dt in enumerate(dates):
        # complexity-driven extras
        artifact = cx.pick_artifact()
        limitation_line = cx.limitation_line(artifact)
        incidentals = cx.sample_incidentals()
        negatives = cx.sample_structured_negatives()
        post_treat = cx.sample_post_treatment_effects(primary.get("site"))
        hedge_phrase = cx.hedge_phrase_or_none()
        hedge_flag = "indeterminate" if hedge_phrase else "definite"

        # RECIST for this TP
        has_new = False
        curr_sld: Optional[int] = None
        follow_targets: Optional[List[Dict[str, Any]]] = None

        if i == 0:
            recist_cat = "Baseline (no category)"
            recist_text = assemble_recist_block(base_targets, [], has_new=False)
            p_cur, lns_cur, mets_cur = primary, lns, mets
        else:
            plan = traj[min(i - 1, len(traj) - 1)]
            follow_targets, _ = apply_response_to_targets(base_targets, plan)
            has_new = (plan == "PD" and rbool(0.7)) or rbool(0.03)

            curr_sld = sum(t["follow_mm"] for t in follow_targets)
            nadir_sld = min(nadir_sld, curr_sld if curr_sld is not None else nadir_sld)
            all_disappeared = all(t["follow_mm"] == 0 for t in follow_targets if t["kind"] != "ln")
            any_node_ge10 = any(t["follow_mm"] >= 10 for t in follow_targets if t["kind"] == "ln")

            recist_cat = recist_overall_from_nadir(
                base_sld=base_sld,
                current_sld=curr_sld,
                nadir_sld=nadir_sld,
                has_new_unequivocal=has_new,
                all_targets_disappeared=all_disappeared,
                any_node_ge10=any_node_ge10
            )
            recist_text = assemble_recist_block(base_targets, follow_targets, has_new)
            p_cur, lns_cur, mets_cur = update_structures_with_follow_targets(primary, lns, mets, follow_targets)

        # FINDINGS core text from your generator (organ-structured)
        core_findings = assemble_findings(
            p_cur, lns_cur, mets_cur, unit_mm_prob=unit_mix,
            include_negatives=include_negatives, comparison="",  # comparison handled below
            nonmeasurable_flags={"peritoneal_carcinomatosis": False}
        )

        # Build preface lines that must live INSIDE FINDINGS (since you want only two sections)
        preface_lines: List[str] = []
        if limitation_line:
            preface_lines.append(limitation_line)
        if i > 0:
            preface_lines.append(f"Comparison: {iso(dates[i - 1])}.")

        # Merge incidentals/negatives/post-treatment into correct organ lines
        merged_findings = merge_into_findings_by_organ(
            raw_findings_text=core_findings,
            incidentals=incidentals,
            negatives=negatives,
            post_treat=post_treat,
            primary_site=primary.get("site"),
            preface_lines=preface_lines
        )

        # IMPRESSION
        impression_body = assemble_impression(
            p_cur, lns_cur, mets_cur,
            hedge=hedge_flag,
            recist_text=recist_text,
            recist_category=recist_cat
        )
        if hedge_phrase:
            impression_body += f"\n\nComment: Some features are {hedge_phrase}; short-interval follow-up or problem-solving imaging may be considered."

        # FINAL REPORT: ONLY two sections by requirement
        report_text = "FINDINGS:\n" + merged_findings + "\n\nIMPRESSION:\n" + impression_body + "\n"

        # staging relevance
        node_thresh = cx.recist["node_thresholds_mm"]["target_short_axis_min"]
        nodes_crossed = bool(follow_targets and any(
            (t.get("kind") == "ln" and (t.get("follow_mm") or 0) >= node_thresh) for t in follow_targets
        ))
        relevance = compute_staging_relevance(
            cfg=cx,
            recist={
                "overall_response": recist_cat,
                "current_sld_mm": None if i == 0 else curr_sld,
                "nadir_sld_mm": None if i == 0 else nadir_sld
            },
            has_new_measurable_met=bool(has_new) if i > 0 else False,
            nodes_crossed_threshold=nodes_crossed if i > 0 else False,
            artifact=artifact,
            used_equivocal_language=bool(hedge_phrase),
        )
        complexity_profile = {
            "level": int(cx.level_name[1:]),
            "level_name": cx.level_name,
            "artifact": artifact
        }

        # build a per-timepoint lesion catalog using CURRENT structures + RECIST linkage
        lesions = build_lesion_catalog(
            primary=p_cur,
            lns=lns_cur,
            mets=mets_cur,
            base_targets=base_targets,
            follow_targets=follow_targets,
        )

        studies.append({
            "patient_id": pid,
            "timepoint": i,
            "study_date": iso(dt),
            "report_text": report_text,
            "recist": {
                "baseline_sld_mm": base_sld,
                "current_sld_mm": None if i == 0 else curr_sld,
                "nadir_sld_mm": None if i == 0 else nadir_sld,
                "overall_response": recist_cat
            },
            "complexity_profile": complexity_profile,
            "staging_relevance": relevance,
            "extras": {
                "incidentals": incidentals,
                "negatives": negatives,
                "post_treatment": post_treat,
            'lesions': lesions
            }
        })

    return {
        "patient_id": pid,
        "baseline_date": iso(dates[0]),
        "n_timepoints": len(studies),
        "studies": studies
    }


# ------------------------- CLI -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--n_patients", type=int, default=20)
    ap.add_argument("--min_tp", type=int, default=3)
    ap.add_argument("--max_tp", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--style", choices=["narrative", "structured", "impression_first"], default="structured")
    ap.add_argument("--include_negatives", action="store_true")
    ap.add_argument("--met_rate", type=float, default=0.35)
    ap.add_argument("--uncertainty_mix", type=float, default=0.2)  # kept for API compat
    ap.add_argument("--unit_mix", type=float, default=0.7)
    ap.add_argument("--primary_mix", nargs="+",
                    default=["lung", "colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"])
    ap.add_argument("--complexity_config", type=str, default="configs/complexity.json")
    ap.add_argument("--complexity_level", type=int, choices=range(0, 6), default=2)
    args = ap.parse_args()

    random.seed(args.seed)
    out = Path(args.out_dir)
    (out / "patients").mkdir(parents=True, exist_ok=True)
    cohort_labels = out / "cohort_labels.jsonl"

    cx = load_complexity(args.complexity_config, args.complexity_level)

    with cohort_labels.open("w", encoding="utf-8") as idx:
        for i in range(args.n_patients):
            pid = f"PID{i:06d}"
            patient = synth_patient_course(
                pid=pid,
                style=args.style,
                include_negatives=args.include_negatives,
                met_rate=args.met_rate,
                uncertainty_mix=args.uncertainty_mix,
                unit_mix=args.unit_mix,
                primary_mix=args.primary_mix,
                min_tp=args.min_tp,
                max_tp=args.max_tp,
                cx=cx,
            )

            pdir = out / "patients" / pid
            for s in patient["studies"]:
                sdir = pdir / s["study_date"]
                sdir.mkdir(parents=True, exist_ok=True)
                (sdir / "report.txt").write_text(s["report_text"], encoding="utf-8")
                meta = {k: v for k, v in s.items() if k != "report_text"}
                (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

                # Append to cohort index (FULL payload for dashboard; UTF-8, no ASCII escaping)
                idx.write(json.dumps({
                    "patient_id": s["patient_id"],
                    "study_date": s["study_date"],
                    "timepoint": s["timepoint"],

                    # full RECIST object (baseline/current/nadir + overall)
                    "recist": s["recist"],

                    # lesion-level details (targets + non-target suspicious)
                    # fields include: lesion_id, kind, organ, rule, target, baseline_mm, follow_mm,
                    # size_mm_current, margin/enhancement/necrosis when applicable
                    "lesions": s.get("extras", {}).get("lesions", []),

                    # complexity + relevance for triage
                    "complexity_profile": s.get("complexity_profile"),
                    "staging_relevance": s.get("staging_relevance"),

                    # optional context (inline with organ sections in your FINDINGS)
                    "incidentals": s.get("extras", {}).get("incidentals", []),
                    "negatives": s.get("extras", {}).get("negatives", []),
                    "post_treatment": s.get("extras", {}).get("post_treatment", []),

                    # include the rendered report so the app can show/preview it if desired
                    "report_text": s["report_text"],
                }, ensure_ascii=False) + "\n")


    print(f"Generated {args.n_patients} patients at {out}/patients and index at {cohort_labels}")

if __name__ == "__main__":
    main()
