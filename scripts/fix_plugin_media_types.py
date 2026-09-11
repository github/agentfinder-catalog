#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

CLAUDE_PLUGIN_MEDIA_TYPE = "application/vnd.anthropic.claude-plugin+json"
CURSOR_PLUGIN_MEDIA_TYPE = "application/vnd.cursor.cursor-plugin+json"
PLUGIN_TYPES = {
    ".claude-plugin/plugin.json": ("claude", CLAUDE_PLUGIN_MEDIA_TYPE),
    ".cursor-plugin/plugin.json": ("cursor", CURSOR_PLUGIN_MEDIA_TYPE),
}
ROOT = Path(__file__).resolve().parents[1]


def plugin_type(entry):
    metadata = entry.get("metadata")
    paths = [entry.get("url")]
    if isinstance(metadata, dict):
        paths.append(metadata.get("repoPath"))

    for suffix, classified_type in PLUGIN_TYPES.items():
        if any(isinstance(path, str) and path.endswith(suffix) for path in paths):
            return classified_type
    return None


def fix_catalog(catalog_dir):
    counts = {"claude": 0, "cursor": 0}
    for path in sorted(catalog_dir.rglob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        classified_type = plugin_type(entry)
        if classified_type is None:
            continue

        name, media_type = classified_type
        counts[name] += 1
        if entry.get("mediaType") != media_type:
            entry["mediaType"] = media_type
            path.write_text(
                json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_dir", nargs="?", type=Path, default=ROOT / "catalog")
    args = parser.parse_args(argv)
    counts = fix_catalog(args.catalog_dir)
    print(f"Claude plugins found: {counts['claude']}")
    print(f"Cursor plugins found: {counts['cursor']}")


if __name__ == "__main__":
    main()