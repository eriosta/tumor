"""
RECIST-aware CT CAP radiology report generator for solid malignancies.

Key features:
- RECIST 1.1 logic:
  * Target lesion selection (≤5 total, ≤2 per organ).
  * Measurable thresholds: non-nodal ≥10 mm longest diameter; lymph node target if short axis ≥15 mm.
  * SLD (Sum of Longest Diameters) calculation (nodes use short axis).
  * CR/PR/SD/PD categorization using baseline→follow-up change and unequivocal new lesions.
- Nodal measurements use short axis; non-nodal use longest diameter.
- Target vs nontarget lesion bookkeeping; nonmeasurable disease simulated (e.g., peritoneal carcinomatosis, blastic bone lesions).
- Organ-structured FINDINGS and concise IMPRESSION with a RECIST summary block.
- Ground-truth JSON includes RECIST details.

Usage (from repo root, with src/ on PYTHONPATH or `pip install -e .`):
  python -m tumor.synth.gen_cap \
    --out_dir data/synth --n 100 --seed 42 \
    --style structured --include_negatives \
    --timepoints 2 --pd_rate 0.25 --pr_rate 0.45

Only stdlib dependencies.
"""

import argparse
import json
import os
import pathlib
import random
from typing import Dict, List, Tuple

# -------------------------- Config & Lexicons --------------------------
HEDGES = ["possible", "probable", "definite"]
MARGINS = ["smooth", "lobulated", "irregular", "spiculated"]
ENHANCEMENT = ["none", "hypoenhancing", "isoenhancing", "hyperenhancing"]

PRIMARY_SITES = ["lung", "colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"]
MET_SITES = ["liver", "adrenal", "bone", "lung", "peritoneum"]

LN_REGIONS = {
    "thoracic": ["right hilar", "left hilar", "subcarinal", "paratracheal"],
    "abdominal": ["porta hepatis", "celiac", "retroperitoneal", "mesenteric"],
    "pelvic": ["external iliac", "internal iliac", "obturator", "inguinal"],
}

ORGAN_HEADINGS = {
    "lungs": ["Lungs", "Pulmonary parenchyma"],
    "mediastinum": ["Mediastinum"],
    "pleura": ["Pleura/Pleural spaces"],
    "aorta": ["Great vessels/Aorta"],
    "liver": ["Liver"],
    "spleen": ["Spleen"],
    "pancreas": ["Pancreas"],
    "adrenals": ["Adrenal glands"],
    "kidneys": ["Kidneys"],
    "gi": ["GI tract/Bowel"],
    "mesentery": ["Mesentery/Omentum"],
    "mes_vessels": ["Mesenteric vessels (SMA/SMV)"],
    "bladder": ["Urinary bladder"],
    "reproductive": ["Reproductive organs"],
    "lymph": ["Lymph nodes"],
    "bones": ["Bones/Osseous structures"],
}

NEG_TEMPLATES = {
    "lungs": [
        "No focal consolidation or suspicious pulmonary nodules. No pneumothorax.",
        "Clear lungs without focal mass. No suspicious nodules identified.",
    ],
    "mediastinum": ["Cardiomediastinal contours within normal limits."],
    "pleura": ["No pleural effusion or pleural thickening."],
    "aorta": ["No thoracic aortic aneurysm or dissection."],
    "liver": ["No focal hepatic lesions. Normal attenuation."],
    "spleen": ["Normal in size and attenuation. No focal splenic lesion."],
    "pancreas": ["Normal pancreatic contour and enhancement. No focal mass."],
    "adrenals": ["Adrenal glands are normal without nodules."],
    "kidneys": ["No hydronephrosis. No enhancing renal mass."],
    "gi": ["No obstructive process. No focal bowel wall mass identified."],
    "mesentery": ["No ascites. No omental caking."],
    "mes_vessels": ["SMA/SMV are patent without thrombosis."],
    "bladder": ["Unremarkable."],
    "reproductive": ["No adnexal mass. Uterus/prostate within expected size for age."],
    "lymph": ["No pathologically enlarged lymph nodes by size criteria."],
    "bones": ["No aggressive osseous lesion. No acute fracture."],
}


