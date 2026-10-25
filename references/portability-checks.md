# Copy-to-library portability checks

Read this reference only when the audit will inform a later workflow that copies or recreates candidates on another Figma page or in another file. The audit itself remains read-only.

## Purpose

A Frame can be structurally identical yet render differently after it leaves its source page. Before recommending automatic promotion, record whether its appearance depends on page context.

## Risk signals

- Nested Instances whose main Components are remote, unresolved, hidden, or context-dependent.
- Variable bindings whose resolved values depend on explicit or inherited collection modes.
- Fonts that are missing, unavailable, or represented by mixed styled segments that cannot be loaded.
- Effect, paint, grid, or text styles that are remote or unresolved.
- Masks, blend modes, clipping, or absolute-positioned descendants whose appearance depends on ancestor geometry.
- A prior screenshot or structural comparison that changed after cross-page cloning.

## Risk levels

- **Low:** no observed nested Instances, variable bindings, unavailable fonts, or unresolved styles. Normal structural verification is still required.
- **Medium:** one context-dependent mechanism is present, but its source and resolved state are known.
- **High:** multiple mechanisms are present, a dependency is unresolved, or a prior cross-page comparison changed.

## Required handoff evidence

For medium or high risk, a future editing workflow should preserve source IDs and resolved modes, compare source and result bounds/structure, and perform a visual comparison. If a nested Instance cannot remain portable, recommend a `visual freeze required` review rather than silently detaching it.

Never treat a portability recommendation as permission to clone, detach, rasterize, move, or edit anything.
