# Component Library Organizer

A read-only audit skill for Figma component libraries. It inventories Components, Component Sets, and Instances; finds repeated Frame candidates; reviews variants and naming; filters internal layers; and assesses whether candidates can be copied safely into a shared library — all without modifying the source file.

## What it does

- **Strictly read-only**: uses only inspection, metadata, search, export, and screenshot operations. Never creates, deletes, renames, moves, detaches, swaps, publishes, or edits anything in the Figma document.
- **Evidence-backed inventory**: distinguishes main Components, Component Sets, Instances, and ordinary Frames; maps Instances to main Components by stable IDs.
- **Effective visibility**: calculates visibility through the full ancestor chain, including inherited opacity, so hidden-only families are never promoted to confirmed candidates.
- **Two-level clustering**: semantic name/role family first, then exact structural or visual-state clusters — same-name Frames with divergent structures are split, not merged.
- **Portability risk checks**: flags nested Instances, inherited variable modes, unavailable fonts, and unresolved remote assets before any copy-to-library workflow.
- **Deterministic reporting**: a stdlib-only helper script produces reproducible counts and grouping; design judgment is always labeled as inference.

## Repository layout

```
SKILL.md                        # Skill definition and workflow
agents/openai.yaml              # Agent-facing configuration
references/
  audit-method.md               # When a Frame counts as a candidate
  inventory-schema.md           # Normalized JSON schema for evidence
  portability-checks.md         # Copy-to-library risk checks
  report-format.md              # Required report structure
scripts/
  audit_inventory.py            # Deterministic audit script (stdlib only)
tests/
  test_audit_inventory.py       # Regression tests
  fixtures/untitled-known-scan.json
```

## Usage

Normalize Figma evidence to the schema in `references/inventory-schema.md`, then run:

```bash
python3 scripts/audit_inventory.py inventory.json --format markdown --output audit.md
```

Use `--format json` when another system will consume the audit.

## Tests

```bash
python3 tests/test_audit_inventory.py
```

## Safety boundary

This skill is an audit tool, not an editing tool. Recommendations describe a future library structure; they are never authorization to modify the file. If changes are requested, hand off to a separate editing workflow with an explicit edit request.

## License

MIT
