import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_inventory.py"
SPEC = importlib.util.spec_from_file_location("audit_inventory", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class AuditInventoryTests(unittest.TestCase):
    def test_known_scan_fixture_preserves_counts_and_estimates(self):
        fixture = ROOT / "tests" / "fixtures" / "untitled-known-scan.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        report = MODULE.audit_document(data)

        self.assertEqual(report["mode"], "read-only")
        self.assertEqual(report["summary"]["components"], 16)
        self.assertEqual(report["summary"]["component_sets"], 7)
        self.assertEqual(report["summary"]["instances"], 17007)
        self.assertEqual(report["summary"]["frames"], 45637)
        self.assertEqual(report["benchmark"]["confirmed_visible_families"], 62)
        self.assertEqual(report["benchmark"]["hidden_only_candidate_families"], 24)
        candidates = {item["name"]: item for item in report["candidates"]}
        self.assertEqual(candidates["聊天item"]["count_kind"], "estimated")
        self.assertEqual(candidates["输入框"]["count"], 254)
        markdown = MODULE.render_markdown(report)
        self.assertIn("Mode: Read-only", markdown)
        self.assertIn("~500 occurrences", markdown)
        self.assertIn("Nothing was deleted or modified.", markdown)

    def test_raw_nodes_detect_candidates_instances_and_variant_data(self):
        nodes = [
            {"id": "set", "name": "Button", "type": "COMPONENT_SET"},
            {"id": "c1", "parent_id": "set", "name": "State=Default", "type": "COMPONENT", "variant_properties": {"State": "Default"}},
            {"id": "c2", "parent_id": "set", "name": "State=Active", "type": "COMPONENT", "variant_properties": {"State": "Active"}},
            {"id": "i1", "name": "Button", "type": "INSTANCE", "component_id": "c1"},
            {"id": "i2", "name": "Missing", "type": "INSTANCE", "component_id": "missing"}
        ]
        nodes.extend({"id": f"page-{index}", "name": f"page-{index}", "type": "SECTION"} for index in range(2))
        for index in range(4):
            parent = f"page-{index % 2}"
            nodes.extend([
                {"id": f"chat-{index}", "parent_id": parent, "name": "Chat Item", "type": "FRAME", "width": 320, "height": 64},
                {"id": f"text-{index}", "parent_id": f"chat-{index}", "name": "Message", "type": "TEXT", "width": 200, "height": 20}
            ])
        nodes.append({"id": "noise", "name": "Frame 123", "type": "FRAME", "width": 10, "height": 10})
        data = {"schema_version": "1.0", "file": {"coverage": "complete", "source": "test"}, "nodes": nodes}

        report = MODULE.audit_document(data)
        self.assertEqual(report["summary"]["component_sets"], 1)
        self.assertEqual(report["instance_audit"]["unresolved"], 1)
        self.assertTrue(any(item["name"] == "Chat Item" and item["count"] == 4 for item in report["candidates"]))
        self.assertTrue(any(item["name"] == "Frame 123" for item in report["ignored"]))

    def test_effective_visibility_separates_hidden_only_families(self):
        nodes = [
            {"id": "page", "name": "Page", "type": "PAGE"},
            {"id": "visible-screen", "parent_id": "page", "name": "Screen", "type": "SECTION"},
            {"id": "hidden-screen", "parent_id": "page", "name": "Legacy", "type": "SECTION", "visible": False},
            {"id": "transparent-screen", "parent_id": "page", "name": "Draft", "type": "SECTION", "opacity": 0},
        ]
        for index in range(3):
            nodes.append({
                "id": f"visible-{index}", "parent_id": "visible-screen", "name": "Toolbar",
                "type": "FRAME", "width": 320, "height": 44,
            })
            nodes.append({
                "id": f"hidden-{index}", "parent_id": "hidden-screen", "name": "Legacy Header",
                "type": "FRAME", "width": 320, "height": 44,
            })
            nodes.append({
                "id": f"transparent-{index}", "parent_id": "transparent-screen", "name": "Ghost Header",
                "type": "FRAME", "width": 320, "height": 44,
            })
        report = MODULE.audit_document({
            "schema_version": "1.1", "file": {"coverage": "complete", "source": "test"}, "nodes": nodes,
        })

        self.assertEqual({item["name"] for item in report["candidates"]}, {"Toolbar"})
        self.assertEqual(
            {item["name"] for item in report["hidden_candidates"]}, {"Legacy Header", "Ghost Header"}
        )
        self.assertTrue(all(item["visibility"] == "hidden-only" for item in report["hidden_candidates"]))

    def test_same_name_structures_are_split_and_flagged(self):
        nodes = [{"id": "page", "name": "Page", "type": "PAGE"}]
        for index in range(3):
            nodes.extend([
                {"id": f"a-{index}", "parent_id": "page", "name": "Input", "type": "FRAME", "width": 320, "height": 44},
                {"id": f"a-text-{index}", "parent_id": f"a-{index}", "name": "Value", "type": "TEXT", "width": 200, "height": 20},
                {"id": f"b-{index}", "parent_id": "page", "name": "Input", "type": "FRAME", "width": 320, "height": 44},
                {"id": f"b-icon-{index}", "parent_id": f"b-{index}", "name": "Icon", "type": "VECTOR", "width": 20, "height": 20},
                {"id": f"b-text-{index}", "parent_id": f"b-{index}", "name": "Value", "type": "TEXT", "width": 200, "height": 20},
            ])
        report = MODULE.audit_document({
            "schema_version": "1.1", "file": {"coverage": "complete", "source": "test"}, "nodes": nodes,
        })
        inputs = [item for item in report["candidates"] if item["name"] == "Input"]
        self.assertEqual(len(inputs), 2)
        self.assertTrue(all(item["structural_cluster_count"] == 2 for item in inputs))
        self.assertTrue(all(item.get("ambiguity") for item in inputs))

    def test_portability_risk_is_reported_without_mutation(self):
        nodes = [{"id": "page", "name": "Page", "type": "PAGE"}]
        for index in range(3):
            nodes.append({
                "id": f"bar-{index}", "parent_id": "page", "name": "Main Bar", "type": "FRAME",
                "width": 288, "height": 62, "nested_instance_count": 2,
                "variable_binding_count": 3, "inherits_variable_modes": True,
            })
        report = MODULE.audit_document({
            "schema_version": "1.1", "file": {"coverage": "complete", "source": "test"}, "nodes": nodes,
        })
        self.assertEqual(report["mode"], "read-only")
        self.assertEqual(report["portability_risks"][0]["risk"], "high")
        self.assertIn("visual freeze", MODULE.render_markdown(report).lower())


if __name__ == "__main__":
    unittest.main()
