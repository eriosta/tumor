
"""
Synthetic CT CAP radiology report generator (solid malignancy) with realistic organ-structured FINDINGS
and an IMPRESSION. Produces free-text reports plus ground-truth JSON.
Usage:
  python -m tumor.synth.gen_cap --out_dir data/synth --n 500 --seed 42     --styles narrative structured impression_first     --primary_mix lung colon pancreas kidney liver ovary prostate stomach     --met_rate 0.3 --uncertainty_mix 0.25 --unit_mix 0.7
"""

import argparse, os, json, random, uuid, pathlib
from typing import List, Dict, Tuple

UNITS = ["mm","cm"]
HEDGES = ["possible","probable","definite"]
MARGINS = ["smooth", "lobulated", "irregular", "spiculated"]
ENHANCEMENT = ["none", "hypoenhancing", "isoenhancing", "hyperenhancing"]

ORGAN_HEADINGS = {
    "lungs": ["Lungs", "Lung parenchyma", "Pulmonary"],
    "mediastinum": ["Mediastinum"],
    "pleura": ["Pleura/Pleural spaces", "Pleura"],
    "aorta": ["Great vessels/Aorta", "Aorta and great vessels"],
    "liver": ["Liver", "Hepatic"],
    "spleen": ["Spleen"],
    "pancreas": ["Pancreas"],
    "adrenals": ["Adrenals", "Adrenal glands"],
    "kidneys": ["Kidneys", "Renal"],
    "gi": ["GI tract", "Bowel"],
    "mesentery": ["Mesentery/Omentum", "Mesentery"],
    "mes_vessels": ["Mesenteric vessels", "SMA/SMV"],
    "bladder": ["Bladder", "Urinary bladder"],
    "reproductive": ["Reproductive organs", "Pelvic organs"],
    "lymph": ["Lymph nodes", "Nodal stations"],
    "bones": ["Bones", "Osseous structures", "Skeleton"]
}

LN_REGIONS = {
    "thoracic": ["right hilar", "left hilar", "subcarinal", "paratracheal"],
    "abdominal": ["porta hepatis", "celiac", "retroperitoneal", "mesenteric"],
    "pelvic": ["external iliac", "internal iliac", "obturator", "inguinal"]
}

MET_SITES = ["liver", "adrenal", "bone", "lung", "peritoneum"]
PRIMARY_SITES = ["lung", "colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"]

NEG_TEMPLATES = {
    "lungs": [
        "No focal consolidation or suspicious pulmonary nodules. No pneumothorax.",
        "Clear lungs without focal mass. No suspicious nodules identified."
    ],
    "mediastinum": ["Cardiomediastinal contours within normal limits."],
    "pleura": ["No pleural effusion or pleural thickening."],
    "aorta": ["No thoracic aortic aneurysm or dissection."],
    "liver": ["No focal hepatic lesions. Normal attenuation."],
    "spleen": ["Normal in size and attenuation. No focal splenic lesion."],
    "pancreas": ["Normal pancreatic contour and enhancement. No focal mass."],
    "adrenals": ["Adrenal glands are normal without nodules."],
    "kidneys": ["No hydronephrosis. No enhancing renal mass."],
    "gi": ["No obstructive bowel process. No focal bowel wall mass identified."],
    "mesentery": ["No ascites. No omental caking."],
    "mes_vessels": ["SMA/SMV patent without thrombosis."],
    "bladder": ["Urinary bladder unremarkable."],
    "reproductive": ["No adnexal mass. Uterus/prostate within expected size for age."],
    "lymph": ["No pathologically enlarged lymph nodes by size criteria."],
    "bones": ["No aggressive osseous lesion. No acute fracture."]
}

def rbool(p: float) -> bool:
    return random.random() < p

def pick(seq):
    return random.choice(seq)

def as_unit(val_mm: int, unit_mm_prob: float) -> str:
    if rbool(unit_mm_prob):
        return f"{val_mm} mm"
    return f"{round(val_mm/10.0, 1)} cm"

