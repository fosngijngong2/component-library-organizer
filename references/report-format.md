# Audit report format

Read this reference immediately before writing the final audit. Use the user's language and keep the report comparable across future scans.

## Required sections

### Header

Include `Component Library Audit`, file identity, scope, `Mode: Read-only`, coverage, evidence source, and scan date when known.

### Inventory

Show separate totals for Components, Component Sets, Instances, Frames, Variables, local Text Styles, and local Effect Styles. Mark every non-exact value with `~` or `estimated`. If supplied totals disagree with a complete node inventory, show both and flag the mismatch.

### Existing components

List Component Sets first, including axes and variant counts, then standalone Components. Include node IDs when available. Do not imply selected examples are the complete list.

### Instance reuse

Show total Instances, top source Components when resolvable, and unresolved relationships. If only an aggregate total is available, say source-level mapping was not inspected.

### Candidate components

For each confirmed visible candidate include name, recurrence count and exactness, confidence, semantic-family total, number of structural clusters, evidence, ambiguities, and representative node IDs when available.

### Hidden-only candidates

List families whose matching representatives are all hidden or effectively transparent. Include the ancestor-based exclusion reason. Do not combine these counts with confirmed visible candidates.

### Portability risks

When the audit feeds a later copy-to-library workflow, list medium/high risks from nested Instances, inherited variable modes, unavailable fonts, or unresolved styles. Label any required visual freeze or comparison as a future handoff gate, not an audit action.

### Naming and variant issues

Use severity only to prioritize review. Separate variant coverage gaps from confirmed duplicates or inconsistent combinations.

### Ignored internal layers

List representative filtered names and why they were filtered. State that nothing was deleted.

### Recommended structure

Show a compact proposed hierarchy only where evidence supports it. Label it `Proposal` and keep it separate from observed facts.

### Limitations and next step

State unscanned pages, truncated metadata, missing IDs, approximate counts, and analysis that needs a narrower rescan. The audit normally ends with a focused read-only scan of the highest-value candidate family—not an automatic rewrite.

## Minimum output example

```text
Component Library Audit
Mode: Read-only
Coverage: Partial — selected page and known whole-file totals

Inventory
- Components: 16
- Component Sets: 7
- Instances: 17,007
- Frames: 45,637

Existing components
- Send Button — Component Set, 3 variants

Candidate components
- Chat Item — ~500 occurrences, High confidence
  Evidence: repeated name, consistent child structure

Ignored internal layers
- Container, BG, Frame 2131176441
  Filtered from candidate results; nothing was deleted.

Recommended structure — Proposal
Input
├─ Theme: Light | Dark
└─ State: Default | Active | Disabled
```
