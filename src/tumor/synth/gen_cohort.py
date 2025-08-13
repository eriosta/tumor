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

from __future__ import annotations

import argparse
import json
import pathlib
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from tumor.synth.gen_cap import (
    gen_primary, gen_ln, gen_met,
    recist_targets, apply_response_to_targets,
    assemble_findings, assemble_recist_block, assemble_impression
)

# NEW: complexity controls
from tumor.synth.complexity import load_complexity, compute_staging_relevance


# ------------------------- helpers -------------------------

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
    # CR
    if all_targets_disappeared and not has_new_unequivocal and not any_node_ge10:
        return "CR"
    # PD by new lesions
    if has_new_unequivocal:
        return "PD"
    # If no measurable targets at baseline, call SD
    if base_sld == 0:
        return "SD"
    # PR by decrease from baseline
    if (current_sld - base_sld) / base_sld <= -0.30:
        return "PR"
    # PD by increase from nadir (min SLD achieved)
    if nadir_sld > 0:
        if (current_sld - nadir_sld) / nadir_sld >= 0.20 and (current_sld - nadir_sld) >= 5:
            return "PD"
    return "SD"

def update_structures_with_follow_targets(
    primary: Dict, lns: List[Dict], mets: List[Dict], follow_targets: Optional[List[Dict]]
) -> Tuple[Dict, List[Dict], List[Dict]]:
    """
    Return copies of primary/lns/mets with sizes updated to reflect follow-up
    target measurements (so prose matches RECIST table).
    """
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

def pick_trajectory() -> List[str]:
    """
    Planned responses for a course; extended by repeating final state.
    """
    choices = [
        ["PR", "PR", "SD"],     # responder
        ["SD", "PD", "PD"],     # progressor
        ["PR", "SD", "PD"],     # mixed
        ["SD", "SD", "SD"],     # flat SD
    ]
    traj = random.choice(choices)
    return traj


# ------------------------- main cohort synth -------------------------

