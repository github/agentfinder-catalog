import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDENTIFIER_PREFIX = "urn:ai:github.com:mattpocock:skills:"
PLUGIN_IDENTIFIER = IDENTIFIER_PREFIX + "mattpocock-skills"
PLUGIN_MEDIA_TYPE = "application/vnd.anthropic.claude-plugin+json"
RETIRED_SKILL_NAMES = ("grill-me", "grilling", "to-questionnaire", "wizard")


class MattPocockPluginRefsTest(unittest.TestCase):
    def setUp(self):
        self.entries = {}
        for path in sorted((ROOT / "catalog/mattpocock").glob("*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            self.entries[entry["identifier"]] = entry
        self.icons = json.loads(
            (ROOT / "catalog-icons.json").read_text(encoding="utf-8")
        )["icons"]

    def test_parent_plugin_targets_root_manifest(self):
        entry = self.entries[PLUGIN_IDENTIFIER]
        self.assertEqual(entry["displayName"], "Matt Pocock Skills")
        self.assertEqual(entry["mediaType"], PLUGIN_MEDIA_TYPE)
        self.assertEqual(
            entry["url"],
            "https://github.com/mattpocock/skills/blob/main/.claude-plugin/plugin.json",
        )
        self.assertEqual(
            entry["metadata"],
            {
                "sourceSet": "mattpocock/skills",
                "repoPath": ".claude-plugin/plugin.json",
            },
        )

    def test_bundled_skills_are_not_separate_entries(self):
        for name in RETIRED_SKILL_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(IDENTIFIER_PREFIX + name, self.entries)

    def test_nonbundled_skills_remain_cataloged(self):
        for name, repo_path in (
            ("claude-handoff", "skills/in-progress/claude-handoff/SKILL.md"),
            ("git-guardrails-claude-code", "skills/misc/git-guardrails-claude-code/SKILL.md"),
        ):
            with self.subTest(name=name):
                entry = self.entries[IDENTIFIER_PREFIX + name]
                self.assertEqual(entry["mediaType"], "application/ai-skill")
                self.assertEqual(entry["metadata"]["sourceSet"], "mattpocock/skills")
                self.assertEqual(entry["metadata"]["repoPath"], repo_path)
                self.assertEqual(
                    entry["url"], f"https://github.com/mattpocock/skills/blob/main/{repo_path}"
                )

    def test_reviewed_icon_targets_only_parent_plugin(self):
        prefix = IDENTIFIER_PREFIX.replace("urn:ai:", "urn:air:", 1)
        icons = [icon for icon in self.icons if icon["identifier"].startswith(prefix)]
        self.assertEqual(
            [icon["identifier"] for icon in icons],
            [PLUGIN_IDENTIFIER.replace("urn:ai:", "urn:air:", 1)],
        )
        self.assertTrue(icons[0]["url"].endswith("/icons/mattpocock/skills.png"))

    def test_generated_catalog_publishes_plugin_instead_of_bundled_skills(self):
        catalog = json.loads((ROOT / "ai-catalog.json").read_text(encoding="utf-8"))
        entries = {entry["identifier"]: entry for entry in catalog["entries"]}
        identifier = PLUGIN_IDENTIFIER.replace("urn:ai:", "urn:air:", 1)
        entry = entries[identifier]
        self.assertEqual(entry["type"], PLUGIN_MEDIA_TYPE)
        self.assertEqual(entry["url"], self.entries[PLUGIN_IDENTIFIER]["url"])
        for key in ("sourceSet", "repoPath"):
            self.assertEqual(entry["metadata"][key], self.entries[PLUGIN_IDENTIFIER]["metadata"][key])
        icon = next(icon for icon in self.icons if icon["identifier"] == identifier)
        self.assertEqual(entry["metadata"]["com.github.agentfinder.icon.url"], icon["url"])
        for name in RETIRED_SKILL_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(
                    (IDENTIFIER_PREFIX + name).replace("urn:ai:", "urn:air:", 1), entries
                )


if __name__ == "__main__":
    unittest.main()
