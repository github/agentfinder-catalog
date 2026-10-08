import json
import unittest
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
SOURCE_SET = "microsoft/skills-for-fabric"
MANIFEST_PATH = "plugins/fabric-skills/.github/plugin/plugin.json"
ALIASES = {
    "fabric-authoring": "Fabric Authoring",
    "fabric-consumption": "Fabric Consumption",
    "fabric-operations": "Fabric Operations",
}


class FabricPluginRefsTest(unittest.TestCase):
    def test_aliases_target_shared_fabric_skills_manifest(self):
        # The upstream marketplace maps all three persona aliases to fabric-skills.
        for name, display_name in ALIASES.items():
            with self.subTest(alias=name):
                entry = json.loads(
                    (CATALOG_DIR / "microsoft" / f"{name}.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    entry["identifier"], f"urn:ai:github.com:microsoft:skills-for-fabric:{name}"
                )
                self.assertEqual(entry["displayName"], display_name)
                self.assertEqual(entry["mediaType"], "application/vnd.github.copilot-plugin")
                self.assertEqual(entry["metadata"]["sourceSet"], SOURCE_SET)
                self.assertEqual(entry["metadata"]["repoPath"], MANIFEST_PATH)
                self.assertEqual(
                    entry["url"],
                    f"https://github.com/{SOURCE_SET}/blob/main/{MANIFEST_PATH}",
                )


if __name__ == "__main__":
    unittest.main()
