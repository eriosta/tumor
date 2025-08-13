#  TO-DO: not generating output

# # src/tumor/synth/gen_onc_notes.py
# """
# Synthetic Oncology Progress Notes Generator

# Generates clinic progress notes for each synthetic patient, aligned to the
# longitudinal CT CAP studies produced by tumor.synth.gen_cohort. Notes include:
# - Oncologic history (primary, dx date, stage at dx)
# - Current and prior lines of therapy
# - Regimen details (components), cycle schedule (C{n}D{d}), and start dates
# - Extractable fields: regimen name(s), components, cycle start dates, line of therapy,
#   and RECIST response at nearest imaging timepoint.

# Outputs (UTF-8):
#   <out_dir>/patients/<PATIENT_ID>/notes/<YYYY-MM-DD>/note.txt
#   <out_dir>/patients/<PATIENT_ID>/notes/<YYYY-MM-DD>/note.json   # structured label
# And a cohort index:
#   <out_dir>/notes_index.jsonl

# Usage:
#   python -m tumor.synth.gen_onc_notes ^
#     --patients_root data/synth_patients/patients ^
#     --out_dir data/synth_patients ^
#     --seed 42 ^
#     --notes_per_tp 1

# If --patients_root is omitted, the script creates standalone patients with
# 3-5 notes each (no imaging linkage).
# """

# import argparse
# import json
# import random
# from datetime import datetime, timedelta
# from pathlib import Path
# from typing import Dict, List, Optional, Tuple

# # --------------------------- regimen library ---------------------------

# Regimen = Dict[str, object]

# REGIMENS: Dict[str, Regimen] = {
#     # GI
#     "FOLFOX": {
#         "components": ["oxaliplatin", "leucovorin", "5-fluorouracil"],
#         "cycle_days": {1: ["all"], 2: ["5-fluorouracil (infusion)"]},  # CxD1: all; CxD2: 5-FU pump day 2
#         "cycle_length_days": 14,
#         "indications": ["colon", "rectal", "stomach"],
#         "synonyms": ["FOLFOX", "oxaliplatin + LV + 5-FU", "mFOLFOX6"],
#     },
#     "FOLFIRI": {
#         "components": ["irinotecan", "leucovorin", "5-fluorouracil"],
#         "cycle_days": {1: ["all"], 2: ["5-fluorouracil (infusion)"]},
#         "cycle_length_days": 14,
#         "indications": ["colon", "rectal"],
#         "synonyms": ["FOLFIRI", "irinotecan + LV + 5-FU"],
#     },
#     "FOLFIRINOX": {
#         "components": ["oxaliplatin", "irinotecan", "leucovorin", "5-fluorouracil"],
#         "cycle_days": {1: ["all"], 2: ["5-fluorouracil (infusion)"]},
#         "cycle_length_days": 14,
#         "indications": ["pancreas"],
#         "synonyms": ["FOLFIRINOX"],
#     },
#     # Lung / Ovary / General
#     "Carboplatin + Paclitaxel": {
#         "components": ["carboplatin", "paclitaxel"],
#         "cycle_days": {1: ["all"]},
#         "cycle_length_days": 21,
#         "indications": ["lung", "ovary"],
#         "synonyms": ["Carbo/Taxol", "carboplatin plus paclitaxel"],
#     },
#     # IO
#     "Pembrolizumab": {
#         "components": ["pembrolizumab"],
#         "cycle_days": {1: ["all"]},
#         "cycle_length_days": 21,  # could also be q6w; keep simple
#         "indications": ["lung", "melanoma", "HNSCC", "stomach"],
#         "synonyms": ["Keytruda", "pembro"],
#     },
#     "Atezolizumab + Bevacizumab": {
#         "components": ["atezolizumab", "bevacizumab"],
#         "cycle_days": {1: ["all"]},
#         "cycle_length_days": 21,
#         "indications": ["liver"],
#         "synonyms": ["Atezo/Bev"],
#     },
# }

# PRIMARY_TO_PLAUSIBLE = {
#     "colon": ["FOLFOX", "FOLFIRI"],
#     "stomach": ["FOLFOX", "Pembrolizumab"],
#     "pancreas": ["FOLFIRINOX"],
#     "liver": ["Atezolizumab + Bevacizumab", "FOLFOX"],
#     "lung": ["Carboplatin + Paclitaxel", "Pembrolizumab"],
#     "ovary": ["Carboplatin + Paclitaxel"],
#     "prostate": ["Carboplatin + Paclitaxel"],  # placeholder
#     "kidney": ["Pembrolizumab"],               # placeholder IO
# }

