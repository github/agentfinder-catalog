import json
import unittest
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
SOURCE_SET = "github/awesome-copilot"
PUBLISHED_REF = "marketplace"

# awesome-copilot plugin manifests on main declare source compositions that are
# only assembled into self-contained packages on the marketplace branch.
PUBLISHED_CANVAS_PLUGINS = frozenset(
    (
        "accessibility-kanban",
        "apng-studio",
        "arcade-canvas",
        "backlog-swipe-triage",
        "backrooms-canvas",
        "chat-cards",
        "chromium-control-canvas",
        "color-orb",
        "diagram-viewer",
        "feedback-themes",
        "flight-map-canvas",
        "gesture-review",
        "java-modernization-studio",
        "pr-artifact-explorer",
        "release-notes-showcase",
        "repo-actions-hub",
        "sentry-triage",
        "signals-dashboard",
        "site-studio",
        "tiny-tool-town-submitter",
        "token-pacman",
        "where-was-i",
        "windows-app-storage-inspector-cleanup",
        "work-hub",
    )
)


def awesome_copilot_plugin_entries():
    entries = {}
    for path in sorted(CATALOG_DIR.glob("*/*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        metadata = entry.get("metadata") or {}
        repo_path = metadata.get("repoPath") or ""
        if metadata.get("sourceSet") == SOURCE_SET and repo_path.startswith("plugins/"):
            entries[path.relative_to(CATALOG_DIR).as_posix()] = entry
    return entries


class AwesomeCopilotPluginRefsTest(unittest.TestCase):
    def test_plugin_entries_target_published_packages(self):
        entries = awesome_copilot_plugin_entries()
        self.assertTrue(entries)
        for source, entry in entries.items():
            with self.subTest(source=source):
                repo_path = entry["metadata"]["repoPath"]
                self.assertEqual(
                    entry["url"],
                    f"https://github.com/{SOURCE_SET}/blob/{PUBLISHED_REF}/{repo_path}",
                )

    def test_published_canvas_plugins_remain_cataloged(self):
        entries = {
            entry["identifier"]: entry for entry in awesome_copilot_plugin_entries().values()
        }
        for name in sorted(PUBLISHED_CANVAS_PLUGINS):
            identifier = f"urn:ai:github.com:github:awesome-copilot:{name}"
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, entries)
                entry = entries[identifier]
                self.assertEqual(entry["mediaType"], "application/vnd.github.copilot-plugin")
                self.assertEqual(entry["metadata"]["repoPath"], f"plugins/{name}/plugin.json")
                self.assertEqual(
                    entry["url"],
                    f"https://github.com/{SOURCE_SET}/blob/{PUBLISHED_REF}/plugins/{name}/plugin.json",
                )


if __name__ == "__main__":
    unittest.main()