def rbool(p: float) -> bool:
    return random.random() < p


def pick(seq):
    return random.choice(seq)


def as_unit(val_mm: int, unit_mm_prob: float) -> str:
    if rbool(unit_mm_prob):
        return f"{val_mm} mm"
    return f"{round(val_mm / 10.0, 1)} cm"


# -------------------------- Lesion factories --------------------------
def gen_primary(primary_site: str) -> Dict:
    size = random.randint(15, 80)  # ≥10 mm threshold for measurability; pick 15–80 mm
    margin = pick(MARGINS)
    enh = pick(["hyperenhancing", "isoenhancing", "hypoenhancing"])
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
    sa = random.randint(8, 30)  # short axis in mm
    return {"type": "ln", "region": region, "station": station, "short_axis_mm": sa, "necrosis": rbool(0.2)}


def gen_met() -> Dict:
    site = pick(MET_SITES)
    size = random.randint(5, 40)
    return {"type": "met", "site": site, "size_mm": size}


# -------------------------- RECIST helpers --------------------------
def measurable_non_nodal(mm: int) -> bool:
    return mm >= 10  # measurable if ≥10 mm (CT) for non-nodal lesions


def measurable_nodal_short_axis(sa_mm: int) -> bool:
    return sa_mm >= 15  # target node if short axis ≥15 mm


def node_is_nontarget(sa_mm: int) -> bool:
    return 10 <= sa_mm < 15  # 10–15 mm SA: nontarget