# SUPPORTIVE_MEDS = [
#     "ondansetron", "dexamethasone", "aprepitant", "loperamide", "oxyCODONE prn",
#     "filgrastim", "pegfilgrastim", "prochlorperazine"
# ]


# # --------------------------- utilities ---------------------------

# def rbool(p: float) -> bool:
#     return random.random() < p

# def iso(d: datetime) -> str:
#     return d.strftime("%Y-%m-%d")

# def add_days(d: datetime, n: int) -> datetime:
#     return d + timedelta(days=n)

# def pick_regimen_for_primary(primary: str) -> str:
#     opts = PRIMARY_TO_PLAUSIBLE.get(primary, list(REGIMENS.keys()))
#     return random.choice(opts)

# def pick_stage() -> str:
#     return random.choice(["II", "III", "IV"])

# def detect_primary_from_patient_dir(pid_dir: Path) -> Optional[str]:
#     """Best-effort: look at first meta.json for clues (not strictly needed)."""
#     # Placeholder: return None (we do not parse report text here)
#     return None

# def load_imaging_timeline(patients_root: Path, pid: str) -> List[Dict]:
#     rows: List[Dict] = []
#     for date_dir in sorted((patients_root / pid).glob("*")):
#         meta = date_dir / "meta.json"
#         if meta.exists():
#             try:
#                 obj = json.loads(meta.read_text(encoding="utf-8"))
#                 rows.append(obj)
#             except Exception:
#                 pass
#     rows.sort(key=lambda x: x.get("study_date", ""))
#     return rows

# def schedule_cycles(regimen_name: str, start: datetime, until: datetime) -> List[Dict]:
#     reg = REGIMENS[regimen_name]
#     cycle_len = int(reg["cycle_length_days"])
#     # generate cycles up to 'until' date
#     cycles = []
#     i = 1
#     d = start
#     while d <= until:
#         per_day = []
#         for day, items in sorted(reg["cycle_days"].items()):
#             day_date = add_days(d, day - 1)
#             per_day.append({
#                 "cycle": i,
#                 "day": day,
#                 "date": iso(day_date),
#                 "administration": "all" if "all" in items else ", ".join(items)
#             })
#         cycles.append({
#             "cycle": i,
#             "start_date": iso(d),
#             "events": per_day
#         })
#         i += 1
#         d = add_days(d, cycle_len)
#     return cycles

# def find_current_cycle_day(cycles: List[Dict], on_date: datetime) -> Optional[Tuple[int,int]]:
#     for c in cycles:
#         for ev in c["events"]:
#             if ev["date"] == iso(on_date):
#                 return (c["cycle"], ev["day"])
#     return None

# def pick_note_date_near(reference: datetime) -> datetime:
#     return reference + timedelta(days=random.randint(-2, 2))

# def summarize_recist_at_date(imaging_rows: List[Dict], on_or_before: datetime) -> Optional[Dict]:
#     cand = [r for r in imaging_rows if r.get("study_date") and r["study_date"] <= iso(on_or_before)]
#     if not cand:
#         return None
#     last = cand[-1]
#     recist = last.get("recist", {})
#     return {
#         "study_date": last.get("study_date"),
#         "overall_response": recist.get("overall_response"),
#         "baseline_sld_mm": recist.get("baseline_sld_mm"),
#         "current_sld_mm": recist.get("current_sld_mm"),
#         "nadir_sld_mm": recist.get("nadir_sld_mm"),
#     }

# def choose_regimen_synonym(regimen_name: str) -> str:
#     syns = REGIMENS[regimen_name].get("synonyms", [regimen_name])
#     return random.choice(syns) if syns else regimen_name

# # --------------------------- note text ---------------------------

# def render_note_text(
#     patient_id: str,
#     encounter_date: datetime,
#     primary_site: str,
#     dx_date: datetime,
#     stage_at_dx: str,
#     lines: List[Dict],
#     current_line: int,
#     current_regimen: str,
#     current_cycle_day: Optional[Tuple[int,int]],
#     recist_summary: Optional[Dict],
# ) -> str:
#     enc = iso(encounter_date)
#     dx_iso = iso(dx_date)
#     syn_name = choose_regimen_synonym(current_regimen)