def synth_patient_course(
    pid: str,
    style: str,
    include_negatives: bool,
    met_rate: float,
    uncertainty_mix: float,   # kept for API compatibility (not used directly; hedging comes from complexity)
    unit_mix: float,
    primary_mix: List[str],
    min_tp: int,
    max_tp: int,
    cx: Any,                  # ComplexityConfig
) -> Dict[str, Any]:
    """
    Build one patient's longitudinal course with reports and labels.
    """
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
    dates = [day0]
    for _ in range(n_tp - 1):
        dates.append(next_followup_date(dates[-1]))

    traj = pick_trajectory()

    studies: List[Dict[str, Any]] = []
    for i, dt in enumerate(dates):
        # ---------------- complexity-driven extras ----------------
        artifact = cx.pick_artifact()
        limitation_line = cx.limitation_line(artifact)
        incidentals = cx.sample_incidentals()
        negatives = cx.sample_structured_negatives()
        post_treat = cx.sample_post_treatment_effects(primary.get("site"))
        hedge_phrase = cx.hedge_phrase_or_none()
        hedge_flag = "indeterminate" if hedge_phrase else "definite"

        # ---------------- RECIST for this TP ----------------
        has_new = False
        curr_sld: Optional[int] = None
        follow_targets: Optional[List[Dict[str, Any]]] = None

        if i == 0:
            # Baseline
            recist_cat = "Baseline (no category)"
            recist_text = assemble_recist_block(base_targets, [], has_new=False)
            p_cur, lns_cur, mets_cur = primary, lns, mets
        else:
            plan = traj[min(i - 1, len(traj) - 1)]
            follow_targets, _ = apply_response_to_targets(base_targets, plan)

            # New lesion probability increases when planning PD
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

            # Update structures so FINDINGS prose reflects follow-up sizes
            p_cur, lns_cur, mets_cur = update_structures_with_follow_targets(primary, lns, mets, follow_targets)

        # ---------------- text assembly ----------------
        comparison = "" if i == 0 else f"Compared to prior {iso(dates[i - 1])}, interval evaluation as below."
        technique = random.choice([
            "CT chest, abdomen, and pelvis performed with IV contrast. Contiguous <=5-mm axial images.",
            "Contrast-enhanced CT CAP with portal venous phase abdomen/pelvis; chest imaged in a single post-contrast phase.",
        ])
        if limitation_line:
            technique += f" {limitation_line}"

        header = f"EXAM: CT CAP\nTECHNIQUE: {technique}\nHISTORY: Staging/restaging of solid malignancy.\n"

        findings = "FINDINGS:\n" + assemble_findings(
            p_cur, lns_cur, mets_cur, unit_mm_prob=unit_mix,
            include_negatives=include_negatives, comparison=comparison,
            nonmeasurable_flags={"peritoneal_carcinomatosis": False}
        )

        # Extra realism blocks controlled by complexity
        extra_blocks: List[str] = []
        if post_treat:
            extra_blocks.append("POST-TREATMENT / PROCEDURAL CHANGES:\n" + "\n".join(f"- {t}" for t in post_treat))
        if incidentals:
            extra_blocks.append("INCIDENTAL / OTHER FINDINGS:\n" + "\n".join(f"- {it['organ']}: {it['text']}" for it in incidentals))
        if negatives:
            extra_blocks.append("NEGATIVE FINDINGS:\n" + "\n".join(f"- {ng['organ']}: {ng['text']}" for ng in negatives))
        if extra_blocks:
            findings = findings + "\n" + "\n\n".join(extra_blocks)

        impression_body = assemble_impression(
            p_cur, lns_cur, mets_cur,
            hedge=hedge_flag,
            recist_text=recist_text,
            recist_category=recist_cat
        )
        if hedge_phrase:
            impression_body += f"\n\nComment: Some features are {hedge_phrase}; short-interval follow-up or problem-solving imaging may be considered."
        impression = "IMPRESSION:\n" + impression_body

        if style == "impression_first":
            report_text = header + "\n" + impression + "\n\n" + findings + "\n"
        elif style == "structured":
            report_text = header + "\n" + findings + "\n\n" + impression + "\n"
        else:
            report_text = header + "\n" + findings.replace("\n", " ") + "\n\n" + impression + "\n"

        # ---------------- staging relevance ----------------
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
            # NEW metadata
            "complexity_profile": complexity_profile,
            "staging_relevance": relevance,
            # include extras (useful for downstream IE/debug)
            "extras": {
                "incidentals": incidentals,
                "negatives": negatives,
                "post_treatment": post_treat
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
    ap.add_argument("--uncertainty_mix", type=float, default=0.2)  # kept for API compatibility
    ap.add_argument("--unit_mix", type=float, default=0.7)
    ap.add_argument("--primary_mix", nargs="+",
                    default=["lung", "colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"])
    # NEW: complexity controls
    ap.add_argument("--complexity_config", type=str, default="configs/complexity.json")
    ap.add_argument("--complexity_level", type=int, choices=range(0, 6), default=2)
    args = ap.parse_args()

    random.seed(args.seed)
    out = Path(args.out_dir)
    (out / "patients").mkdir(parents=True, exist_ok=True)
    cohort_labels = out / "cohort_labels.jsonl"

    # load complexity once
    cx = load_complexity(args.complexity_config, args.complexity_level)

    with open(cohort_labels, "w", encoding="utf-8") as idx:
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

            # Write per-study files under patient folder
            pdir = out / "patients" / pid
            for s in patient["studies"]:
                sdir = pdir / s["study_date"]
                sdir.mkdir(parents=True, exist_ok=True)
                (sdir / "report.txt").write_text(s["report_text"], encoding="utf-8")
                meta = {k: v for k, v in s.items() if k != "report_text"}
                (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

                # Append to cohort index (include relevance for triage)
                idx.write(json.dumps({
                    "patient_id": s["patient_id"],
                    "study_date": s["study_date"],
                    "timepoint": s["timepoint"],
                    "overall_response": s["recist"]["overall_response"],
                    "baseline_sld_mm": s["recist"]["baseline_sld_mm"],
                    "current_sld_mm": s["recist"]["current_sld_mm"],
                    "nadir_sld_mm": s["recist"]["nadir_sld_mm"],
                    "staging_relevance": s.get("staging_relevance"),
                    "complexity_level": meta.get("complexity_profile", {}).get("level")
                }) + "\n")

    print(f"Generated {args.n_patients} patients at {out}/patients and index at {cohort_labels}")

if __name__ == "__main__":
    main()
