# Audit method

Read this reference before classifying candidate Frames, ignored internal layers, or variant issues.

## Evidence classes

- **Observed:** Directly returned by Figma metadata or a trusted export.
- **Derived:** Deterministically calculated from observed node records.
- **Estimated:** Approximate count or sampled result supplied by the scan or user.
- **Inferred:** Design judgment that explains likely intent. It must include the evidence and uncertainty.

Never merge these labels. An estimated recurrence count remains estimated in the final report.

## Existing library objects

Inventory `COMPONENT_SET` and `COMPONENT` separately. For a Component within a set, record its owning set and variant properties rather than double-presenting it as an unrelated standalone component. Keep node IDs when available.

For each Component Set, derive axis names and values, observed variant combinations, inconsistent axis sets, duplicates, gaps in the observed Cartesian product, singleton axes, and generic axis names such as `Property 1` or `Variant`.

Missing combinations are not automatically defects. Phrase them as coverage gaps for review, especially when the design intentionally excludes impossible states.

## Instance audit

Resolve an Instance only through its stable main-component ID. Report usage count per source Component when the scan is complete; unresolved or missing source IDs; local overrides only if exposed; and detached lookalikes as Frame candidates, not as Instances. A matching name or screenshot is not a resolved relationship.

## Candidate Frame detection

A candidate family must contain at least three eligible ordinary Frames by default. Exclude Frames that are descendants of a Component, Component Set, or Instance unless component-internal auditing was explicitly requested.

Group conservatively using normalized semantic name, child node types and order, nesting pattern, geometry buckets or layout properties, and an explicit structural signature when supplied. Split same-name Frames when structures materially diverge. Cross-name structural matches may be mentioned with lower confidence unless role and context also agree.

Use two levels of grouping:

1. **Semantic family:** the normalized name or an explicit semantic role. This reveals that one business label may contain several incompatible structures.
2. **Structural state:** the exact or supplied structural/visual signature within that semantic family. Candidate eligibility is evaluated at this level, not from the semantic-family total alone.

Report the number of structural clusters and the total semantic-family count. A large semantic family with many small clusters is a domain that needs design review, not one automatically convertible component.

## Effective visibility

Visibility is inherited. A Frame is confirmed visible only when the Frame and every known ancestor have `visible != false` and effective opacity greater than `0.01`. Prefer an upstream `effective_visible` or `effective_opacity` value when supplied. Otherwise derive the result from the available ancestor chain.

Keep hidden or effectively transparent matches in a separate `hidden-only` result. Record the exclusion reason and count. If an ancestor is missing from a partial inventory, mark visibility unresolved rather than upgrading the candidate to confirmed.

Confidence inputs are recurrence, structural similarity, context spread, naming quality, node depth, effective visibility, and evidence of overlap with an existing Component.

- **High:** score at least 0.75; repeated and structurally consistent, with no major ambiguity.
- **Medium:** 0.55–0.74; plausible but needs review of states, dimensions, or role.
- **Low:** below 0.55; mention only when useful and never recommend automatic conversion.

## Internal-layer filter

Typical internal names include auto-generated Frames and Groups, `Container`, `Wrapper`, `Content`, `BG`, `Background`, `Fill + Shadow`, `Mask`, `Overlay`, `Spacer`, `点击热区`, and similar hit-area names.

Also down-rank or filter clearly generated deep-layer names such as `Component 13`, `_图层_1`, or `内容 group` when ancestry and structure show that they are implementation details. Do not apply this rule to an actual `COMPONENT` node merely because its name starts with `Component`.

Filtering means excluding a node from candidate results. It never means deleting or renaming it. Do not filter solely because a name is short: a repeated top-level `Card`, `Tab`, or `Input` can still be legitimate. Consider ancestry, structure, size, and context.

## Naming review

Flag auto-generated names; duplicate business names attached to incompatible structures; mixed hierarchy separators within one family; inconsistent language or capitalization within the same family; state or theme encoded inconsistently between names and axes; and generic axes or values.

Do not force English naming, slash hierarchies, or a taxonomy unless the user supplied that convention. Recommend one coherent convention and show a small migration example.

## Safe recommendations

Recommendations may show a target hierarchy or possible variant axes. State that they are proposals. This audit skill must not convert Frames, detach Instances, rewrite names, or create a replacement library.