#     history_lines = []
#     history_lines.append(f"Primary: {primary_site.capitalize()}, diagnosed {dx_iso}. Stage at dx: {stage_at_dx}.")
#     if recist_summary:
#         history_lines.append(
#             f"Most recent imaging {recist_summary['study_date']}: RECIST overall {recist_summary['overall_response']}, "
#             f"SLD baseline {recist_summary.get('baseline_sld_mm','')}, current {recist_summary.get('current_sld_mm','')}, "
#             f"nadir {recist_summary.get('nadir_sld_mm','')}."
#         )
#     history = " ".join(history_lines)

#     ther_hist = []
#     for ln in lines:
#         stop = f", stop {ln['stop_date']}" if ln.get("stop_date") else ""
#         ther_hist.append(
#             f"{ln['line']}L: {ln['regimen']} (start {ln['start_date']}{stop}); components: {', '.join(ln['components'])}."
#         )
#     therapy_history = "\n  - " + "\n  - ".join(ther_hist) if ther_hist else "  - none recorded"

#     cycle_str = ""
#     if current_cycle_day:
#         cycle_str = f"C{current_cycle_day[0]}D{current_cycle_day[1]}"
#     plan_line = f"Continue {syn_name} as tolerated." if not recist_summary or recist_summary.get("overall_response") in (None, "SD", "PR", "CR") else f"Plan to switch therapy pending progression review."

#     supportive = ", ".join(sorted(set(random.sample(SUPPORTIVE_MEDS, k=random.randint(2, 4)))))

#     text = f"""Oncology Clinic Progress Note
# Patient: {patient_id}
# Date: {enc}

# Oncologic History:
#   {history}

# Therapy History:
# {therapy_history}

# Interval History:
#   Reports expected toxicities; eating and drinking adequately. No emergent issues.

# Current Treatment:
#   Line: {current_line}L
#   Regimen: {syn_name}
#   Status: {"on-treatment" if current_cycle_day else "off-cycle"}
#   {("Today is " + cycle_str) if cycle_str else "Not a treatment day today."}
#   Supportive meds: {supportive}

# Assessment:
#   Solid malignancy with ongoing systemic therapy. Performance status ECOG 1.
#   Imaging-based response as above.

# Plan:
#   {plan_line}
#   Continue labs and symptom management; return for next visit per protocol.
# """.rstrip() + "\n"
#     return text

# # --------------------------- core generation ---------------------------

# def synth_patient_notes_for_existing(
#     patients_root: Path,
#     out_root: Path,
#     pid: str,
#     notes_per_tp: int = 1,
# ) -> List[Dict]:
#     """Create notes aligned to imaging timepoints under the patient's folder."""
#     imaging = load_imaging_timeline(patients_root, pid)
#     if not imaging:
#         return []

#     # crude primary guess; otherwise pick common site
#     primary = detect_primary_from_patient_dir(patients_root / pid) or random.choice(
#         ["colon", "lung", "pancreas", "stomach", "liver", "ovary"]
#     )
#     stage = pick_stage()
#     dx_date = datetime.strptime(imaging[0]["study_date"], "%Y-%m-%d") - timedelta(days=random.randint(30, 240))

#     # Start with a 1L regimen around baseline
#     regimen_name = pick_regimen_for_primary(primary)
#     regimen = REGIMENS[regimen_name]
#     start_c1d1 = datetime.strptime(imaging[0]["study_date"], "%Y-%m-%d") - timedelta(days=random.randint(0, 14))
#     end_horizon = datetime.strptime(imaging[-1]["study_date"], "%Y-%m-%d") + timedelta(days=30)
#     cycles = schedule_cycles(regimen_name, start_c1d1, end_horizon)

#     lines: List[Dict] = [{
#         "line": 1,
#         "regimen": regimen_name,
#         "components": regimen["components"],
#         "start_date": iso(start_c1d1),
#         "stop_date": None,
#         "cycles": cycles,
#     }]
#     current_line = 1

