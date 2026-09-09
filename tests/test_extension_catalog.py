import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_ai_catalog


class ExtensionCatalogTest(unittest.TestCase):
    def test_documented_contributor_template_is_canonical_and_valid(self):
        document = (generate_ai_catalog.ROOT / "CONTRIBUTING.md").read_text()
        match = re.search(r"```json\n(\{.*?\})\n```", document, re.DOTALL)
        self.assertIsNotNone(match)
        template = match.group(1)
        for placeholder, value in (
            ("<publisher>", "example"),
            ("<repo>", "resource-repository"),
            ("<augment-name>", "example-skill"),
        ):
            template = template.replace(placeholder, value)
        entry = json.loads(template)
        self.assertTrue(entry["identifier"].startswith("urn:air:"))
        self.assertIn("type", entry)
        self.assertNotIn("mediaType", entry)
        generate_ai_catalog.validate(entry, "CONTRIBUTING.md")

    def entry(self, prefix="urn:air:"):
        return {
            "identifier": prefix + "example.org:openenv:echo:" + "a" * 40,
            "displayName": "Echo",
            "type": "application/vnd.openenv.environment-card+json",
            "data": {
                "source": {
                    "uri": "https://github.com/example/envs.git",
                    "path": "envs/echo_env",
                    "revision": "a" * 40,
                },
                "license": "unknown",
                "interfaces": [{"role": "orchestration", "protocol": "openenv"}],
            },
            "representativeQueries": ["test client tool calls", "find a message echo environment"],
        }

    def generate(self, *entries):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publisher = root / "catalog" / "example"
            publisher.mkdir(parents=True)
            for index, entry in enumerate(entries):
                (publisher / f"entry-{index}.json").write_text(json.dumps(entry))
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
            ):
                return generate_ai_catalog.generate()

    def test_modern_inline_extension_round_trips_without_rewriting_its_subject(self):
        entry = self.entry()
        rendered, count = self.generate(entry)
        self.assertEqual(count, 1)
        result = json.loads(rendered)["entries"][0]
        self.assertEqual(result, entry)
        self.assertNotIn("url", result)

    def test_legacy_identifiers_are_normalized_without_double_prefixing(self):
        entry = self.entry("urn:ai:")
        rendered, _ = self.generate(entry)
        result = json.loads(rendered)["entries"][0]
        self.assertEqual(result["identifier"], self.entry()["identifier"])
        self.assertEqual(result["data"], entry["data"])

    def test_aliases_cannot_create_duplicate_generated_identities(self):
        with self.assertRaisesRegex(SystemExit, "duplicate"):
            self.generate(self.entry("urn:ai:"), self.entry())

    def test_two_revision_cards_remain_distinct(self):
        second = self.entry()
        second["identifier"] = second["identifier"][:-40] + "b" * 40
        second["data"]["source"]["revision"] = "b" * 40
        rendered, count = self.generate(self.entry(), second)
        self.assertEqual(count, 2)
        self.assertEqual(
            {entry["data"]["source"]["revision"] for entry in json.loads(rendered)["entries"]},
            {"a" * 40, "b" * 40},
        )


if __name__ == "__main__":
    unittest.main()
