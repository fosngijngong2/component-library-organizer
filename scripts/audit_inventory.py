#!/usr/bin/env python3
"""Create a read-only component-library audit from normalized Figma inventory JSON."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


NOISE_NAMES = {
    "container", "wrapper", "content", "inner", "outer", "background", "bg",
    "fill", "fill + shadow", "mask", "overlay", "spacer", "hotspot",
    "hit area", "click area", "点击热区", "容器", "背景", "蒙层", "遮罩",
}
WEAK_NAMES = {
    "block", "item", "list", "list1", "module", "component", "组件",
    "内容 group", "content group",
}
GENERIC_AXIS_NAMES = {"property", "property 1", "variant", "variant 1", "属性", "属性 1"}
SUMMARY_KEYS = (
    "components", "component_sets", "instances", "frames", "variables",
    "local_text_styles", "local_effect_styles",
)


def normalize_name(value: str) -> str:
    value = value.strip().lower().replace("／", "/")
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"(?:\s+copy|\s*副本)(?:\s*\d+)?$", "", value)


def is_noise_name(value: str) -> bool:
    name = normalize_name(value)
    if name in NOISE_NAMES:
        return True
    return bool(
        re.fullmatch(r"(?:frame|group|rectangle|ellipse|line|vector)[\s_-]*\d*", name)
        or re.fullmatch(r"(?:图层|框架|编组)[\s_-]*\d*", name)
        or re.fullmatch(r"component[\s_-]+\d+", name)
        or re.fullmatch(r"_?图层_?\d+", name)
        or name in {"内容 group", "content group"}
    )


def is_weak_name(value: str) -> bool:
    name = normalize_name(value)
    return not name or name in WEAK_NAMES or is_noise_name(name)


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _bucket(value: Any, step: int = 4) -> str:
    number = _number(value)
    return "?" if number is None else str(int(round(number / step) * step))


def _node_type(node: dict[str, Any]) -> str:
    return str(node.get("type", "UNKNOWN")).upper()


def _summary_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, int]:
    types = Counter(_node_type(node) for node in nodes)
    return {
        "components": types["COMPONENT"],
        "component_sets": types["COMPONENT_SET"],
        "instances": types["INSTANCE"],
        "frames": types["FRAME"],
        "variables": 0,
        "local_text_styles": 0,
        "local_effect_styles": 0,
    }


def _children_index(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node.get("parent_id") is not None:
            children[str(node["parent_id"])].append(node)
    return children


def _fingerprint(node: dict[str, Any], children: dict[str, list[dict[str, Any]]], depth: int = 2) -> str:
    if node.get("structure_signature"):
        return f"explicit:{node['structure_signature']}"

    def walk(current: dict[str, Any], remaining: int) -> Any:
        base: list[Any] = [_node_type(current), _bucket(current.get("width")), _bucket(current.get("height"))]
        if remaining > 0:
            base.append([walk(child, remaining - 1) for child in children.get(str(current.get("id")), [])])
        return base

    raw = json.dumps(walk(node, depth), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _visual_fingerprint(node: dict[str, Any], fallback: str) -> str:
    if node.get("visual_signature"):
        return f"explicit:{node['visual_signature']}"
    return fallback


def _blocked_by_component_ancestor(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> bool:
    parent_id = node.get("parent_id")
    visited: set[str] = set()
    while parent_id:
        key = str(parent_id)
        if key in visited:
            return True
        visited.add(key)
        parent = node_by_id.get(key)
        if not parent:
            return False
        if _node_type(parent) in {"COMPONENT", "COMPONENT_SET", "INSTANCE"}:
            return True
        parent_id = parent.get("parent_id")
    return False


def _ancestry(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    result: list[dict[str, Any]] = []
    parent_id = node.get("parent_id")
    visited: set[str] = set()
    unresolved = False
    while parent_id:
        key = str(parent_id)
        if key in visited:
            unresolved = True
            break
        visited.add(key)
        parent = node_by_id.get(key)
        if not parent:
            unresolved = True
            break
        result.append(parent)
        parent_id = parent.get("parent_id")
    return result, unresolved


def _effective_visibility(
    node: dict[str, Any], node_by_id: dict[str, dict[str, Any]], opacity_threshold: float = 0.01
) -> tuple[str, list[str]]:
    if node.get("effective_visible") is False:
        return "hidden", ["upstream effective_visible=false"]
    effective_opacity = _number(node.get("effective_opacity"))
    if effective_opacity is not None and effective_opacity <= opacity_threshold:
        return "hidden", [f"effective opacity <= {opacity_threshold:g}"]

    reasons: list[str] = []
    ancestry, unresolved = _ancestry(node, node_by_id)
    for current in [node, *ancestry]:
        if current.get("visible") is False:
            reasons.append(f"hidden node/ancestor {current.get('id', '(unknown)')}")
        opacity = _number(current.get("opacity"))
        if opacity is not None and opacity <= opacity_threshold:
            reasons.append(f"transparent node/ancestor {current.get('id', '(unknown)')}")
    if reasons:
        return "hidden", reasons
    if unresolved:
        return "unresolved", ["ancestor chain is incomplete"]
    return "visible", []


def _depth(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> int:
    ancestry, _ = _ancestry(node, node_by_id)
    return len(ancestry)


def _context_id(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> str:
    if node.get("top_level_context_id") is not None:
        return str(node["top_level_context_id"])
    current = node
    ancestry, _ = _ancestry(node, node_by_id)
    for parent in ancestry:
        if _node_type(parent) in {"PAGE", "SECTION"}:
            return str(current.get("id", parent.get("id", "(unknown)")))
        current = parent
    return str(current.get("id", node.get("parent_id", "(unknown)")))


def _confidence(count: int, context_count: int, meaningful_name: bool, cluster_count: int = 1, average_depth: float = 0) -> float:
    recurrence = 0.45 if count >= 50 else 0.38 if count >= 20 else 0.31 if count >= 10 else 0.23 if count >= 5 else 0.15
    structural = max(0.15, 0.35 - min(0.20, max(0, cluster_count - 1) * 0.04))
    context = 0.10 if context_count >= 2 else 0.04
    naming = 0.10 if meaningful_name else 0.0
    depth_penalty = 0.15 if average_depth >= 9 else 0.10 if average_depth >= 6 else 0.0
    return round(max(0.0, min(1.0, recurrence + structural + context + naming - depth_penalty)), 2)


def _band(score: float) -> str:
    return "high" if score >= 0.75 else "medium" if score >= 0.55 else "low"


def _portability_risk(family: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if any((_number(node.get("nested_instance_count")) or 0) > 0 for node in family):
        reasons.append("contains nested Instances")
    if any((_number(node.get("variable_binding_count")) or 0) > 0 for node in family):
        reasons.append("contains variable bindings")
    if any(node.get("inherits_variable_modes") is True for node in family):
        reasons.append("inherits variable modes from source context")
    if any(str(node.get("font_availability", "available")).lower() not in {"available", "ok", "true"} for node in family):
        reasons.append("contains unavailable or unresolved fonts")
    if any(node.get("unresolved_style_count", 0) for node in family):
        reasons.append("contains unresolved local or remote styles")
    if any(node.get("cross_page_visual_changed") is True for node in family):
        reasons.append("a prior cross-page comparison changed appearance")
    if not reasons:
        return "low", []
    high_markers = {
        "inherits variable modes from source context",
        "contains unavailable or unresolved fonts",
        "contains unresolved local or remote styles",
        "a prior cross-page comparison changed appearance",
    }
    return ("high" if len(reasons) >= 2 or any(reason in high_markers for reason in reasons) else "medium"), reasons


def _candidate_frames(
    nodes: list[dict[str, Any]], min_repetitions: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    node_by_id = {str(node["id"]): node for node in nodes if node.get("id") is not None}
    children = _children_index(nodes)
    visible_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    hidden_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    ignored = Counter()
    visibility_exclusions = Counter()

    for node in nodes:
        if _node_type(node) != "FRAME":
            continue
        if _blocked_by_component_ancestor(node, node_by_id):
            continue
        name = str(node.get("name", "")).strip() or "(unnamed)"
        if is_noise_name(name):
            ignored[name] += 1
            continue
        signature = _fingerprint(node, children)
        key = (normalize_name(str(node.get("semantic_role") or name)), signature)
        visibility, reasons = _effective_visibility(node, node_by_id)
        if visibility == "visible":
            visible_groups[key].append(node)
        elif visibility == "hidden":
            hidden_groups[key].append(node)
            visibility_exclusions.update(reasons)
        else:
            unresolved_groups[key].append(node)
            visibility_exclusions.update(reasons)

    semantic_clusters: dict[str, set[str]] = defaultdict(set)
    semantic_totals = Counter()
    for (semantic, signature), family in itertools.chain(
        visible_groups.items(), hidden_groups.items(), unresolved_groups.items()
    ):
        semantic_clusters[semantic].add(signature)
        semantic_totals[semantic] += len(family)

    def build_candidate(
        semantic: str, signature: str, family: list[dict[str, Any]], visibility: str
    ) -> dict[str, Any]:
        names = Counter(str(node.get("name", "")).strip() or "(unnamed)" for node in family)
        representative = names.most_common(1)[0][0]
        contexts = {_context_id(node, node_by_id) for node in family}
        cluster_count = len(semantic_clusters[semantic])
        average_depth = sum(_depth(node, node_by_id) for node in family) / len(family)
        score = _confidence(
            len(family), len(contexts), not is_weak_name(representative), cluster_count, average_depth
        )
        visual_states = Counter(_visual_fingerprint(node, signature) for node in family)
        portability, portability_reasons = _portability_risk(family)
        item: dict[str, Any] = {
            "name": representative,
            "semantic_family": semantic,
            "count": len(family),
            "family_total_count": semantic_totals[semantic],
            "structural_cluster_count": cluster_count,
            "visual_state_count": len(visual_states),
            "count_kind": "exact",
            "confidence": score,
            "confidence_band": _band(score),
            "signature": signature,
            "visibility": visibility,
            "average_depth": round(average_depth, 1),
            "representative_node_ids": [str(node.get("id")) for node in family[:5]],
            "basis": [
                f"{len(family)} repeated Frames in this structural cluster",
                f"{semantic_totals[semantic]} Frames across the semantic family",
                f"{len(contexts)} top-level contexts",
            ],
            "portability_risk": portability,
            "portability_reasons": portability_reasons,
        }
        if cluster_count > 1:
            item["ambiguity"] = (
                f"Semantic family contains {cluster_count} structural clusters; "
                "review them as separate states or components before promotion."
            )
        return item

    candidates: list[dict[str, Any]] = []
    for (semantic, signature), family in visible_groups.items():
        if len(family) < min_repetitions:
            continue
        candidates.append(build_candidate(semantic, signature, family, "confirmed-visible"))

    hidden_candidates: list[dict[str, Any]] = []
    for (semantic, signature), family in hidden_groups.items():
        if len(family) < min_repetitions:
            continue
        item = build_candidate(semantic, signature, family, "hidden-only")
        item["basis"].append("all representatives are hidden or effectively transparent")
        hidden_candidates.append(item)

    for (semantic, signature), family in unresolved_groups.items():
        if len(family) < min_repetitions:
            continue
        item = build_candidate(semantic, signature, family, "visibility-unresolved")
        item["basis"].append("ancestor chain is incomplete")
        hidden_candidates.append(item)

    candidates.sort(key=lambda item: (-float(item["confidence"]), -int(item["count"]), str(item["name"])))
    hidden_candidates.sort(key=lambda item: (-int(item["count"]), str(item["name"])))
    ignored_items = [
        {"name": name, "count": count, "reason": "generic or auto-generated internal-layer name"}
        for name, count in ignored.most_common()
    ]
    return candidates, hidden_candidates, ignored_items, dict(visibility_exclusions)


def _variant_audit(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    children = _children_index(nodes)
    sets: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for component_set in (node for node in nodes if _node_type(node) == "COMPONENT_SET"):
        set_id = str(component_set.get("id"))
        variants = [child for child in children.get(set_id, []) if _node_type(child) == "COMPONENT"]
        axis_values: dict[str, set[str]] = defaultdict(set)
        combos: Counter[tuple[tuple[str, str], ...]] = Counter()
        key_sets: set[tuple[str, ...]] = set()
        for variant in variants:
            properties = variant.get("variant_properties") or {}
            if not isinstance(properties, dict):
                properties = {}
            combo = tuple(sorted((str(key), str(value)) for key, value in properties.items()))
            combos[combo] += 1
            key_sets.add(tuple(sorted(str(key) for key in properties)))
            for key, value in properties.items():
                axis_values[str(key)].add(str(value))

        record = {
            "name": str(component_set.get("name", "(unnamed set)")),
            "kind": "COMPONENT_SET",
            "node_id": set_id,
            "variants": len(variants),
            "variant_axes": {key: sorted(values) for key, values in sorted(axis_values.items())},
            "evidence": "derived",
        }
        sets.append(record)
        subject = record["name"]
        if variants and len(key_sets) > 1:
            issues.append({"severity": "high", "subject": subject, "detail": "Variants use inconsistent axis sets."})
        duplicate_count = sum(count - 1 for count in combos.values() if count > 1)
        if duplicate_count:
            issues.append({"severity": "high", "subject": subject, "detail": f"{duplicate_count} duplicate variant combinations detected."})
        for axis, values in axis_values.items():
            if normalize_name(axis) in GENERIC_AXIS_NAMES:
                issues.append({"severity": "medium", "subject": subject, "detail": f"Generic variant axis name: {axis}."})
            if len(values) == 1:
                issues.append({"severity": "low", "subject": subject, "detail": f"Axis {axis} has only one observed value."})
        if axis_values:
            expected = math.prod(len(values) for values in axis_values.values())
            observed = len(combos)
            if expected <= 100 and observed < expected:
                issues.append({"severity": "medium", "subject": subject, "detail": f"Observed {observed} of {expected} possible variant combinations; review intentional gaps."})
    sets.sort(key=lambda item: str(item["name"]))
    return sets, issues


def _instance_audit(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    components = {
        str(node["id"]): node for node in nodes
        if _node_type(node) == "COMPONENT" and node.get("id") is not None
    }
    usage = Counter()
    unresolved = Counter()
    for node in nodes:
        if _node_type(node) != "INSTANCE":
            continue
        source_id = node.get("component_id")
        if source_id is None or str(source_id) not in components:
            unresolved[str(source_id) if source_id is not None else "(missing id)"] += 1
        else:
            usage[str(source_id)] += 1
    return {
        "total": sum(1 for node in nodes if _node_type(node) == "INSTANCE"),
        "top_sources": [
            {"component_id": source_id, "name": str(components[source_id].get("name", "(unnamed component)")), "count": count}
            for source_id, count in usage.most_common(20)
        ],
        "unresolved": sum(unresolved.values()),
        "unresolved_source_ids": dict(unresolved),
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _merge_named(primary: Iterable[dict[str, Any]], secondary: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in itertools.chain(primary, secondary):
        if not isinstance(item, dict):
            continue
        key = (normalize_name(str(item.get("name", item.get("subject", "")))), str(item.get("kind", "")))
        if key not in seen:
            seen.add(key)
            result.append(dict(item))
    return result


def _merge_candidates(primary: Iterable[dict[str, Any]], secondary: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in itertools.chain(primary, secondary):
        if not isinstance(item, dict):
            continue
        key = (
            normalize_name(str(item.get("semantic_family") or item.get("name", ""))),
            str(item.get("signature", "precomputed")),
            str(item.get("visibility", "confirmed-visible")),
        )
        if key not in seen:
            seen.add(key)
            result.append(dict(item))
    return result


def audit_document(data: dict[str, Any], min_repetitions: int = 3) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Inventory root must be a JSON object.")
    nodes = [node for node in _as_list(data.get("nodes")) if isinstance(node, dict)]
    observations = data.get("observations") if isinstance(data.get("observations"), dict) else {}
    supplied = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    derived = _summary_from_nodes(nodes)
    summary = {
        key: supplied[key] if isinstance(supplied.get(key), int) and supplied[key] >= 0 else derived[key]
        for key in SUMMARY_KEYS
    }

    derived_candidates, derived_hidden_candidates, derived_ignored, visibility_exclusions = _candidate_frames(
        nodes, min_repetitions
    )
    derived_sets, variant_issues = _variant_audit(nodes)
    existing = _merge_named(_as_list(observations.get("existing")), derived_sets)
    candidates = _merge_candidates(_as_list(observations.get("candidates")), derived_candidates)
    hidden_candidates = _merge_candidates(
        _as_list(observations.get("hidden_candidates")), derived_hidden_candidates
    )
    ignored_observations: list[dict[str, Any]] = []
    for item in _as_list(observations.get("ignored")):
        ignored_observations.append({"name": item, "reason": "provided internal-layer filter"} if isinstance(item, str) else dict(item))
    ignored = _merge_named(ignored_observations, derived_ignored)
    issues = [dict(item) for item in _as_list(observations.get("issues")) if isinstance(item, dict)] + variant_issues

    file_info = data.get("file") if isinstance(data.get("file"), dict) else {}
    coverage = str(file_info.get("coverage", "unknown")).lower()
    if coverage not in {"complete", "partial", "unknown"}:
        coverage = "unknown"
    mismatches = []
    if nodes and coverage == "complete":
        for key in ("components", "component_sets", "instances", "frames"):
            if key in supplied and supplied.get(key) != derived[key]:
                mismatches.append({"key": key, "supplied": supplied.get(key), "derived": derived[key]})

    instance_audit = _instance_audit(nodes) if nodes else {
        "total": summary["instances"], "top_sources": [], "unresolved": None, "unresolved_source_ids": {},
    }
    portability_risks = []
    for item in itertools.chain(candidates, hidden_candidates):
        if item.get("portability_risk") in {"medium", "high"}:
            portability_risks.append({
                "name": item.get("name", "(unnamed)"),
                "risk": item.get("portability_risk"),
                "reasons": list(item.get("portability_reasons") or []),
                "representative_node_ids": list(item.get("representative_node_ids") or []),
            })
    return {
        "schema_version": "1.1",
        "mode": "read-only",
        "file": dict(file_info),
        "coverage": coverage,
        "summary": summary,
        "summary_mismatches": mismatches,
        "existing": existing,
        "instance_audit": instance_audit,
        "candidates": candidates,
        "hidden_candidates": hidden_candidates,
        "visibility_exclusions": visibility_exclusions,
        "portability_risks": portability_risks,
        "issues": issues,
        "ignored": ignored,
        "recommendations": [dict(item) for item in _as_list(observations.get("recommendations")) if isinstance(item, dict)],
        "limitations": [str(item) for item in _as_list(observations.get("limitations"))],
        "benchmark": dict(observations.get("benchmark")) if isinstance(observations.get("benchmark"), dict) else {},
    }


def _fmt_count(value: Any, kind: str | None = None) -> str:
    if value is None:
        return "not available"
    rendered = f"{value:,}" if isinstance(value, int) else str(value)
    return f"~{rendered}" if kind == "estimated" else rendered


def render_markdown(report: dict[str, Any]) -> str:
    file_info = report.get("file", {})
    lines = ["# Component Library Audit", ""]
    for label, key in (("File", "name"), ("URL", "url"), ("Scope", "node_scope")):
        if file_info.get(key):
            lines.append(f"- {label}: {file_info[key]}")
    lines.extend([
        "- Mode: Read-only",
        f"- Coverage: {str(report.get('coverage', 'unknown')).capitalize()}",
        f"- Evidence source: {file_info.get('source', 'not specified')}",
        "", "## Inventory", "",
    ])
    labels = {
        "components": "Components", "component_sets": "Component Sets", "instances": "Instances",
        "frames": "Frames", "variables": "Variables", "local_text_styles": "Local Text Styles",
        "local_effect_styles": "Local Effect Styles",
    }
    for key in SUMMARY_KEYS:
        lines.append(f"- {labels[key]}: {_fmt_count(report['summary'].get(key))}")
    if report.get("summary_mismatches"):
        lines.extend(["", "Summary mismatches:"])
        for item in report["summary_mismatches"]:
            lines.append(f"- {item['key']}: supplied {item['supplied']}, derived {item['derived']}")

    lines.extend(["", "## Existing components", ""])
    if not report.get("existing"):
        lines.append("- No detailed component records were available.")
    for item in report.get("existing", []):
        detail = f"{item.get('name', '(unnamed)')} — {item.get('kind', 'COMPONENT')}"
        if item.get("variants") is not None:
            detail += f", {item['variants']} variants"
        if item.get("node_id"):
            detail += f" (node {item['node_id']})"
        if item.get("evidence"):
            detail += f" [{item['evidence']}]"
        lines.append(f"- {detail}")
        axes = item.get("variant_axes")
        if isinstance(axes, dict) and axes:
            lines.append("  - Axes: " + "; ".join(f"{name}: {' | '.join(map(str, values))}" for name, values in axes.items()))

    lines.extend(["", "## Instance reuse", ""])
    instance_audit = report.get("instance_audit", {})
    lines.append(f"- Total Instances: {_fmt_count(instance_audit.get('total'))}")
    if instance_audit.get("top_sources"):
        for source in instance_audit["top_sources"]:
            lines.append(f"- {source['name']} ({source['component_id']}): {source['count']:,}")
        lines.append(f"- Unresolved source relationships: {instance_audit.get('unresolved', 0):,}")
    else:
        lines.append("- Source-level main-component mapping was not available in this evidence set.")

    lines.extend(["", "## Candidate components", ""])
    if not report.get("candidates"):
        lines.append("- No candidate family met the configured recurrence threshold.")
    for item in report.get("candidates", []):
        score = float(item.get("confidence", 0))
        band = item.get("confidence_band") or _band(score)
        count = _fmt_count(item.get("count"), item.get("count_kind"))
        lines.append(f"- {item.get('name', '(unnamed)')} — {count} occurrences, {str(band).capitalize()} confidence ({score:.2f})")
        if item.get("family_total_count") is not None or item.get("structural_cluster_count") is not None:
            lines.append(
                "  - Family: "
                f"{_fmt_count(item.get('family_total_count', item.get('count')))} total; "
                f"{item.get('structural_cluster_count', 1)} structural clusters; "
                f"{item.get('visual_state_count', 1)} visual states in this cluster"
            )
        if isinstance(item.get("basis"), list) and item["basis"]:
            lines.append(f"  - Evidence: {'; '.join(map(str, item['basis']))}")
        if isinstance(item.get("representative_node_ids"), list) and item["representative_node_ids"]:
            lines.append(f"  - Representative nodes: {', '.join(map(str, item['representative_node_ids']))}")
        if item.get("ambiguity"):
            lines.append(f"  - Review: {item['ambiguity']}")

    lines.extend(["", "## Hidden-only candidates", ""])
    if not report.get("hidden_candidates"):
        lines.append("- No repeated family was classified as hidden-only or visibility-unresolved.")
    for item in report.get("hidden_candidates", []):
        score = float(item.get("confidence", 0))
        count = _fmt_count(item.get("count"), item.get("count_kind"))
        lines.append(
            f"- {item.get('name', '(unnamed)')} — {count} occurrences, "
            f"{item.get('visibility', 'hidden-only')}, review confidence {score:.2f}"
        )
        if isinstance(item.get("representative_node_ids"), list) and item["representative_node_ids"]:
            lines.append(f"  - Representative nodes: {', '.join(map(str, item['representative_node_ids']))}")
        if isinstance(item.get("basis"), list) and item["basis"]:
            lines.append(f"  - Evidence: {'; '.join(map(str, item['basis']))}")
    if report.get("visibility_exclusions"):
        lines.append("- Visibility exclusions: " + "; ".join(
            f"{reason} ({count})" for reason, count in report["visibility_exclusions"].items()
        ))

    lines.extend(["", "## Portability risks", ""])
    if not report.get("portability_risks"):
        lines.append("- No medium/high cross-page portability risk was derived from the supplied metadata.")
    for item in report.get("portability_risks", []):
        lines.append(
            f"- [{str(item.get('risk', 'review')).upper()}] {item.get('name', '(unnamed)')}: "
            f"{'; '.join(map(str, item.get('reasons') or []))}."
        )
        if item.get("risk") == "high":
            lines.append("  - Handoff gate: compare source and result visually; review whether a visual freeze is required.")

    lines.extend(["", "## Naming and variant issues", ""])
    if not report.get("issues"):
        lines.append("- No evidence-backed issue was recorded in the available scope.")
    for item in report.get("issues", []):
        lines.append(f"- [{str(item.get('severity', 'review')).upper()}] {item.get('subject', 'General')}: {item.get('detail', '')}")

    lines.extend(["", "## Ignored internal layers", ""])
    if not report.get("ignored"):
        lines.append("- No internal-layer filters were recorded.")
    for item in report.get("ignored", []):
        count = f" ({item['count']:,})" if isinstance(item.get("count"), int) else ""
        lines.append(f"- {item.get('name', '(unnamed)')}{count} — {item.get('reason', 'filtered from candidate results')}")
    lines.append("- Nothing was deleted or modified.")

    lines.extend(["", "## Recommended structure — Proposal", ""])
    if not report.get("recommendations"):
        lines.append("- No target structure is proposed without stronger evidence.")
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation.get('component', 'Component')}")
        if isinstance(recommendation.get("axes"), dict):
            for axis, values in recommendation["axes"].items():
                lines.append(f"  - {axis}: {' | '.join(map(str, values))}")
        if recommendation.get("note"):
            lines.append(f"  - Note: {recommendation['note']}")

    lines.extend(["", "## Limitations and next step", ""])
    limitations = report.get("limitations", [])
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    elif report.get("coverage") != "complete":
        lines.append("- The scan is not complete; totals or families may be missing.")
    else:
        lines.append("- No scan limitation was recorded.")
    if report.get("benchmark"):
        lines.append("- Regression benchmark: " + "; ".join(
            f"{key}={value}" for key, value in report["benchmark"].items()
        ))
    lines.append("- Next step: perform a focused read-only rescan of the highest-value candidate family before any proposed edit workflow.")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Normalized inventory JSON")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write output to a file instead of stdout")
    parser.add_argument("--min-repetitions", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.min_repetitions < 2:
        raise SystemExit("--min-repetitions must be at least 2")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        report = audit_document(data, min_repetitions=args.min_repetitions)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else render_markdown(report)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