#     # If imaging shows PD at any timepoint, switch to next line starting soon after that date
#     for row in imaging[1:]:
#         if (row.get("recist") or {}).get("overall_response") == "PD":
#             # start 2L approximately 7-14 days after PD study date
#             switch_date = datetime.strptime(row["study_date"], "%Y-%m-%d") + timedelta(days=random.randint(7, 14))
#             current_line += 1
#             # close prior line stop_date
#             if lines[-1]["stop_date"] is None:
#                 lines[-1]["stop_date"] = iso(switch_date)
#             # choose a different regimen if possible
#             new_regimen_name = random.choice([r for r in PRIMARY_TO_PLAUSIBLE.get(primary, list(REGIMENS.keys()))
#                                               if r != lines[-1]["regimen"]] or [lines[-1]["regimen"]])
#             new_regimen = REGIMENS[new_regimen_name]
#             new_cycles = schedule_cycles(new_regimen_name, switch_date, end_horizon)
#             lines.append({
#                 "line": current_line,
#                 "regimen": new_regimen_name,
#                 "components": new_regimen["components"],
#                 "start_date": iso(switch_date),
#                 "stop_date": None,
#                 "cycles": new_cycles,
#             })

#     notes_index: List[Dict] = []
#     for tp, row in enumerate(imaging):
#         study_date = datetime.strptime(row["study_date"], "%Y-%m-%d")
#         recist_summary = summarize_recist_at_date(imaging, study_date)
#         # pick which line is active on this date
#         active_line_idx = 0
#         for i, ln in enumerate(lines):
#             start_dt = datetime.strptime(ln["start_date"], "%Y-%m-%d")
#             stop_dt = datetime.max if ln["stop_date"] is None else datetime.strptime(ln["stop_date"], "%Y-%m-%d")
#             if start_dt <= study_date <= stop_dt:
#                 active_line_idx = i
#                 break
#         active = lines[active_line_idx]
#         # find if today is a treatment event (C?D?)
#         cday = find_current_cycle_day(active["cycles"], study_date)

#         for k in range(notes_per_tp):
#             # place note near study date
#             note_date = pick_note_date_near(study_date)
#             # render text
#             text = render_note_text(
#                 patient_id=pid,
#                 encounter_date=note_date,
#                 primary_site=primary,
#                 dx_date=dx_date,
#                 stage_at_dx=stage,
#                 lines=lines,
#                 current_line=active["line"],
#                 current_regimen=active["regimen"],
#                 current_cycle_day=cday if k == 0 else None,  # only first note of tp marked as treatment day
#                 recist_summary=recist_summary
#             )
#             # structured label for easy IE training
#             label = {
#                 "patient_id": pid,
#                 "encounter_date": iso(note_date),
#                 "primary_site": primary,
#                 "stage_at_dx": stage,
#                 "oncologic_history": {
#                     "diagnosis_date": iso(dx_date),
#                 },
#                 "lines": [
#                     {
#                         "line": ln["line"],
#                         "regimen": ln["regimen"],
#                         "components": ln["components"],
#                         "start_date": ln["start_date"],
#                         "stop_date": ln["stop_date"],
#                         "cycles": ln["cycles"],  # includes per-event CxDy with dates
#                     } for ln in lines
#                 ],
#                 "active_line": active["line"],
#                 "active_regimen": active["regimen"],
#                 "active_cycle_day": None if not cday else {"cycle": cday[0], "day": cday[1], "date": iso(study_date)},
#                 "recist": recist_summary,
#             }

#             # write files
#             note_dir = out_root / "patients" / pid / "notes" / iso(note_date)
#             note_dir.mkdir(parents=True, exist_ok=True)
#             (note_dir / "note.txt").write_text(text, encoding="utf-8")
#             (note_dir / "note.json").write_text(json.dumps(label, ensure_ascii=False, indent=2), encoding="utf-8")

#             notes_index.append({
#                 "patient_id": pid,
#                 "encounter_date": iso(note_date),
#                 "line": active["line"],
#                 "regimen": active["regimen"],
#                 "is_treatment_day": bool(cday and k == 0),
#                 "has_imaging_on_or_before": bool(recist_summary),
#                 "overall_response": recist_summary.get("overall_response") if recist_summary else None,
#             })

#     return notes_index