def gen_primary(primary_site: str) -> Dict:
    size = random.randint(15, 80)
    margin = pick(["smooth","lobulated","irregular","spiculated"])
    enh = pick(["hyperenhancing","isoenhancing","hypoenhancing"])
    if primary_site == "lung":
        location = f"{pick(['right','left'])} {pick(['upper','middle','lower'])} lobe"
    elif primary_site == "colon":
        location = f"{pick(['ascending','transverse','descending','sigmoid'])} colon"
    elif primary_site == "pancreas":
        location = f"{pick(['head','neck','body','tail'])} of the pancreas"
    elif primary_site == "kidney":
        location = f"{pick(['right','left'])} kidney, {pick(['upper pole','interpolar','lower pole'])}"
    elif primary_site == "liver":
        location = f"segment {pick(list('2345678'))} of the liver"
    elif primary_site == "ovary":
        location = f"{pick(['right','left'])} adnexa"
    elif primary_site == "prostate":
        location = "prostate gland, peripheral zone"
    elif primary_site == "stomach":
        location = f"{pick(['antrum','body','fundus','lesser curvature','greater curvature'])} of the stomach"
    else:
        location = "unspecified"
    return {"site": primary_site, "location": location, "size_mm": size, "margin": margin, "enhancement": enh}

def gen_ln(region: str) -> Dict:
    station = pick(LN_REGIONS[region])
    sa = random.randint(8, 30)
    return {"region": region, "station": station, "short_axis_mm": sa, "necrosis": rbool(0.2)}

def gen_met() -> Dict:
    site = pick(MET_SITES)
    size = random.randint(5, 40)
    return {"site": site, "size_mm": size}

def stage_bucket(has_ln: bool, has_met: bool) -> str:
    if has_met: return "metastatic"
    if has_ln: return "nodal"
    return "localized"

def organ_heading(key: str) -> str:
    return pick(ORGAN_HEADINGS[key]) + ":"

def positive_sentence_for_primary(p: Dict, unit_mm_prob: float) -> str:
    sz = as_unit(p["size_mm"], unit_mm_prob)
    site = p["site"]
    if site == "lung":
        return f"{sz} {p['margin']} mass in the {p['location']} ({p['enhancement']})."
    if site == "colon":
        return f"{sz} {p['margin']} mass involving the {p['location']} with focal wall thickening ({p['enhancement']})."
    if site == "pancreas":
        return f"{sz} {p['margin']} pancreatic mass in the {p['location']} ({p['enhancement']})."
    if site == "kidney":
        return f"{sz} {p['margin']} enhancing renal mass in the {p['location']}."
    if site == "liver":
        return f"{sz} {p['margin']} hepatic mass in {p['location']} ({p['enhancement']})."
    if site == "ovary":
        return f"{sz} complex adnexal mass in the {p['location']}."
    if site == "prostate":
        return f"{sz} {p['margin']} mass within the {p['location']}."
    if site == "stomach":
        return f"{sz} {p['margin']} gastric mass at the {p['location']} ({p['enhancement']})."
    return f"{sz} mass at {p['location']}."

def positive_sentence_for_ln(ln: Dict, unit_mm_prob: float) -> str:
    sa = as_unit(ln["short_axis_mm"], unit_mm_prob)
    nec = " with central necrosis" if ln["necrosis"] else ""
    return f"Enlarged {ln['station']} lymph node, short axis {sa}{nec}."

def positive_sentence_for_met(m: Dict, unit_mm_prob: float) -> str:
    sz = as_unit(m["size_mm"], unit_mm_prob)
    return f"{sz} lesion in the {m['site']}, suspicious for metastasis."

