"""Deterministic challenges for A7, and validation of the review and insight drafts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import registry
from .state import read_artifact

VERDICTS = ("supported", "partially_supported", "not_supported", "inconclusive")
STRENGTHS = ("strong", "moderate", "weak", "null")
CONFIDENCE = ("high", "medium", "low")
CAUSAL = re.compile(r"\b(cause[sd]?|causing|drives?|driving|driven by|impacts?|impacted|effect of|leads? to|"
                    r"because of|results? in|boosts?|makes? .{0,20}(increase|decrease))\b", re.I)


def load_results(run_dir: Path) -> dict:
    out = {}
    for p in (run_dir / "results").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        out[r["label"]] = r
    return out


def challenges(run_dir: Path) -> dict:
    scope = read_artifact(run_dir, "approved_scope.json")
    results = load_results(run_dir)
    alpha, min_n = float(scope.get("alpha", .05)), int(scope.get("min_n", 30))
    q = {(r["result"], r["label"]): r["q"] for r in results.get("multiple-testing", {}).get("q_values", [])}
    ent = scope.get("entity_column")
    panel = set(registry.panel_tools())
    per_result = []
    for label, r in sorted(results.items()):
        if label == "multiple-testing":
            continue
        items = list(r.get("flags", []))
        if ent and r["tool"] not in panel and r.get("findings"):
            items.append(f"PANEL POOLED: pools all {ent} rows; CIs treat them as independent and mix within- and "
                         f"between-{ent} patterns. Check the panel results before leading with this")
        if r.get("error"):
            items.append(f"ERROR: {r['error']}")
        rows = []
        for f in r.get("findings", []):
            issues = []
            qv = q.get((label, f["label"]))
            if f.get("n") is not None and f["n"] < min_n:
                issues.append(f"n={f['n']} < min_n")
            if f.get("ci_low") is not None and f.get("ci_high") is not None and f["ci_low"] < 0 < f["ci_high"] \
                    and (f["metric"].endswith("_r") or f["metric"].startswith("spearman_r")):
                issues.append("CI includes 0")
            if qv is not None and qv >= alpha:
                issues.append(f"q={qv:.3g} not significant after FDR")
            if f.get("estimate") is not None and abs(f["estimate"]) < .1 and f["metric"] in (
                    "spearman_r", "eta", "cramers_v", "partial_spearman_r", "spearman_r_within_segments",
                    "spearman_r_pooled", "spearman_r_within_entity", "spearman_r_between_entity"):
                issues.append("negligible size (|est| < 0.1)")
            rows.append({"finding": f["label"], "metric": f["metric"], "estimate": f.get("estimate"),
                         "ci": [f.get("ci_low"), f.get("ci_high")], "n": f.get("n"), "q": qv, "issues": issues})
        per_result.append({"result": label, "tool": r["tool"], "hypothesis": r.get("hypothesis"),
                           "followup": r.get("followup_reason"), "summary": r.get("summary"), "flags": items,
                           "findings": rows})
    by_h = {}
    for h in scope["hypotheses"]:
        by_h[h["id"]] = {"statement": h["statement"], "support_criteria": h["support_criteria"],
                         "results": [x["result"] for x in per_result if x["hypothesis"] == h["id"]]}
    prompts = ["Does the pooled result survive within segments? Lead with within-segment when they differ.",
               "Is a weak correlation hiding a curve (nonlinearity flags)?",
               "Do overlapping drivers tell one story or two (collinear pairs)?",
               "Is anything that looks too good actually leakage or a derived column?",
               "Which findings fail FDR, and are any insights resting only on those?"]
    if ent:
        prompts.insert(0, f"Panel data ({ent}): lead with within-{ent} estimates (the same {ent} over time), report "
                          f"between-{ent} separately (n = entities), and do not headline a pooled estimate the panel "
                          "tools contradict (PANEL SPLIT flags).")
    return {"results": per_result, "hypotheses": by_h, "prompts": prompts}


def _check_evidence(evidence: list, results: dict, where: str) -> list[str]:
    errs = []
    if not evidence:
        errs.append(f"{where}: needs at least one evidence item")
    for ev in evidence:
        r = results.get(ev.get("result"))
        if r is None:
            errs.append(f"{where}: unknown result '{ev.get('result')}'")
        elif ev.get("finding") and ev["finding"] not in {f["label"] for f in r.get("findings", [])}:
            errs.append(f"{where}: result '{ev['result']}' has no finding '{ev['finding']}'")
    return errs


def _causal(text: str, where: str) -> list[str]:
    m = CAUSAL.search(text or "")
    return [f"{where}: causal wording '{m.group(0)}'; describe an association instead"] if m else []


def validate_review(draft: dict, run_dir: Path) -> list[str]:
    scope = read_artifact(run_dir, "approved_scope.json")
    results = load_results(run_dir)
    errs = []
    ids = {h["id"] for h in scope["hypotheses"]}
    seen = set()
    for v in draft.get("hypothesis_verdicts", []):
        where = f"verdict {v.get('id')}"
        seen.add(v.get("id"))
        if v.get("id") not in ids:
            errs.append(f"{where}: not a hypothesis in the approved scope")
        if v.get("verdict") not in VERDICTS:
            errs.append(f"{where}: verdict must be one of {VERDICTS}")
        if not v.get("reasoning"):
            errs.append(f"{where}: needs reasoning")
        errs += _check_evidence(v.get("evidence", []), results, where) + _causal(v.get("reasoning"), where)
    if ids - seen:
        errs.append(f"missing verdicts for {sorted(ids - seen)}")
    for i, c in enumerate(draft.get("challenges", []), 1):
        if not c.get("issue") or not c.get("resolution"):
            errs.append(f"challenge {i}: needs 'issue' and 'resolution'")
    for i, rr in enumerate(draft.get("rerun_requests", []), 1):
        if not rr.get("tool") or not rr.get("reason"):
            errs.append(f"rerun {i}: needs 'tool' and 'reason'")
    return errs


def validate_insights(draft: dict, run_dir: Path) -> list[str]:
    results = load_results(run_dir)
    errs = []
    if not draft.get("headline_summary"):
        errs.append("needs 'headline_summary'")
    errs += _causal(draft.get("headline_summary"), "headline_summary")
    items = draft.get("insights", [])
    if not 2 <= len(items) <= 7:
        errs.append("give 2 to 7 insights; pick the ones that matter for the decision")
    for ins in items:
        where = f"insight {ins.get('id')}"
        for key in ("id", "title", "statement", "strength", "confidence"):
            if not ins.get(key):
                errs.append(f"{where}: missing '{key}'")
        if ins.get("strength") not in STRENGTHS:
            errs.append(f"{where}: strength must be one of {STRENGTHS}")
        if ins.get("confidence") not in CONFIDENCE:
            errs.append(f"{where}: confidence must be one of {CONFIDENCE}")
        errs += _check_evidence(ins.get("evidence", []), results, where)
        if any(not ev.get("finding") for ev in ins.get("evidence", [])):
            errs.append(f"{where}: every evidence item needs a 'finding' label so the report can quote n and CI")
        for key in ("title", "statement"):
            errs += _causal(ins.get(key), f"{where} {key}")
    for key in ("limitations", "next_steps"):
        if not draft.get(key):
            errs.append(f"needs '{key}'")
    return errs