# def synth_patient_notes_standalone(
#     out_root: Path,
#     pid: str,
# ) -> List[Dict]:
#     """If no imaging exists, generate 3-5 notes and a simple 1L course."""
#     primary = random.choice(["colon", "lung", "pancreas", "stomach"])
#     stage = pick_stage()
#     today = datetime(2024, random.randint(1, 12), random.randint(1, 28))
#     dx_date = today - timedelta(days=random.randint(60, 300))
#     regimen_name = pick_regimen_for_primary(primary)
#     start_c1d1 = today - timedelta(days=random.randint(0, 21))
#     cycles = schedule_cycles(regimen_name, start_c1d1, today + timedelta(days=120))

#     lines = [{
#         "line": 1,
#         "regimen": regimen_name,
#         "components": REGIMENS[regimen_name]["components"],
#         "start_date": iso(start_c1d1),
#         "stop_date": None,
#         "cycles": cycles,
#     }]

#     notes_index: List[Dict] = []
#     n_notes = random.randint(3, 5)
#     curr = today
#     for i in range(n_notes):
#         note_date = curr + timedelta(days=i * 21)
#         cday = find_current_cycle_day(cycles, note_date)
#         text = render_note_text(
#             patient_id=pid,
#             encounter_date=note_date,
#             primary_site=primary,
#             dx_date=dx_date,
#             stage_at_dx=stage,
#             lines=lines,
#             current_line=1,
#             current_regimen=regimen_name,
#             current_cycle_day=cday,
#             recist_summary=None
#         )
#         label = {
#             "patient_id": pid,
#             "encounter_date": iso(note_date),
#             "primary_site": primary,
#             "stage_at_dx": stage,
#             "oncologic_history": {"diagnosis_date": iso(dx_date)},
#             "lines": lines,
#             "active_line": 1,
#             "active_regimen": regimen_name,
#             "active_cycle_day": None if not cday else {"cycle": cday[0], "day": cday[1], "date": iso(note_date)},
#             "recist": None,
#         }
#         note_dir = out_root / "patients" / pid / "notes" / iso(note_date)
#         note_dir.mkdir(parents=True, exist_ok=True)
#         (note_dir / "note.txt").write_text(text, encoding="utf-8")
#         (note_dir / "note.json").write_text(json.dumps(label, ensure_ascii=False, indent=2), encoding="utf-8")

#         notes_index.append({
#             "patient_id": pid,
#             "encounter_date": iso(note_date),
#             "line": 1,
#             "regimen": regimen_name,
#             "is_treatment_day": bool(cday),
#             "has_imaging_on_or_before": False,
#             "overall_response": None,
#         })
#     return notes_index

# # --------------------------- CLI ---------------------------

# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--patients_root", type=str, default="", help="Path to patients dir with imaging meta.json (e.g., data/synth_patients/patients)")
#     ap.add_argument("--out_dir", type=str, required=True, help="Root where notes will be written (usually same parent as patients_root)")
#     ap.add_argument("--seed", type=int, default=0)
#     ap.add_argument("--notes_per_tp", type=int, default=1, help="Notes per imaging timepoint (e.g., clinic + infusion)")
#     args = ap.parse_args()

#     random.seed(args.seed)
#     out_root = Path(args.out_dir)
#     out_root.mkdir(parents=True, exist_ok=True)
#     notes_index_path = out_root / "notes_index.jsonl"

#     all_rows: List[Dict] = []

#     if args.patients_root:
#         patients_root = Path(args.patients_root)
#         pids = sorted([p.name for p in patients_root.iterdir() if p.is_dir()])
#         for pid in pids:
#             rows = synth_patient_notes_for_existing(patients_root, out_root, pid, notes_per_tp=args.notes_per_tp)
#             all_rows.extend(rows)
#     else:
#         # standalone mode: synthesize a few patients without imaging
#         for i in range(10):
#             pid = f"PID{i:06d}"
#             rows = synth_patient_notes_standalone(out_root, pid)
#             all_rows.extend(rows)

#     with notes_index_path.open("w", encoding="utf-8") as idx:
#         for r in all_rows:
#             idx.write(json.dumps(r) + "\n")

#     print(f"Generated notes for {len(set(r['patient_id'] for r in all_rows))} patients. Index at {notes_index_path}")

# if __name__ == "__main__":
#     main()
