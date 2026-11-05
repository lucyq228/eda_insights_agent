"""Deterministic challenges and validation for review and insight drafts."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import registry
from .state import read_artifact, sha

VERDICTS = ("supported", "partially_supported", "not_supported", "inconclusive", "not_evaluated")
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
    q = {(r["result"], r["label"]): r["q"] for r in (results.get("multiple-testing-adjustment") or results.get("multiple-testing") or {}).get("q_values", [])}
    ent = scope.get("entity_column")
    panel = set(registry.panel_tools())
    waiver_artifact = read_artifact(run_dir, "step_waivers.json") or {}
    waivers = ({w["step_id"]: w for w in waiver_artifact.get("waivers", [])}
               if (waiver_artifact.get("upstream") or {}).get("sha256") == sha(run_dir / "approved_scope.json") else {})
    evidence_refs = {}
    for result in results.values():
        for finding in result.get("findings", []):
            if finding.get("test_id"):
                evidence_refs.setdefault(finding["test_id"], []).append(result["label"])
    per_result = []
    for label, r in sorted(results.items()):
        if label in ("multiple-testing-adjustment", "multiple-testing"):
            continue
        items = list(r.get("flags", []))
        if ent and registry.canonical(r["tool"]) not in panel and r.get("findings"):
            items.append(f"PANEL POOLED: pools all {ent} rows; CIs treat them as independent and mix within- and "
                         f"between-{ent} patterns. Check the panel results before leading with this")
        if r.get("error"):
            items.append(f"ERROR: {r['error']}")
        rows = []
        for f in r.get("findings", []):
            issues = []
            reused = sorted(set(evidence_refs.get(f.get("test_id"), [])))
            if len(reused) > 1:
                issues.append("REUSED TEST: " + ", ".join(reused) + "; one test, not independent confirmation")
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
                         "ci": [f.get("ci_low"), f.get("ci_high")], "n": f.get("n"), "q": qv, "test_id": f.get("test_id"), "issues": issues})
        descriptive = bool(r.get("findings")) and all(f.get("evidence_type") == "descriptive" for f in r["findings"])
        finding_count = len(rows)
        if descriptive:
            rows = rows[:30]
        per_result.append({"finding_count": finding_count, "preview_truncated": descriptive and finding_count > 30,
                           "evidence_access": "Use read_evidence.py for bounded/sorted aggregate table pages",
                           "result": label, "tool": r["tool"], "hypothesis": r.get("hypothesis"),
                           "followup": r.get("followup_reason"), "summary": r.get("summary"), "flags": items,
                           "findings": rows})
    by_h = {}
    for h in scope["hypotheses"]:
        by_h[h["id"]] = {"statement": h["statement"], "support_criteria": h["support_criteria"],
                         "rationale": h["rationale"], "followup_when": h.get("followup_when"),
                         "results": [x["result"] for x in per_result if x["hypothesis"] == h["id"]],
                         "skipped_steps": [{"step_id": s["step_id"], "reason": waivers[s["step_id"]]["reason"]}
                                           for s in registry.plan_steps(scope)
                                           if s["hypothesis"] == h["id"] and s["step_id"] in waivers]}
    prompts = ["Have the agreed sequential questions been answered, or their conditional triggers and data gaps explained?",
               "Does each claim state its aggregation, denominator, population and observational limits?",
               "Read aggregate result tables; a null trend is not evidence of no temporal patterns.","Do pooled and within-segment results answer different questions? Lead with the comparison agreed in scope.",
               "Is a weak correlation hiding a curve (nonlinearity flags)?",
               "Do overlapping drivers tell one story or two (collinear pairs)?",
               "Is anything that looks too good actually leakage or a derived column?",
               "Which findings fail FDR, and are any insights resting only on those?"]
    if ent:
        prompts.insert(0, f"Panel data ({ent}): distinguish within-{ent}, between-{ent} and pooled estimates; "
                          "lead with the scoped comparison and explain PANEL SPLIT flags.")
    checks = {"results": per_result, "hypotheses": by_h, "prompts": prompts}
    if registry.broad_change(scope) or "dimension_omissions" in scope:
        checks["dimension_screens"] = {s["step_id"]: s["params"]["by"] for s in registry.change_steps(scope)}
        checks["dimension_omissions"] = scope.get("dimension_omissions", {})
        prompts.append("Inspect group-level offsets, verify omitted or equivalent fields, and complete dimension_coverage.")
    if (registry.broad_change(scope) or "dimension_omissions" in scope) and any(
            s["tool"] == "count-change-contribution" for s in registry.change_steps(scope)):
        prompts.append("Complete intersection_review: cite selected combined-dimension results or explain why none were needed/feasible. Check contributions and offsets against the original total.")
    return checks


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


def _intersection_errors(draft: dict, scope: dict, results: dict) -> list[str]:
    screens = [s for s in registry.change_steps(scope) if s["tool"] == "count-change-contribution"]
    if not (registry.broad_change(scope) or "dimension_omissions" in scope) or not screens:
        return []
    item = draft.get("intersection_review")
    if (not isinstance(item, dict) or item.get("status") not in ("completed", "not_needed", "unresolved")
            or not isinstance(item.get("reason"), str) or not item["reason"].strip()):
        return ["intersection_review needs status (completed, not_needed, unresolved) and a reason"]
    evidence = item.get("evidence", [])
    errs = _check_evidence(evidence, results, "intersection_review")
    if item["status"] != "completed":
        return errs
    # A claim of completion must cite an actual joint count attribution under the
    # same comparison, not merely two separate marginal screens.
    reference = screens[0]["params"]
    matched = []
    for ev in evidence:
        result = results.get(ev.get("result"), {})
        params = result.get("params", {})
        try:
            groups = registry.grouping_columns(params.get("by"))
        except ValueError:
            continue
        if result.get("tool") != "count-change-contribution" or result.get("error") or len(groups) < 2:
            continue
        if any(params.get(k) != reference.get(k) for k in ("cohort", "baseline", "comparison", "history", "absent_is_zero")):
            errs.append("intersection_review: joint result must use the screen's periods and baseline")
            continue
        metrics = {f["metric"]: f.get("estimate") for f in result.get("findings", [])}
        base = {f["metric"]: f.get("estimate")
                for f in results.get(screens[0]["step_id"], {}).get("findings", [])}
        totals = ("expected_count", "observed_count", "net_change")
        if any(not isinstance(metrics.get(k), (int, float)) or not isinstance(base.get(k), (int, float))
               or not math.isclose(metrics[k], base[k], rel_tol=1e-12, abs_tol=1e-8) for k in totals):
            errs.append("intersection_review: joint counts must reconcile to the screen's totals")
            continue
        matched.append(result)
    if not matched:
        errs.append("intersection_review: completed requires a successful combined-dimension count result")
    return errs


def validate_review(draft: dict, run_dir: Path) -> list[str]:
    scope = read_artifact(run_dir, "approved_scope.json")
    results = load_results(run_dir)
    errs = []
    if registry.broad_change(scope) or "dimension_omissions" in scope:
        coverage = draft.get("dimension_coverage")
        steps = registry.change_steps(scope)
        if not isinstance(coverage, dict) or set(coverage) != {s["step_id"] for s in steps}:
            errs.append("dimension_coverage must address every planned change screen by step ID")
        else:
            for step in steps:
                label = step["step_id"]
                row = coverage[label]
                if (not isinstance(row, dict)
                        or row.get("status") not in ("movement", "little movement", "unresolved")
                        or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
                    errs.append(f"{label}: supply coverage status and a reason based on group contributions")
                    continue
                result = results.get(label, {})
                required = "mix_pp" if step["tool"] == "rate-change-decomposition" else "net_change"
                if required not in {f["metric"] for f in result.get("findings", [])} and row["status"] != "unresolved":
                    errs.append(f"{label}: missing attribution evidence requires unresolved status")
    errs += _intersection_errors(draft, scope, results)
    ids = {h["id"] for h in scope["hypotheses"]}
    waiver_artifact = read_artifact(run_dir, "step_waivers.json") or {}
    waivers = ({w["step_id"] for w in waiver_artifact.get("waivers", [])}
               if (waiver_artifact.get("upstream") or {}).get("sha256") == sha(run_dir / "approved_scope.json") else set())
    hypothesis_steps = {h["id"]: {s["step_id"] for s in registry.plan_steps(scope) if s["hypothesis"] == h["id"]}
                        for h in scope["hypotheses"]}
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
        all_skipped = bool(hypothesis_steps.get(v.get("id"))) and hypothesis_steps[v.get("id")].issubset(waivers)
        adaptive = next((h for h in scope["hypotheses"] if h["id"] == v.get("id")
                         and not h.get("pathway") and h.get("followup_when")), None)
        if v.get("verdict") == "not_evaluated":
            if adaptive:
                errs += _check_evidence(v.get("evidence", []), results, where)
            elif not all_skipped:
                errs.append(f"{where}: not_evaluated is allowed only when all of the hypothesis's steps were user-approved skips")
        else:
            errs += _check_evidence(v.get("evidence", []), results, where)
        errs += _causal(v.get("reasoning"), where)
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
    if not items and not draft.get("no_findings_reason"):
        errs.append("provide supported insights or a no_findings_reason; never pad the report")
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
        for ev in ins.get("evidence", []):
            result = results.get(ev.get("result"), {})
            finding = next((f for f in result.get("findings", []) if f.get("label") == ev.get("finding")), {})
            if str(finding.get("interval_status", "")).startswith("screening_point_estimate"):
                errs.append(f"{where}: '{ev.get('finding')}' is screening-only; run a selected deep dive for a report-grade interval")
        for key in ("title", "statement"):
            errs += _causal(ins.get(key), f"{where} {key}")
    for rec in draft.get("recommendations", []):
        for key in ("action", "rationale", "validation_plan", "success_metric", "assumptions", "risks"):
            if not rec.get(key):
                errs.append(f"recommendation needs {key}")
        errs += _check_evidence(rec.get("evidence", []), results, "recommendation")
        if rec.get("evidence_type") not in ("descriptive", "association", "experimental", "causal_design"):
            errs.append("recommendation needs an explicit evidence_type")
    for key in ("limitations", "next_steps"):
        if not draft.get(key):
            errs.append(f"needs '{key}'")
    return errs
