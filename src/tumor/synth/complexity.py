"""
Complexity controls for synthetic CT CAP oncologic reports.

Reads configs/complexity.json (the one you just created) and exposes helpers to:
- sample artifacts/limitations
- sample incidental findings (organ-aware)
- decide lesion burden counts (targets/non-targets) by level
- optionally inject post-treatment/radiation/surgical changes
- pick uncertainty/hedge phrases
- emit structured negatives breadth by level
- compute a staging_relevance score (to surface what matters)

All randomness uses Python's `random` (seed in your caller).
"""

from __future__ import annotations
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# --------------------- dataclass ---------------------

@dataclass
class ComplexityConfig:
    data: Dict[str, Any]
    level_name: str  # "C0"..."C5"

    # --- convenience getters ---

    @property
    def levels(self) -> Dict[str, Any]:
        return self.data["complexity_levels"]

    @property
    def level(self) -> Dict[str, Any]:
        return self.levels[self.level_name]

    @property
    def global_(self) -> Dict[str, Any]:
        return self.data["global"]

    @property
    def organs(self) -> Dict[str, Any]:
        return self.data["organs"]

    @property
    def recist(self) -> Dict[str, Any]:
        return self.data["recist_helpers"]

    @property
    def weights(self) -> Dict[str, Any]:
        return self.data["staging_relevance_weights"]

    @property
    def artifacts_spec(self) -> Dict[str, Any]:
        return self.global_["artifacts_ct"]

    # --- helpers ---

    def _choice_weighted(self, weights: Dict[str, float]) -> str:
        keys, vals = zip(*weights.items())
        return random.choices(keys, weights=vals, k=1)[0]

    def hedge_phrase_or_none(self) -> Optional[str]:
        """Return a hedge phrase based on level probability, else None."""
        pmap = self.global_.get("hedge_usage_by_level", {})
        use_p = pmap.get(self.level_name, 0.0)
        if random.random() >= use_p:
            return None
        # pick a bucket then a phrase
        buckets = list(self.global_["uncertainty_language"].keys())
        bucket = random.choice(buckets)
        phrases = self.global_["uncertainty_language"][bucket]["phrases"]
        return random.choice(phrases)

    # ----------------- artifacts -----------------

    _severity_rank = {
        "none": 0,
        "partial_volume": 1,
        "motion_mild": 2,
        "beam_hardening": 3,
        "metal_streak": 4,
        "motion_moderate": 5,
    }

    def pick_artifact(self) -> Optional[Dict[str, Any]]:
        """Choose an artifact within severity cap for this level. Returns dict or None."""
        weights_by_level = self.artifacts_spec["weights_by_level"][self.level_name].copy()
        cap = self.level.get("artifact_max_severity", "motion_moderate")
        cap_rank = self._severity_rank.get(cap, 99)

        # filter out disallowed by cap
        allowed = {
            k: v for k, v in weights_by_level.items()
            if self._severity_rank.get(k, 99) <= cap_rank
        }
        if not allowed:
            return None
        key = self._choice_weighted(allowed)
        if key == "none":
            return None

        t = self.artifacts_spec["types"][key]
        return {
            "key": key,
            "impact": int(t.get("impact", 1)),
            "report_phrase": t.get("report_phrase", key.replace("_", " ")),
            "severity_rank": self._severity_rank.get(key, 0),
        }

    # --------------- incidentals ----------------

    def sample_incidentals(self) -> List[Dict[str, str]]:
        """Sample incidental/other findings across organs based on level."""
        lo, hi = self.level.get("incidental_total", [0, 0])
        k = random.randint(lo, hi)
        picks: List[Dict[str, str]] = []
        if k <= 0:
            return picks

        # Build organ -> phrases library from config
        corpus: List[Tuple[str, str]] = []
        for organ, spec in self.organs.items():
            items = []
            if isinstance(spec, dict) and "incidental" in spec:
                items += list(spec["incidental"])
            # accommodate nested (e.g., gi.stomach.incidental)
            if isinstance(spec, dict):
                for subname, subspec in spec.items():
                    if isinstance(subspec, dict) and "incidental" in subspec:
                        for txt in subspec["incidental"]:
                            corpus.append((f"{organ}.{subname}", txt))
            for txt in items:
                corpus.append((organ, txt))

        if not corpus:
            return picks
        for _ in range(k):
            organ, txt = random.choice(corpus)
            picks.append({"organ": organ, "text": txt})
        return picks

    # --------------- structured negatives ----------------

    def sample_structured_negatives(self, max_organs: Optional[int] = None) -> List[Dict[str, str]]:
        """Pick a breadth of 'no X' statements, broader at higher complexity."""
        neg = self.global_.get("structured_negatives", {})
        organs = list(neg.keys())
        # breadth scales with level (C0..C5 -> 2..10 organs)
        breadth_map = {"C0": 2, "C1": 3, "C2": 5, "C3": 7, "C4": 9, "C5": 10}
        breadth = breadth_map.get(self.level_name, 5)
        if max_organs is not None:
            breadth = min(breadth, max_organs)

        chosen_orgs = random.sample(organs, k=min(breadth, len(organs)))
        out: List[Dict[str, str]] = []
        for organ in chosen_orgs:
            phrase = random.choice(neg[organ])
            out.append({"organ": organ, "text": phrase})
        return out

    # --------------- lesion burden ----------------

    def target_nontarget_counts(self) -> Tuple[int, int]:
        t_lo, t_hi = self.data["recist_helpers"]["target_count_range_by_level"][self.level_name]
        nt_lo, nt_hi = self.data["recist_helpers"]["nontarget_count_range_by_level"][self.level_name]
        return random.randint(t_lo, t_hi), random.randint(nt_lo, nt_hi)

    def new_lesion_probability(self) -> float:
        return float(self.data["recist_helpers"]["new_lesion_probability_by_level"][self.level_name])

    # --------------- post-treatment / surgery / RT ----------------

    def sample_post_treatment_effects(self, primary: Optional[str] = None) -> List[str]:
        """Return textual markers of treatment effects as a list of phrases."""
        out: List[str] = []
        if not self.level.get("enable_post_treatment", False):
            return out

        pte = self.data.get("post_treatment_effects", {})
        # radiation (lung + abdomen pelvis generic)
        rad = pte.get("radiation", {})
        for site, spec in rad.items():
            w = spec.get("weight_by_level", {}).get(self.level_name, 0.0)
            if random.random() < w:
                # pick acute or chronic randomly
                bucket = random.choice([k for k in spec.keys() if k in ("acute", "chronic")])
                txt = random.choice(spec[bucket])
                out.append(f"Radiation change: {txt}")

        # surgery
        surg = pte.get("surgery", {})
        w = surg.get("weight_by_level", {}).get(self.level_name, 0.0)
        if random.random() < w:
            # choose organ (prefer primary if available)
            organ_list = [o for o in surg.keys() if o not in ("weight_by_level",)]
            if primary in organ_list and random.random() < 0.7:
                organ = primary
            else:
                organ = random.choice(organ_list)
            txt = random.choice(surg[organ])
            out.append(f"Postsurgical change: {txt}")

        # ablation/embolization
        abl = pte.get("ablation_embolization", {})
        w = abl.get("weight_by_level", {}).get(self.level_name, 0.0)
        if random.random() < w:
            organ_list = [o for o in abl.keys() if o not in ("weight_by_level",)]
            organ = random.choice(organ_list)
            txt = random.choice(abl[organ])
            out.append(f"Post-ablation/embolization change: {txt}")

        return out

    # --------------- impression helpers ----------------

    def limitation_line(self, artifact: Optional[Dict[str, Any]]) -> Optional[str]:
        if not artifact:
            return None
        return artifact["report_phrase"]


