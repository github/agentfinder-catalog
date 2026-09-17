import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import fix_plugin_media_types


class FixPluginMediaTypesTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.catalog_dir = Path(self.temporary_directory.name) / "catalog"

    def write_entry(self, relative_path, **overrides):
        entry = {
            "identifier": "urn:ai:github.com:example:plugins:test",
            "displayName": "Test Plugin",
            "mediaType": "application/vnd.github.copilot-plugin",
            "url": "https://github.com/example/plugins/blob/main/test",
        }
        entry.update(overrides)
        path = self.catalog_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        return path

    def test_updates_plugins_classified_by_repo_path_or_url(self):
        claude_path = self.write_entry(
            "nested/claude.json",
            metadata={"repoPath": "plugins/test/.claude-plugin/plugin.json"},
        )
        cursor_path = self.write_entry(
            "cursor.json",
            url=(
                "https://github.com/example/plugins/blob/main/"
                "test/.cursor-plugin/plugin.json"
            ),
        )
        copilot_path = self.write_entry(
            "copilot.json",
            metadata={"repoPath": "plugins/test/plugin.json"},
        )

        fix_plugin_media_types.fix_catalog(self.catalog_dir)

        self.assertEqual(
            json.loads(claude_path.read_text(encoding="utf-8"))["mediaType"],
            fix_plugin_media_types.CLAUDE_PLUGIN_MEDIA_TYPE,
        )
        self.assertEqual(
            json.loads(cursor_path.read_text(encoding="utf-8"))["mediaType"],
            fix_plugin_media_types.CURSOR_PLUGIN_MEDIA_TYPE,
        )
        self.assertEqual(
            json.loads(copilot_path.read_text(encoding="utf-8"))["mediaType"],
            "application/vnd.github.copilot-plugin",
        )

    def test_counts_every_found_plugin_including_already_correct_entries(self):
        self.write_entry(
            "claude.json",
            mediaType=fix_plugin_media_types.CLAUDE_PLUGIN_MEDIA_TYPE,
            metadata={"repoPath": ".claude-plugin/plugin.json"},
        )
        self.write_entry(
            "cursor.json",
            mediaType=fix_plugin_media_types.CURSOR_PLUGIN_MEDIA_TYPE,
            metadata={"repoPath": ".cursor-plugin/plugin.json"},
        )

        counts = fix_plugin_media_types.fix_catalog(self.catalog_dir)

        self.assertEqual(counts, {"claude": 1, "cursor": 1})

    def test_main_prints_total_counts_for_each_plugin_type(self):
        self.write_entry(
            "claude.json",
            metadata={"repoPath": ".claude-plugin/plugin.json"},
        )
        self.write_entry(
            "cursor.json",
            metadata={"repoPath": ".cursor-plugin/plugin.json"},
        )
        output = StringIO()

        with redirect_stdout(output):
            fix_plugin_media_types.main([str(self.catalog_dir)])

        self.assertEqual(
            output.getvalue(),
            "Claude plugins found: 1\nCursor plugins found: 1\n",
        )


if __name__ == "__main__":
    unittest.main()