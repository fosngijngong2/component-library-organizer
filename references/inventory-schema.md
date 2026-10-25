# Normalized inventory schema

Read this reference when converting Figma metadata into JSON or when preparing input for `scripts/audit_inventory.py`.

## Root object

```json
{
  "schema_version": "1.1",
  "file": {
    "name": "Example",
    "url": "https://www.figma.com/design/...",
    "file_key": "optional",
    "node_scope": "0:1",
    "source": "live-metadata",
    "coverage": "complete"
  },
  "summary": {},
  "nodes": [],
  "observations": {}
}
```

Required root fields are `schema_version` and at least one of `nodes`, `summary`, or `observations`.

`file.coverage` is `complete`, `partial`, or `unknown`. Use `complete` only when every intended page or node scope was traversed without truncation. `file.source` should describe the evidence, such as `live-metadata`, `figma-export`, `user-provided-summary`, or `mixed`.

## Summary

Summary values are non-negative integers unless noted:

```json
{
  "components": 16,
  "component_sets": 7,
  "instances": 17007,
  "frames": 45637,
  "variables": 0,
  "local_text_styles": 0,
  "local_effect_styles": 0
}
```

If `nodes` contains the full scan, the script derives node totals and checks supplied totals for mismatches. If the node list is partial, keep the authoritative whole-file totals in `summary` and set coverage to `partial`.

## Nodes

Each node is a flat record. Parent-child relationships use stable IDs.

```json
{
  "id": "123:456",
  "name": "State=Active",
  "type": "COMPONENT",
  "parent_id": "123:400",
  "component_id": null,
  "component_set_id": "123:400",
  "width": 320,
  "height": 48,
  "visible": true,
  "opacity": 1,
  "effective_visible": true,
  "effective_opacity": 1,
  "top_level_context_id": "12:1",
  "semantic_role": "Input/Search",
  "variant_properties": {"State": "Active"},
  "structure_signature": "optional-upstream-signature",
  "visual_signature": "optional-upstream-state-signature",
  "nested_instance_count": 2,
  "variable_binding_count": 4,
  "inherits_variable_modes": true,
  "font_availability": "available"
}
```

- `id`, `name`, and `type` are required.
- Use uppercase Figma node types where possible.
- `component_id` on an Instance is the stable ID of its main Component. Do not infer it from names.
- `component_set_id` identifies the owning Component Set when available.
- `variant_properties` maps axis names to values.
- `effective_visible` and `effective_opacity` are optional upstream calculations across the full ancestor chain. When absent, the script derives them from available ancestors and reports unresolved ancestry in a partial inventory.
- `top_level_context_id` is the nearest meaningful page-level screen, section, or flow container. It is preferred over the immediate parent when measuring context spread.
- `semantic_role` is optional and must come from observable metadata or a human-confirmed classification, not guesswork.
- `structure_signature` is optional. Supply it only when generated from child type/order, relevant geometry, and nesting—not from a screenshot hash.
- `visual_signature` may split one structure into observable visual states. It should not contain arbitrary text content.
- `nested_instance_count`, `variable_binding_count`, `inherits_variable_modes`, and `font_availability` support a read-only portability risk assessment for a later editing workflow.
- Preserve exact node IDs and names. Do not put access tokens, emails, comments, or unrelated text content in the inventory.

## Precomputed observations

Use observations when the source provides aggregate findings but not a full node list. This is also useful for documenting estimates from a large scan.

```json
{
  "observations": {
    "existing": [{
      "name": "Send Button",
      "kind": "COMPONENT_SET",
      "node_id": "optional",
      "variants": 3,
      "variant_axes": {"State": ["Disabled", "Partial", "Active"]},
      "evidence": "observed"
    }],
    "candidates": [{
      "name": "Chat Item",
      "count": 500,
      "count_kind": "estimated",
      "confidence": 0.92,
      "basis": ["high recurrence", "similar child structure"]
    }],
    "hidden_candidates": [{
      "name": "Legacy Header",
      "count": 24,
      "count_kind": "exact",
      "confidence": 0.61,
      "basis": ["all representatives have a hidden or transparent ancestor"]
    }],
    "ignored": ["Container", "BG"],
    "issues": [{"severity": "medium", "subject": "Input", "detail": "Two incompatible structures share one name."}],
    "recommendations": [{
      "component": "Input",
      "axes": {"Theme": ["Light", "Dark"], "State": ["Default", "Active", "Disabled"]}
    }],
    "limitations": ["Only selected component sets were inspected in detail."],
    "benchmark": {
      "confirmed_visible_families": 62,
      "hidden_only_candidate_families": 24,
      "frozen_visual_exceptions": 1
    }
  }
}
```

Allowed evidence labels are `observed`, `derived`, `estimated`, and `inferred`. A precomputed observation must not be silently upgraded to an exact fact.

## Large-file acquisition

For a large Figma file, capture page IDs first, then traverse one page or bounded section at a time. Keep a scan ledger with each scope marked `complete`, `truncated`, `failed`, or `skipped`. Merge totals only for disjoint scopes. Deduplicate nodes by stable ID. If a response is truncated, rescan smaller subtrees rather than guessing the omitted content.

Keep tool output compact: return aggregate counts plus bounded representative IDs, and persist the full normalized inventory outside the Figma file when possible. Do not rely on one oversized response as the only evidence source.