def assemble_findings(primary: Dict, lns, mets, unit_mm_prob: float, include_negatives: bool, comparison: str) -> str:
    sections = []
    # Lungs
    lungs_lines = []
    if primary["site"] == "lung":
        lungs_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    if include_negatives or not lungs_lines:
        lungs_lines.append(random.choice(["No focal consolidation or suspicious pulmonary nodules. No pneumothorax.",
                                          "Clear lungs without focal mass. No suspicious nodules identified."]))
    sections.append(organ_heading("lungs") + " " + " ".join(lungs_lines))
    # Mediastinum
    med_lines = []
    thor_ln = [ln for ln in lns if ln["region"]=="thoracic"]
    for ln in thor_ln:
        med_lines.append(positive_sentence_for_ln(ln, unit_mm_prob))
    if include_negatives or not med_lines:
        med_lines.append("Cardiomediastinal contours within normal limits.")
    sections.append(organ_heading("mediastinum") + " " + " ".join(med_lines))
    # Pleura
    sections.append(organ_heading("pleura") + " No pleural effusion or pleural thickening.")
    # Aorta
    sections.append(organ_heading("aorta") + " No thoracic aortic aneurysm or dissection.")
    # Liver
    liver_lines = []
    if primary["site"] == "liver":
        liver_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    for m in [m for m in mets if m["site"]=="liver"]:
        liver_lines.append(positive_sentence_for_met(m, unit_mm_prob))
    if include_negatives or not liver_lines:
        liver_lines.append("No focal hepatic lesions. Normal attenuation.")
    sections.append(organ_heading("liver") + " " + " ".join(liver_lines))
    # Spleen
    sections.append(organ_heading("spleen") + " Normal in size and attenuation. No focal splenic lesion.")
    # Pancreas
    pancreas_lines = []
    if primary["site"] == "pancreas":
        pancreas_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    if include_negatives or not pancreas_lines:
        pancreas_lines.append("Normal pancreatic contour and enhancement. No focal mass.")
    sections.append(organ_heading("pancreas") + " " + " ".join(pancreas_lines))
    # Adrenals
    adrenal_lines = []
    for m in [m for m in mets if m["site"]=="adrenal"]:
        adrenal_lines.append(positive_sentence_for_met(m, unit_mm_prob))
    if include_negatives or not adrenal_lines:
        adrenal_lines.append("Adrenal glands are normal without nodules.")
    sections.append(organ_heading("adrenals") + " " + " ".join(adrenal_lines))
    # Kidneys
    kidney_lines = []
    if primary["site"] == "kidney":
        kidney_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    if include_negatives or not kidney_lines:
        kidney_lines.append("No hydronephrosis. No enhancing renal mass.")
    sections.append(organ_heading("kidneys") + " " + " ".join(kidney_lines))
    # GI
    gi_lines = []
    if primary["site"] in ["colon","stomach"]:
        gi_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    if include_negatives or not gi_lines:
        gi_lines.append("No obstructive bowel process. No focal bowel wall mass identified.")
    sections.append(organ_heading("gi") + " " + " ".join(gi_lines))
    # Mesentery/Omentum
    mes_lines = []
    for m in [m for m in mets if m["site"]=="peritoneum"]:
        mes_lines.append(positive_sentence_for_met(m, unit_mm_prob))
    if include_negatives or not mes_lines:
        mes_lines.append("No ascites. No omental caking.")
    sections.append(organ_heading("mesentery") + " " + " ".join(mes_lines))
    # Mesenteric vessels
    sections.append(organ_heading("mes_vessels") + " SMA/SMV patent without thrombosis.")
    # Bladder
    sections.append(organ_heading("bladder") + " Urinary bladder unremarkable.")
    # Reproductive
    repro_lines = []
    if primary["site"] in ["ovary","prostate"]:
        repro_lines.append(positive_sentence_for_primary(primary, unit_mm_prob))
    if include_negatives or not repro_lines:
        repro_lines.append("No adnexal mass. Uterus/prostate within expected size for age.")
    sections.append(organ_heading("reproductive") + " " + " ".join(repro_lines))
    # Lymph nodes
    abdpel_ln = [ln for ln in lns if ln["region"] in ("abdominal","pelvic")]
    ln_lines = []
    for ln in abdpel_ln:
        ln_lines.append(positive_sentence_for_ln(ln, unit_mm_prob))
    if include_negatives or not ln_lines:
        ln_lines.append("No pathologically enlarged lymph nodes by size criteria.")
    sections.append(organ_heading("lymph") + " " + " ".join(ln_lines))
    # Bones
    bone_lines = []
    for m in [m for m in mets if m["site"]=="bone"]:
        bone_lines.append(positive_sentence_for_met(m, unit_mm_prob))
    if include_negatives or not bone_lines:
        bone_lines.append("No aggressive osseous lesion. No acute fracture.")
    sections.append(organ_heading("bones") + " " + " ".join(bone_lines))
    # Comparison
    if comparison:
        sections.append("Comparison: " + comparison)
    return "\\n".join(sections)