def recist_targets(primary: Dict, lns: List[Dict], mets: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Select up to 5 targets total, ≤2 per organ.
    Non-nodal lesions: longest diameter.
    Lymph nodes: short axis if ≥15 mm (else nontarget if 10–15 mm).
    """
    by_organ_count: Dict[str, int] = {}
    targets: List[Dict] = []
    nontargets: List[Dict] = []

    # Primary as candidate target if measurable
    if measurable_non_nodal(primary["size_mm"]):
        organ = primary["site"]
        by_organ_count[organ] = by_organ_count.get(organ, 0)
        if by_organ_count[organ] < 2 and len(targets) < 5:
            targets.append(
                {
                    "kind": "primary",
                    "organ": organ,
                    "location": primary["location"],
                    "measure_mm": primary["size_mm"],
                    "rule": "longest",
                }
            )
            by_organ_count[organ] += 1
        else:
            nontargets.append({"kind": "primary", "organ": organ})

    # Mets by organ
    for m in mets:
        organ = m["site"]
        if measurable_non_nodal(m["size_mm"]):
            by_organ_count[organ] = by_organ_count.get(organ, 0)
            if by_organ_count[organ] < 2 and len(targets) < 5:
                targets.append(
                    {
                        "kind": "met",
                        "organ": organ,
                        "site": organ,
                        "measure_mm": m["size_mm"],
                        "rule": "longest",
                    }
                )
                by_organ_count[organ] += 1
            else:
                nontargets.append({"kind": "met", "organ": organ})
        else:
            nontargets.append({"kind": "met", "organ": organ})

    # Nodes (short axis)
    for ln in lns:
        organ = "lymph"
        sa = ln["short_axis_mm"]
        if measurable_nodal_short_axis(sa):
            by_organ_count[organ] = by_organ_count.get(organ, 0)
            if by_organ_count[organ] < 2 and len(targets) < 5:
                targets.append(
                    {"kind": "ln", "organ": organ, "station": ln["station"], "measure_mm": sa, "rule": "short_axis"}
                )
                by_organ_count[organ] += 1
            else:
                nontargets.append({"kind": "ln", "organ": organ})
        elif node_is_nontarget(sa):
            nontargets.append({"kind": "ln", "organ": organ})
        else:
            # <10 mm SA = nonpathologic
            pass

    return targets, nontargets


def sld(targets: List[Dict]) -> int:
    """Sum of Longest Diameters (RECIST 1.1); for nodes, use short axis."""
    return int(round(sum(t["measure_mm"] for t in targets)))


def apply_response_to_targets(baseline_targets: List[Dict], resp: str) -> Tuple[List[Dict], int]:
    """
    Generate follow-up measurements for targets consistent with a RECIST category:
    - PR: ≥30% decrease in SLD
    - PD: ≥20% increase in SLD AND ≥5 mm absolute increase
    - SD: between PR and PD thresholds
    - CR: all non-nodal targets -> 0 mm; nodal -> <10 mm SA
    """
    base_sld = sld(baseline_targets)
    if base_sld == 0:
        return [dict(t) for t in baseline_targets], 0

    if resp == "PR":
        factor = random.uniform(0.55, 0.69)  # ~31–45% decrease
    elif resp == "PD":
        # ensure ≥20% and ≥5 mm absolute increase
        min_factor = max(1.21, (base_sld + 5) / base_sld)
        factor = random.uniform(min_factor, min_factor + 0.2)
    elif resp == "CR":
        factor = 0.0
    else:  # SD
        factor = random.uniform(0.85, 1.15)

    follow: List[Dict] = []
    for t in baseline_targets:
        m = t["measure_mm"]
        if resp == "CR":
            if t["kind"] == "ln":
                new_m = random.randint(4, 9)  # <10 mm SA for nodes
            else:
                new_m = 0
        else:
            noise = random.uniform(0.95, 1.05)
            new_m = max(0, int(round(m * factor * noise)))
            if t["kind"] == "ln" and new_m < 5:
                new_m = random.randint(5, 9)
        t2 = dict(t)
        t2["follow_mm"] = new_m
        follow.append(t2)

    # Align to thresholds more tightly
    follow_sld = sum(t["follow_mm"] for t in follow)
    if resp == "PR" and follow_sld > 0.7 * base_sld:
        delta = int(follow_sld - 0.7 * base_sld) + 1
        for t in follow:
            if delta <= 0:
                break
            cut = min(t["follow_mm"], max(1, delta // len(follow)))
            t["follow_mm"] = max(0, t["follow_mm"] - cut)
            delta -= cut

    if resp == "PD":
        min_needed = int(max(int(1.2 * base_sld) + 5, follow_sld))
        if follow_sld < min_needed:
            add = min_needed - follow_sld
            idx = max(range(len(follow)), key=lambda i: follow[i]["follow_mm"])
            follow[idx]["follow_mm"] += add

    return follow, base_sld


def recist_call(
    base_sld: int,
    follow_sld: int,
    has_new_unequivocal: bool,
    all_targets_disappeared: bool,
    any_node_ge10: bool,
) -> str:
    if all_targets_disappeared and not has_new_unequivocal and not any_node_ge10:
        return "CR"
    if has_new_unequivocal:
        return "PD"
    if base_sld == 0:
        return "SD"
    change = (follow_sld - base_sld) / base_sld
    if change <= -0.30:
        return "PR"
    if change >= 0.20 and (follow_sld - base_sld) >= 5:
        return "PD"
    return "SD"


# -------------------------- Text assembly --------------------------
def organ_heading(key: str) -> str:
    return pick(ORGAN_HEADINGS[key]) + ":"


def sentence_primary(p: Dict, unit_mm_prob: float) -> str:
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


def sentence_ln(ln: Dict, unit_mm_prob: float) -> str:
    sa = as_unit(ln["short_axis_mm"], unit_mm_prob)
    nec = " with central necrosis" if ln.get("necrosis") else ""
    return f"Enlarged {ln['station']} lymph node, short axis {sa}{nec}."


def sentence_met(m: Dict, unit_mm_prob: float) -> str:
    sz = as_unit(m["size_mm"], unit_mm_prob)
    return f"{sz} lesion in the {m['site']}, suspicious for metastasis."


def assemble_findings(
    primary: Dict,
    lns: List[Dict],
    mets: List[Dict],
    unit_mm_prob: float,
    include_negatives: bool,
    comparison: str,
    nonmeasurable_flags: Dict[str, bool],
) -> str:
    sections = []

    # Lungs
    lungs_lines = []
    if primary["site"] == "lung":
        lungs_lines.append(sentence_primary(primary, unit_mm_prob))
    if include_negatives or not lungs_lines:
        lungs_lines.append(pick(NEG_TEMPLATES["lungs"]))
    sections.append(organ_heading("lungs") + " " + " ".join(lungs_lines))

    # Mediastinum (thoracic nodes)
    med_lines = []
    for ln in [x for x in lns if x["region"] == "thoracic"]:
        med_lines.append(sentence_ln(ln, unit_mm_prob))
    if include_negatives or not med_lines:
        med_lines.append(pick(NEG_TEMPLATES["mediastinum"]))
    sections.append(organ_heading("mediastinum") + " " + " ".join(med_lines))

    # Pleura / Aorta
    sections.append(organ_heading("pleura") + " " + pick(NEG_TEMPLATES["pleura"]))
    sections.append(organ_heading("aorta") + " " + pick(NEG_TEMPLATES["aorta"]))

    # Liver (primary & mets)
    liver_lines = []
    if primary["site"] == "liver":
        liver_lines.append(sentence_primary(primary, unit_mm_prob))
    for m in [x for x in mets if x["site"] == "liver"]:
        liver_lines.append(sentence_met(m, unit_mm_prob))
    if include_negatives or not liver_lines:
        liver_lines.append(pick(NEG_TEMPLATES["liver"]))
    sections.append(organ_heading("liver") + " " + " ".join(liver_lines))

    # Spleen
    sections.append(organ_heading("spleen") + " " + pick(NEG_TEMPLATES["spleen"]))

    # Pancreas
    pancreas_lines = []
    if primary["site"] == "pancreas":
        pancreas_lines.append(sentence_primary(primary, unit_mm_prob))
    if include_negatives or not pancreas_lines:
        pancreas_lines.append(pick(NEG_TEMPLATES["pancreas"]))
    sections.append(organ_heading("pancreas") + " " + " ".join(pancreas_lines))

    # Adrenals
    adrenal_lines = []
    for m in [x for x in mets if x["site"] == "adrenal"]:
        adrenal_lines.append(sentence_met(m, unit_mm_prob))
    if include_negatives or not adrenal_lines:
        adrenal_lines.append(pick(NEG_TEMPLATES["adrenals"]))
    sections.append(organ_heading("adrenals") + " " + " ".join(adrenal_lines))

    # Kidneys
    kidney_lines = []
    if primary["site"] == "kidney":
        kidney_lines.append(sentence_primary(primary, unit_mm_prob))
    if include_negatives or not kidney_lines:
        kidney_lines.append(pick(NEG_TEMPLATES["kidneys"]))
    sections.append(organ_heading("kidneys") + " " + " ".join(kidney_lines))

    # GI
    gi_lines = []
    if primary["site"] in ["colon", "stomach"]:
        gi_lines.append(sentence_primary(primary, unit_mm_prob))
    if include_negatives or not gi_lines:
        gi_lines.append(pick(NEG_TEMPLATES["gi"]))
    sections.append(organ_heading("gi") + " " + " ".join(gi_lines))

    # Mesentery / Peritoneum
    mes_lines = []
    for m in [x for x in mets if x["site"] == "peritoneum"]:
        mes_lines.append(sentence_met(m, unit_mm_prob))
    if nonmeasurable_flags.get("peritoneal_carcinomatosis", False):
        mes_lines.append("Diffuse peritoneal thickening with nodularity and ascites, poorly defined—nonmeasurable by RECIST.")
    if include_negatives or not mes_lines:
        mes_lines.append(pick(NEG_TEMPLATES["mesentery"]))
    sections.append(organ_heading("mesentery") + " " + " ".join(mes_lines))

    # Mesenteric vessels
    sections.append(organ_heading("mes_vessels") + " " + pick(NEG_TEMPLATES["mes_vessels"]))

    # Bladder
    sections.append(organ_heading("bladder") + " " + pick(NEG_TEMPLATES["bladder"]))

    # Reproductive
    repro_lines = []
    if primary["site"] in ["ovary", "prostate"]:
        repro_lines.append(sentence_primary(primary, unit_mm_prob))
    if include_negatives or not repro_lines:
        repro_lines.append(pick(NEG_TEMPLATES["reproductive"]))
    sections.append(organ_heading("reproductive") + " " + " ".join(repro_lines))

    # Abd/pelvic nodes
    ln_lines = []
    for ln in [x for x in lns if x["region"] in ("abdominal", "pelvic")]:
        ln_lines.append(sentence_ln(ln, unit_mm_prob))
    if include_negatives or not ln_lines:
        ln_lines.append(pick(NEG_TEMPLATES["lymph"]))
    sections.append(organ_heading("lymph") + " " + " ".join(ln_lines))

    # Bones
    bone_lines = []
    for m in [x for x in mets if x["site"] == "bone"]:
        if rbool(0.5):
            bone_lines.append("Sclerotic osseous metastasis—nonmeasurable by RECIST (blastic).")
        else:
            bone_lines.append(sentence_met(m, unit_mm_prob))
    if include_negatives or not bone_lines:
        bone_lines.append(pick(NEG_TEMPLATES["bones"]))
    sections.append(organ_heading("bones") + " " + " ".join(bone_lines))

    # Comparison
    if comparison:
        sections.append("Comparison: " + comparison)

    return "\n".join(sections)


def assemble_recist_block(base_targets: List[Dict], follow_targets: List[Dict], has_new: bool) -> str:
    lines = []
    base_sld = sld(base_targets)
    follow_sld = sum(t["follow_mm"] for t in follow_targets) if follow_targets else None
    change_pct = None if follow_sld is None or base_sld == 0 else round(100 * (follow_sld - base_sld) / base_sld, 1)

    lines.append("RECIST 1.1 Summary:")
    lines.append(f"- Target lesions (n={len(base_targets)}; ≤2 per organ rule applied).")

    tl = []
    for i, t in enumerate(base_targets, 1):
        name = {"primary": "Primary", "met": "Metastasis", "ln": "Lymph node"}[t["kind"]]
        rule = "short axis" if t["rule"] == "short_axis" else "longest diameter"
        # naive match of follow-up by kind+rule+key
        follow_mm = None
        if follow_targets:
            for ft in follow_targets:
                if ft["kind"] == t["kind"] and ft["rule"] == t["rule"]:
                    key_t = t.get("station") or t.get("site") or t.get("organ")
                    key_f = ft.get("station") or ft.get("site") or ft.get("organ")
                    if key_t == key_f:
                        follow_mm = ft["follow_mm"]
                        break
        if follow_mm is None:
            tl.append(f"  • T{i}: {name} — {t['measure_mm']} mm ({rule}) at baseline.")
        else:
            tl.append(f"  • T{i}: {name} — {t['measure_mm']}→{follow_mm} mm ({rule}).")
    lines.extend(tl)

    lines.append(f"- SLD baseline: {base_sld} mm.")
    if follow_sld is not None:
        sign = "+" if change_pct is not None and change_pct >= 0 else ""
        lines.append(f"- SLD current: {follow_sld} mm ({sign}{change_pct}% change).")
    lines.append(f"- New lesions: {'present' if has_new else 'absent'} (unequivocal).")
    return "\n".join(lines)


def assemble_impression(
    primary: Dict,
    lns: List[Dict],
    mets: List[Dict],
    hedge: str,
    recist_text: str,
    recist_category: str,
) -> str:
    lines = []
    lines.append(
        f"{primary['site'].capitalize()} primary "
        + ("malignancy" if hedge == "definite" else f"neoplasm ({hedge})")
        + f" at {primary['location']} measuring approximately {primary['size_mm']} mm."
    )
    if lns:
        lines.append("Findings concerning for nodal involvement.")
    else:
        lines.append("No pathologically enlarged lymph nodes by size criteria.")
    if mets:
        sites = sorted({m["site"] for m in mets})
        lines.append("Findings compatible with distant metastases involving: " + ", ".join(sites) + ".")
    else:
        lines.append("No definite distant metastases identified.")
    lines.append(recist_text)
    lines.append(f"- RECIST 1.1 overall response category: {recist_category}.")
    return "\n".join(f"- {x}" for x in lines)


# -------------------------- Case synthesis --------------------------
def synth_case(args) -> Tuple[str, Dict]:
    primary_site = random.choice(args.primary_mix)
    primary = gen_primary(primary_site)

    # Nodes
    lns: List[Dict] = []
    if primary_site == "lung" or rbool(0.4):
        if rbool(0.6):
            lns.append(gen_ln("thoracic"))
    if primary_site in ["colon", "pancreas", "kidney", "liver", "ovary", "prostate", "stomach"] or rbool(0.5):
        if rbool(0.6):
            lns.append(gen_ln("abdominal"))
        if rbool(0.4):
            lns.append(gen_ln("pelvic"))

    # Mets
    mets: List[Dict] = []
    if rbool(args.met_rate):
        for _ in range(random.randint(1, 2)):
            mets.append(gen_met())

    # Nonmeasurable disease flags
    nonmeasurable_flags = {"peritoneal_carcinomatosis": rbool(0.15) and primary_site in ["colon", "stomach", "ovary"]}

    # Hedge
    hedge = random.choice(HEDGES if rbool(args.uncertainty_mix) else ["definite"])

    # Comparison sentence
    comparison = ""
    if rbool(0.6):
        comparison = f"Compared to prior {random.randint(1,12):02d}/{random.randint(1,28):02d}/{random.randint(2019,2025)}, primary mass {random.choice(['smaller','stable','larger','new'])}."

    # RECIST baseline targets
    base_targets, nontargets = recist_targets(primary, lns, mets)
    base_sld = sld(base_targets)

    # Plan response if timepoints==2
    resp_plan = None
    if args.timepoints == 2:
        # probabilities: PD / PR / remainder split SD/CR
        rates = [args.pd_rate, args.pr_rate]
        rest = max(0.0, 1.0 - sum(rates))
        sd_rate = rest * 0.95
        cr_rate = rest - sd_rate
        roll = random.random()
        if roll < args.pd_rate:
            resp_plan = "PD"
        elif roll < args.pd_rate + args.pr_rate:
            resp_plan = "PR"
        elif roll < args.pd_rate + args.pr_rate + sd_rate:
            resp_plan = "SD"
        else:
            resp_plan = "CR"

    follow_targets = None
    has_new_unequivocal = False
    if args.timepoints == 2:
        follow_targets, _ = apply_response_to_targets(base_targets, resp_plan or "SD")
        has_new_unequivocal = (resp_plan == "PD" and rbool(0.7)) or rbool(0.05)

    all_disappeared = (
        args.timepoints == 2
        and follow_targets is not None
        and all(t["follow_mm"] == 0 for t in follow_targets if t["kind"] != "ln")
    )
    any_node_ge10 = (
        args.timepoints == 2 and follow_targets is not None and any(t["follow_mm"] >= 10 for t in follow_targets if t["kind"] == "ln")
    )
    follow_sld = sum(t["follow_mm"] for t in follow_targets) if follow_targets else None
    recist_category = (
        recist_call(base_sld, follow_sld or 0, has_new_unequivocal, all_disappeared, any_node_ge10)
        if args.timepoints == 2
        else "Baseline (no category)"
    )

    # Technique
    technique = random.choice(
        [
            "CT chest, abdomen, and pelvis performed with IV contrast. Contiguous ≤5-mm axial images.",
            "Contrast-enhanced CT CAP with portal venous phase abdomen/pelvis; chest imaged in a single post-contrast phase.",
        ]
    )

    header = f"EXAM: CT CAP\nTECHNIQUE: {technique}\nHISTORY: Staging evaluation of known solid malignancy.\n"

    # Findings
    findings = "FINDINGS:\n" + assemble_findings(
        primary, lns, mets, args.unit_mix, args.include_negatives, comparison, nonmeasurable_flags
    )

    # RECIST block
    recist_text = assemble_recist_block(base_targets, follow_targets or [], has_new_unequivocal)

    # Impression
    impression = "IMPRESSION:\n" + assemble_impression(primary, lns, mets, hedge, recist_text, recist_category)

    # Style
    if args.style == "impression_first":
        text = header + "\n" + impression + "\n\n" + findings + "\n"
    elif args.style == "structured":
        text = header + "\n" + findings + "\n\n" + impression + "\n"
    else:
        text = header + "\n" + findings.replace("\n", " ") + "\n\n" + impression + "\n"

    # Ground truth
    gt = {
        "primary_tumor": {
            "organ": primary["site"],
            "location": primary["location"],
            "size_mm": primary["size_mm"],
            "margin": "spiculated"
            if "spiculated" in primary["margin"]
            else primary["margin"].replace("smooth", "regular").replace("lobulated", "irregular"),
            "enhancement": "hyper" if "hyper" in primary["enhancement"] else ("iso" if "iso" in primary["enhancement"] else "hypo"),
            "certainty": hedge,
        },
        "recist": {
            "targets": base_targets,
            "follow_targets": follow_targets,
            "baseline_sld_mm": base_sld,
            "followup_sld_mm": follow_sld,
            "new_lesions_unequivocal": has_new_unequivocal,
            "overall_response": recist_category,
        },
    }
    return text, gt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--style", choices=["narrative", "structured", "impression_first"], default="structured")
    ap.add_argument("--include_negatives", action="store_true")
    ap.add_argument("--met_rate", type=float, default=0.3)
    ap.add_argument("--uncertainty_mix", type=float, default=0.2)
    ap.add_argument("--unit_mix", type=float, default=0.7, help="Probability of using mm, else cm in prose")
    ap.add_argument("--primary_mix", nargs="+", default=PRIMARY_SITES)
    ap.add_argument("--timepoints", type=int, choices=[1, 2], default=2, help="1=baseline only, 2=baseline+follow-up with RECIST call")
    ap.add_argument("--pd_rate", type=float, default=0.25, help="Prior probability to simulate PD when timepoints=2")
    ap.add_argument("--pr_rate", type=float, default=0.45, help="Prior probability to simulate PR when timepoints=2")
    args = ap.parse_args()

    random.seed(args.seed)
    out = pathlib.Path(args.out_dir)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    labels_fp = out / "labels.jsonl"

    labels_fp = out / "labels.jsonl"
    with open(labels_fp, "w", encoding="utf-8") as lab:   # <-- add encoding
        for i in range(args.n):
            text, gt = synth_case(args)
            rp = out / "reports" / f"case_{i:05d}.txt"
            with open(rp, "w", encoding="utf-8") as f:    # <-- add encoding
                f.write(text)
            lab.write(json.dumps({"report_file": str(rp), "label": gt}) + "\n")

    print(f"Generated {args.n} synthetic CAP reports at {out}/reports and labels at {labels_fp}")


if __name__ == "__main__":
    main()