# --------------------- API ---------------------

def load_complexity(config_path: Path | str, level: int | str) -> ComplexityConfig:
    p = Path(config_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    # normalize level -> "C#"
    if isinstance(level, int):
        level_name = f"C{level}"
    else:
        level_name = level if level.startswith("C") else f"C{level}"
    if level_name not in data["complexity_levels"]:
        raise ValueError(f"Unknown complexity level: {level_name}")
    return ComplexityConfig(data=data, level_name=level_name)


def compute_staging_relevance(
    cfg: ComplexityConfig,
    recist: Dict[str, Any],
    has_new_measurable_met: bool,
    nodes_crossed_threshold: bool,
    artifact: Optional[Dict[str, Any]],
    used_equivocal_language: bool,
) -> float:
    """
    Weighted score summarizing why a study matters for staging/response.
    """
    w = cfg.weights
    score = 0.0

    if has_new_measurable_met:
        score += w["new_measurable_metastasis"]

    # RECIST PD vs nadir (needs nadir and current)
    cur = recist.get("current_sld_mm")
    nad = recist.get("nadir_sld_mm")
    if recist.get("overall_response") == "PD" and (cur is not None) and (nad is not None) and nad > 0:
        score += w["recist_pd_vs_nadir"]

    if nodes_crossed_threshold:
        score += w["short_axis_node_crossing_threshold"]

    if (cur is not None) and (nad is not None) and nad > 0:
        if (cur - nad) / nad >= 0.20:
            score += w["target_growth_ge20pct_from_nadir"]

    # simple placeholder for unequivocal non-target progression (caller can pass as part of flags)
    # score += w["unequivocal_non_target_progression"]   # if you detect it in your pipeline

    # penalties
    if artifact:
        impact = int(artifact.get("impact", 1))
        if impact >= 3:
            score -= w["artifact_penalty"]["severe"]
        elif impact == 2:
            score -= w["artifact_penalty"]["moderate"]
        else:
            score -= w["artifact_penalty"]["mild"]

    if used_equivocal_language:
        score -= w.get("equivocal_language_penalty", 1.0)

    return round(score, 1)