def assemble_impression(primary, lns, mets, hedge):
    lines = []
    lines.append(f"{primary['site'].capitalize()} primary " + ("malignancy" if hedge=='definite' else f"neoplasm ({hedge})") + f" at {primary['location']} measuring approximately {primary['size_mm']} mm.")
    lines.append("Findings concerning for nodal involvement." if lns else "No pathologically enlarged lymph nodes identified by size criteria.")
    if mets:
        sites = sorted({m['site'] for m in mets})
        lines.append("Findings compatible with distant metastases involving: " + ", ".join(sites) + ".")
    else:
        lines.append("No definite distant metastases identified.")
    lines.append("Recommend correlation with clinical staging and multidisciplinary discussion.")
    return "\\n".join("- " + x for x in lines)

def synth_case(args):
    primary_site = random.choice(args.primary_mix)
    primary = gen_primary(primary_site)
    lns = []
    if primary_site == "lung" or rbool(0.4):
        if rbool(0.6): lns.append(gen_ln("thoracic"))
    if primary_site in ["colon","pancreas","kidney","liver","ovary","prostate","stomach"] or rbool(0.5):
        if rbool(0.6): lns.append(gen_ln("abdominal"))
        if rbool(0.4): lns.append(gen_ln("pelvic"))
    mets = []
    if rbool(args.met_rate):
        for _ in range(random.randint(1,2)):
            mets.append(gen_met())
    hedge = random.choice(HEDGES if rbool(args.uncertainty_mix) else ["definite"])
    comparison = ""
    if rbool(0.6):
        comparison = f"Compared to prior {random.randint(1,12):02d}/{random.randint(1,28):02d}/{random.randint(2019,2025)}, primary mass {random.choice(['smaller','stable','larger','new'])}."
    technique = random.choice(["CT chest, abdomen, and pelvis with IV contrast.",
                               "Contrast-enhanced CT of the chest/abdomen/pelvis (CAP)."])
    header = f"EXAM: CT CAP\\nTECHNIQUE: {technique}\\nHISTORY: Staging evaluation of known solid malignancy.\\n"
    findings = "FINDINGS:\\n" + assemble_findings(primary, lns, mets, args.unit_mix, args.include_negatives, comparison)
    impression = "IMPRESSION:\\n" + assemble_impression(primary, lns, mets, hedge)
    if args.style == "impression_first":
        text = header + "\\n" + impression + "\\n\\n" + findings + "\\n"
    elif args.style == "structured":
        text = header + "\\n" + findings + "\\n\\n" + impression + "\\n"
    else:
        text = header + "\\n" + findings.replace("\\n", " ") + "\\n\\n" + impression + "\\n"
    gt = {
        "primary_tumor": {
            "organ": primary["site"],
            "location": primary["location"],
            "size_mm": primary["size_mm"],
            "margin": "spiculated" if "spiculated" in primary["margin"] else primary["margin"].replace("smooth","regular").replace("lobulated","irregular"),
            "enhancement": "hyper" if "hyper" in primary["enhancement"] else ("iso" if "iso" in primary["enhancement"] else "hypo"),
            "certainty": hedge
        },
        "lymph_nodes": [{"region": ln["region"], "station": ln["station"], "short_axis_mm": ln["short_axis_mm"], "necrosis": ln["necrosis"]} for ln in lns],
        "metastases": [{"site": m["site"], "size_mm": m["size_mm"]} for m in mets],
        "staging_suspected": stage_bucket(bool(lns), bool(mets)),
        "comparison_present": bool(comparison)
    }
    return text, gt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--style", choices=["narrative","structured","impression_first"], default="structured")
    ap.add_argument("--include_negatives", action="store_true")
    ap.add_argument("--met_rate", type=float, default=0.3)
    ap.add_argument("--uncertainty_mix", type=float, default=0.2)
    ap.add_argument("--unit_mix", type=float, default=0.7)
    ap.add_argument("--primary_mix", nargs="+", default=["lung","colon","pancreas","kidney","liver","ovary","prostate","stomach"])
    args = ap.parse_args()
    random.seed(args.seed)
    out = pathlib.Path(args.out_dir)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    labels_fp = out / "labels.jsonl"
    with open(labels_fp, "w") as lab:
        for i in range(args.n):
            text, gt = synth_case(args)
            rp = out / "reports" / f"case_{i:05d}.txt"
            with open(rp, "w") as f:
                f.write(text)
            lab.write(json.dumps({"report_file": str(rp), "label": gt}) + "\\n")
    print(f"Generated {args.n} synthetic CAP reports at {out}/reports and labels at {labels_fp}")

if __name__ == "__main__":
    main()
