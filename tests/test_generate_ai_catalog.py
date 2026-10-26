import hashlib
import io
import json
import re
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from PIL import Image

from scripts import generate_ai_catalog


class CatalogIconsTest(unittest.TestCase):
    COMMIT = "0123456789abcdef0123456789abcdef01234567"
    URL = (
        "https://raw.githubusercontent.com/github/agentfinder-catalog/"
        f"{COMMIT}/icons/example/weather.png"
    )
    IDENTIFIER = "urn:air:registry.modelcontextprotocol.io:example:weather"

    @staticmethod
    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    @classmethod
    def png(cls, width=1, height=1, pixel=b"\x00\x00\x00\xff", interlace=0):
        header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, interlace)
        pixels = (b"\x00" + pixel * width) * height
        return (
            b"\x89PNG\r\n\x1a\n" + cls.chunk(b"IHDR", header)
            + cls.chunk(b"IDAT", zlib.compress(pixels)) + cls.chunk(b"IEND", b"")
        )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.asset = self.root / "icons/example/weather.png"
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(self.png())
        self.overlay = self.root / "catalog-icons.json"
        self.source = self.root / "catalog/example"
        self.source.mkdir(parents=True)
        self.remote = {
            "identifier": "urn:ai:registry.modelcontextprotocol.io:example:weather",
            "displayName": "Weather",
            "type": "application/mcp-server+json",
            "version": "1.0.0",
            "url": "https://api.mcp.github.com/v0.1/servers/example%2Fweather/versions/1.0.0",
            "metadata": {
                "repository": "https://github.com/example/weather",
                "connectorId": "unchanged",
                "materialization": {"nativeUrl": "https://example.com/install"},
            },
        }
        self.local = {
            "identifier": "urn:ai:github.com:example:skills:weather",
            "displayName": "Weather skill",
            "mediaType": "application/ai-skill",
            "url": "https://github.com/example/skills/blob/main/weather/SKILL.md",
            "metadata": {"sourceSet": "example/skills", "repoPath": "weather/SKILL.md"},
        }
        (self.source / "weather.json").write_text(json.dumps(self.local), encoding="utf-8")
        for patcher in (
            patch.object(generate_ai_catalog, "ROOT", self.root),
            patch.object(generate_ai_catalog, "SOURCE_DIR", self.root / "catalog"),
            patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[self.remote]),
            patch.object(generate_ai_catalog, "load_mcp_registry_records", return_value=[]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def declaration(self, **changes):
        return {
            "identifier": self.IDENTIFIER,
            "url": self.URL,
            "provenance": {
                "sourceUrl": "https://example.com/weather-artwork",
                "license": "CC0-1.0",
                "permissionUrl": "https://example.com/weather-artwork-permission",
                "sha256": hashlib.sha256(self.asset.read_bytes()).hexdigest(),
            },
        } | changes

    def write_overlay(self, *declarations):
        self.overlay.write_text(json.dumps({"icons": declarations}), encoding="utf-8")

    def generate(self):
        rendered, count = generate_ai_catalog.generate()
        entries = json.loads(rendered)["entries"]
        self.assertEqual(len(entries), count)
        return rendered, entries

    def test_empty_and_absent_overlay_are_byte_identical(self):
        baseline, _ = self.generate()
        self.write_overlay()
        rendered, _ = self.generate()
        self.assertEqual(rendered, baseline)

    def test_local_and_imported_icons_preserve_every_other_field(self):
        _, baseline = self.generate()
        source_bytes = (self.source / "weather.json").read_bytes()
        remote_bytes = json.dumps(self.remote)
        local_id = self.local["identifier"].replace("urn:ai:", "urn:air:", 1)
        self.write_overlay(self.declaration(), self.declaration(identifier=local_id))
        rendered, entries = self.generate()
        self.assertEqual(len(entries), 2)
        self.assertNotIn(b"provenance", rendered)
        self.assertNotIn(b"metadata.github.icon.url", rendered)
        for before, after in zip(baseline, entries):
            self.assertEqual(
                after,
                before | {"metadata": before["metadata"] | {
                    generate_ai_catalog.ICON_METADATA_KEY: self.URL,
                }},
            )
        self.assertEqual((self.source / "weather.json").read_bytes(), source_bytes)
        self.assertEqual(json.dumps(self.remote), remote_bytes)
        self.write_overlay(self.declaration(identifier=local_id), self.declaration())
        self.assertEqual(self.generate()[0], rendered)

    def test_inline_data_and_missing_metadata_are_preserved(self):
        inline = self.local.copy()
        inline.pop("url")
        inline.pop("metadata")
        inline["data"] = {"nativeConfig": {"endpoint": "https://example.com/install"}}
        (self.source / "weather.json").write_text(json.dumps(inline), encoding="utf-8")
        _, baseline = self.generate()
        self.write_overlay(self.declaration(identifier=baseline[0]["identifier"]))
        _, entries = self.generate()
        self.assertEqual(entries[0], baseline[0] | {
            "metadata": {generate_ai_catalog.ICON_METADATA_KEY: self.URL},
        })
        self.assertEqual(entries[1], baseline[1])

    def test_exact_generated_fixture(self):
        self.remote.pop("metadata")
        self.write_overlay(self.declaration())
        _, entries = self.generate()
        self.assertEqual(entries[1], {
            "identifier": self.IDENTIFIER,
            "displayName": "Weather",
            "type": "application/mcp-server+json",
            "version": "1.0.0",
            "url": "https://api.mcp.github.com/v0.1/servers/example%2Fweather/versions/1.0.0",
            "metadata": {"com.github.agentfinder.icon.url": self.URL},
        })

    def test_local_shadowing_of_registry_entries_is_unchanged(self):
        self.remote["identifier"] = self.local["identifier"]
        identifier = self.local["identifier"].replace("urn:ai:", "urn:air:", 1)
        self.write_overlay(self.declaration(identifier=identifier))
        _, entries = self.generate()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], self.local["url"])

    def test_optional_version_and_registry_rollover(self):
        second = self.remote | {"version": "2.0.0", "url": self.remote["url"].replace("1.0.0", "2.0.0")}
        with patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[self.remote, second]):
            self.write_overlay(self.declaration(version="1.0.0"))
            _, entries = self.generate()
            self.assertIn(generate_ai_catalog.ICON_METADATA_KEY, entries[1]["metadata"])
            self.assertNotIn(generate_ai_catalog.ICON_METADATA_KEY, entries[2]["metadata"])
            self.write_overlay(self.declaration())
            _, entries = self.generate()
            self.assertTrue(all(
                entry["metadata"][generate_ai_catalog.ICON_METADATA_KEY] == self.URL
                for entry in entries[1:]
            ))
            self.write_overlay(self.declaration(version="1.0.0"), self.declaration(version="2.0.0"))
            _, exact = self.generate()
            self.assertEqual(exact, entries)
        with patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[second]):
            self.write_overlay(self.declaration())
            self.generate()
            self.write_overlay(self.declaration(version="1.0.0"))
            with self.assertRaisesRegex(SystemExit, r"icons\[0\].*unmatched.*1\.0\.0"):
                self.generate()

    def test_add_replace_remove_is_reversible_and_deterministic(self):
        baseline, _ = self.generate()
        self.write_overlay(self.declaration())
        added, _ = self.generate()
        self.assertNotEqual(added, baseline)
        self.assertEqual(added, self.generate()[0])
        self.asset.write_bytes(self.png(pixel=b"\xff\x00\x00\xff"))
        replacement = self.URL.replace(self.COMMIT, "f" * 40)
        self.write_overlay(self.declaration(url=replacement))
        replaced, entries = self.generate()
        self.assertNotEqual(added, replaced)
        self.assertEqual(entries[1]["metadata"][generate_ai_catalog.ICON_METADATA_KEY], replacement)
        self.write_overlay()
        self.assertEqual(self.generate()[0], baseline)

    def test_overlap_and_unmatched_declarations_fail(self):
        for declarations, message in (
            ([self.declaration(), self.declaration()], "overlapping"),
            ([self.declaration(), self.declaration(version="1.0.0")], "overlapping"),
            ([self.declaration(version="1.0.0"), self.declaration()], "overlapping"),
            ([self.declaration(version="1.0.0"), self.declaration(version="1.0.0")], "overlapping"),
            ([self.declaration(identifier=self.IDENTIFIER + "-missing")], "unmatched"),
        ):
            with self.subTest(declarations=declarations):
                self.write_overlay(*declarations)
                with self.assertRaisesRegex(SystemExit, message):
                    self.generate()

    def test_invalid_overlay_shapes_and_duplicate_keys(self):
        for document in (
            "{", "null", "[]", "{}", '{"icons":{}}', '{"icons":[],"other":1}',
            '{"icons":[],"icons":[]}', '{"icons":[{"identifier":"a","identifier":"b"}]}',
        ):
            with self.subTest(document=document):
                self.overlay.write_text(document, encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "catalog-icons.json"):
                    self.generate()
        for declaration in (
            None, [], {}, self.declaration(extra=True),
            self.declaration(identifier=self.remote["identifier"]),
            self.declaration(identifier=None),
            self.declaration(version=None), self.declaration(version=""), self.declaration(version=1),
        ):
            with self.subTest(declaration=declaration):
                self.write_overlay(declaration)
                with self.assertRaisesRegex(SystemExit, r"catalog-icons.json icons\[0\]"):
                    self.generate()

    def test_invalid_urls(self):
        for url in (
            None, 1, "", "/relative.png", self.URL.replace("https:", "http:"),
            self.URL.replace("raw.githubusercontent.com", "raw.githubusercontent.com.evil.test"),
            self.URL.replace("raw.githubusercontent.com", "github.com"),
            self.URL.replace("raw.githubusercontent.com", "raw.githubusercontent.com:443"),
            self.URL.replace("raw.githubusercontent.com", "user@raw.githubusercontent.com"),
            self.URL.replace("github/agentfinder-catalog", "other/repository"),
            self.URL.replace(self.COMMIT, "main"), self.URL.replace(self.COMMIT, "a" * 39),
            self.URL.replace("icons/example", "icons/../example"),
            self.URL.replace("weather.png", "%77eather.png"),
            self.URL.replace("weather.png", "weather.svg"),
            self.URL.replace("icons/example", "icons\\example"),
            self.URL + "?download=1", self.URL + "#image", self.URL + "?", self.URL + "#",
            self.URL.replace("https://", "https://[invalid/"), "\n" + self.URL,
        ):
            with self.subTest(url=url):
                self.write_overlay(self.declaration(url=url))
                with self.assertRaisesRegex(SystemExit, "url must"):
                    self.generate()

    def test_invalid_provenance_and_missing_assets(self):
        base = self.declaration()["provenance"]
        for provenance in (
            None, [], {}, base | {"extra": "field"}, base | {"license": ""},
            base | {"sourceUrl": "relative"}, base | {"permissionUrl": "http://example.com"},
            base | {"permissionUrl": "https://user@example.com"},
            base | {"sourceUrl": "https://example.com:443/file"},
            base | {"sourceUrl": "https://[invalid"}, base | {"sourceUrl": "https://example.com/a b"},
            base | {"sha256": "not-a-digest"}, base | {"sha256": "A" * 64},
            base | {"sha256": "a" * 64},
        ):
            with self.subTest(provenance=provenance):
                self.write_overlay(self.declaration(provenance=provenance))
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    self.generate()
        self.write_overlay(self.declaration(url=self.URL.replace("weather.png", "missing.png")))
        with self.assertRaisesRegex(SystemExit, "cannot read asset"):
            self.generate()

    def test_explicit_redistribution_approval_without_fabricated_license(self):
        provenance = self.declaration()["provenance"]
        provenance.pop("license")
        provenance.pop("permissionUrl")
        provenance["approval"] = "Selected artwork approved for public redistribution."
        self.write_overlay(self.declaration(provenance=provenance))
        rendered, _ = self.generate()
        self.assertNotIn(b"approval", rendered)
        for invalid in (
            provenance | {"approval": ""},
            provenance | {"approval": None},
            provenance | {"license": "invented"},
            {key: value for key, value in provenance.items() if key != "approval"},
        ):
            with self.subTest(provenance=invalid):
                self.write_overlay(self.declaration(provenance=invalid))
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    self.generate()

    def test_symlink_asset_and_overlay_rejected(self):
        link = self.asset.with_name("link.png")
        link.symlink_to(self.asset)
        self.write_overlay(self.declaration(url=self.URL.replace("weather.png", "link.png")))
        with self.assertRaisesRegex(SystemExit, "symlinks"):
            self.generate()
        (self.root / "icons/alias").symlink_to(self.root, target_is_directory=True)
        self.write_overlay(self.declaration(url=self.URL.replace("icons/example", "icons/alias")))
        with self.assertRaisesRegex(SystemExit, "symlinks"):
            self.generate()
        self.overlay.unlink()
        self.overlay.symlink_to(self.asset)
        with self.assertRaisesRegex(SystemExit, "overlay must not be a symlink"):
            self.generate()

    def test_asset_size_dimensions_and_png_integrity(self):
        for content, message in (
            (b"not a PNG", "invalid PNG"),
            (self.png(0, 1), "invalid PNG"), (self.png(513, 1), "dimensions"),
            (self.png(1, 513), "dimensions"),
            (self.png()[:30], "invalid PNG"),
            (self.png()[:-12], "invalid PNG"),
            (self.png().replace(b"IDAT", b"JDAT"), "invalid PNG"),
            (self.png() + b"\0" * generate_ai_catalog.MAX_ICON_BYTES, "exceeds"),
        ):
            with self.subTest(message=message):
                self.asset.write_bytes(content)
                self.write_overlay(self.declaration())
                with self.assertRaisesRegex(SystemExit, message):
                    self.generate()
        png = self.png()
        padding = self.chunk(b"tEXt", b"comment\0" + b"x" * (
            generate_ai_catalog.MAX_ICON_BYTES - len(png) - 12 - 8
        ))
        at_limit = png[:33] + padding + png[33:]
        self.assertEqual(len(at_limit), generate_ai_catalog.MAX_ICON_BYTES)
        for content in (self.png(512, 512), self.png(interlace=1), at_limit):
            self.asset.write_bytes(content)
            self.write_overlay(self.declaration())
            self.generate()

    def test_png_palette_and_adam7_layout(self):
        signature = b"\x89PNG\r\n\x1a\n"
        end = self.chunk(b"IEND", b"")
        indexed = self.chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 1, 3, 0, 0, 0))
        palette = self.chunk(b"PLTE", b"\0\0\0")
        data = self.chunk(b"IDAT", zlib.compress(b"\0\0"))
        rgba = self.chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 1))
        # A 2x2 Adam7 image has one pixel in passes 1 and 6, and two in pass 7.
        interlaced = self.chunk(b"IDAT", zlib.compress(
            b"\0" + b"\xff\0\0\xff" + b"\0" + b"\0\xff\0\xff"
            + b"\0" + b"\xff\0\0\xff" + b"\0\xff\0\xff"
        ))
        for chunks in ([indexed, palette, data, end], [rgba, interlaced, end]):
            self.asset.write_bytes(signature + b"".join(chunks))
            self.write_overlay(self.declaration())
            self.generate()

    def test_png_decode_errors_are_rejected(self):
        header = self.chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        signature = b"\x89PNG\r\n\x1a\n"
        end = self.chunk(b"IEND", b"")
        for chunks in (
            [header, self.chunk(b"IDAT", zlib.compress(b"\x05" + b"\0" * 4)), end],
            [header, self.chunk(b"IDAT", b"not compressed image data"), end],
            [header, end],
            [self.chunk(b"IDAT", zlib.compress(b"\0" * 5)), header, end],
        ):
            with self.subTest(chunks=chunks):
                self.asset.write_bytes(signature + b"".join(chunks))
                self.write_overlay(self.declaration())
                with self.assertRaisesRegex(SystemExit, "invalid PNG"):
                    self.generate()

    def test_animation_and_other_formats_are_rejected(self):
        first = Image.new("RGBA", (2, 2), "red")
        second = Image.new("RGBA", (2, 2), "blue")
        animated = io.BytesIO()
        first.save(animated, format="PNG", save_all=True, append_images=[second])
        gif = io.BytesIO()
        first.save(gif, format="GIF")
        for content, message in (
            (animated.getvalue(), "animated PNG"),
            (gif.getvalue(), "invalid PNG"),
        ):
            self.asset.write_bytes(content)
            self.write_overlay(self.declaration())
            with self.assertRaisesRegex(SystemExit, message):
                self.generate()

    def test_reserved_key_cannot_bypass_overlay_review(self):
        self.local["metadata"][generate_ai_catalog.ICON_METADATA_KEY] = self.URL
        (self.source / "weather.json").write_text(json.dumps(self.local), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "must be declared through catalog-icons.json"):
            self.generate()
        self.local["metadata"].pop(generate_ai_catalog.ICON_METADATA_KEY)
        (self.source / "weather.json").write_text(json.dumps(self.local), encoding="utf-8")
        self.remote["metadata"][generate_ai_catalog.ICON_METADATA_KEY] = self.URL
        with self.assertRaisesRegex(SystemExit, "must be declared through catalog-icons.json"):
            self.generate()


class ValidateEntryTest(unittest.TestCase):
    @staticmethod
    def canvas_entry():
        return {
            "identifier": "urn:ai:example.com:test:canvas",
            "displayName": "Test Canvas",
            "mediaType": generate_ai_catalog.CANVAS_PLUGIN_MEDIA_TYPE,
            "url": (
                "https://github.com/owner/repository/blob/main/"
                "plugins/canvas/plugin.json"
            ),
            "tags": sorted(generate_ai_catalog.CANVAS_ONLY_REQUIRED_TAGS),
            "metadata": {
                "sourceSet": "owner/repository",
                "repoPath": "plugins/canvas/plugin.json",
            },
        }

    def test_display_name_precedence(self):
        entry = {"displayName": "owner/repo", "title": "Catalog title", "name": "server-name"}
        registry_record = {
            "server": {
                "title": "Registry title",
                "_meta": {
                    "io.modelcontextprotocol.registry/publisher-provided": {
                        "github": {"displayName": "GitHub display name"}
                    }
                },
            }
        }
        self.assertEqual(
            generate_ai_catalog.display_name(entry, registry_record),
            "GitHub display name",
        )
        self.assertEqual(
            generate_ai_catalog.display_name(entry, {"server": {"title": "Registry title"}}),
            "Registry title",
        )
        self.assertEqual(
            generate_ai_catalog.display_name(
                entry,
                {
                    "server": {
                        "title": "Registry title",
                        "_meta": {
                            "io.modelcontextprotocol.registry/publisher-provided": {
                                "github": None,
                            }
                        },
                    }
                },
            ),
            "Registry title",
        )
        self.assertEqual(
            generate_ai_catalog.display_name(entry, {}),
            "Catalog title",
        )
        self.assertEqual(
            generate_ai_catalog.display_name({"displayName": "owner/repo"}, {}),
            "owner/repo",
        )

    def test_registry_record_key_from_version_url(self):
        entry = {
            "url": (
                "https://api.mcp.github.com/v0.1/servers/"
                "microsoft%2Fmarkitdown/versions/1.0.0"
            )
        }
        self.assertEqual(
            generate_ai_catalog.registry_record_key(entry),
            ("microsoft/markitdown", "1.0.0"),
        )

    def test_url_or_data(self):
        entry = {
            "identifier": "urn:ai:example.com:test:item",
            "displayName": "Test",
            "type": "application/example",
        }
        for delivery in (
            {"url": ""},
            {"url": "relative"},
            {"url": 1},
            {"data": "value"},
            {},
            {"url": "https://example.com", "data": {}},
        ):
            with self.subTest(delivery=delivery), self.assertRaises(SystemExit):
                generate_ai_catalog.validate(entry | delivery, "test")

        generate_ai_catalog.validate(entry | {"url": "https://example.com"}, "test")
        generate_ai_catalog.validate(entry | {"data": {}}, "test")

    def test_valid_canvas_only_entry(self):
        entry = self.canvas_entry()
        generate_ai_catalog.validate(entry, "test")

    def test_canvas_only_entry_requires_each_contract_tag(self):
        tags = generate_ai_catalog.CANVAS_ONLY_REQUIRED_TAGS
        for missing_tag in sorted(tags):
            with self.subTest(missing_tag=missing_tag), self.assertRaisesRegex(
                SystemExit, rf"missing required tags {missing_tag}"
            ):
                generate_ai_catalog.validate_canvas_only_tags(
                    tags - {missing_tag}, "test"
                )

    def test_canvas_only_entry_requires_generic_plugin_media_type(self):
        with self.assertRaisesRegex(SystemExit, "must use mediaType"):
            generate_ai_catalog.validate(
                self.canvas_entry() | {"mediaType": "application/ai-skill"},
                "test",
            )
        with self.assertRaisesRegex(SystemExit, "type must match mediaType"):
            generate_ai_catalog.validate(
                self.canvas_entry() | {"type": "application/ai-skill"},
                "test",
            )

    def test_claude_layout_canvas_only_entry_requires_claude_plugin_media_type(self):
        claude_layout = {
            "url": (
                "https://github.com/owner/repository/blob/main/"
                ".claude-plugin/plugin.json"
            ),
            "metadata": {
                "sourceSet": "owner/repository",
                "repoPath": ".claude-plugin/plugin.json",
            },
        }
        entry = self.canvas_entry() | claude_layout
        with self.assertRaisesRegex(
            SystemExit,
            f"must use mediaType {re.escape(generate_ai_catalog.CLAUDE_PLUGIN_MEDIA_TYPE)}",
        ):
            generate_ai_catalog.validate(entry, "test")

        generate_ai_catalog.validate(
            entry | {"mediaType": generate_ai_catalog.CLAUDE_PLUGIN_MEDIA_TYPE},
            "test",
        )
        with self.assertRaisesRegex(SystemExit, "type must match mediaType"):
            generate_ai_catalog.validate(
                entry
                | {
                    "mediaType": generate_ai_catalog.CLAUDE_PLUGIN_MEDIA_TYPE,
                    "type": generate_ai_catalog.CANVAS_PLUGIN_MEDIA_TYPE,
                },
                "test",
            )

    def test_mixed_plugin_cannot_be_marked_canvas_only(self):
        with self.assertRaisesRegex(SystemExit, "non-Canvas capability tags agent"):
            generate_ai_catalog.validate(
                self.canvas_entry()
                | {
                    "tags": [
                        "agent",
                        *sorted(generate_ai_catalog.CANVAS_ONLY_REQUIRED_TAGS),
                    ]
                },
                "test",
            )

    def test_canvas_classification_is_not_name_based(self):
        generate_ai_catalog.validate(
            {
                "identifier": "urn:ai:example.com:test:not-classified",
                "displayName": "Canvas-only in name",
                "mediaType": "application/ai-skill",
                "url": "https://example.com/canvas-only",
                "description": "Mentions a canvas without declaring the contract.",
            },
            "test",
        )

    def test_rejects_invalid_tags_url_and_repository_path(self):
        entry = self.canvas_entry()
        invalid_entries = (
            (entry | {"tags": "canvas"}, "tags must be an array"),
            (entry | {"tags": ["canvas", ""]}, "array of non-empty strings"),
            (entry | {"tags": ["canvas", "canvas"]}, "must not contain duplicates"),
            (entry | {"version": ""}, "version must be a non-empty string"),
            (
                entry | {"url": "https://user:secret@example.com/plugin"},
                "must not contain credentials",
            ),
            (
                entry | {"url": "https://example.com\\@attacker.test/plugin"},
                "must be an absolute HTTP",
            ),
            (
                entry | {"url": "https://[invalid/plugin"},
                "must be a valid absolute HTTP",
            ),
            (
                entry
                | {
                    "url": (
                        "https://github.com:notaport/owner/repository/blob/main/"
                        "plugins/canvas/plugin.json"
                    )
                },
                "must be a valid absolute HTTP",
            ),
            (
                entry
                | {
                    "url": (
                        "https://github.com:99999/owner/repository/blob/main/"
                        "plugins/canvas/plugin.json"
                    )
                },
                "must be a valid absolute HTTP",
            ),
            (
                entry
                | {
                    "url": (
                        "https://github.com/owner/repository/blob/main/"
                        "plugins/other/plugin.json"
                    )
                },
                "must point to metadata.repoPath",
            ),
            (
                entry
                | {
                    "metadata": {
                        "sourceSet": "owner/repository",
                        "repoPath": "../plugin.json",
                    }
                },
                "safe relative POSIX path",
            ),
            (
                entry
                | {
                    "metadata": {
                        "sourceSet": "owner/repository",
                        "repoPath": "plugins/%2e%2e/README.md",
                    },
                    "url": (
                        "https://github.com/owner/repository/blob/main/"
                        "plugins/%2e%2e/README.md"
                    ),
                },
                "safe relative POSIX path",
            ),
            (
                entry
                | {
                    "metadata": {
                        "sourceSet": "owner/repository",
                        "repoPath": "README.md",
                    },
                    "url": (
                        "https://github.com/owner/repository/blob/main/"
                        "plugins/%2e%2e/README.md"
                    ),
                },
                "must point to metadata.repoPath",
            ),
        )
        for invalid, message in invalid_entries:
            with self.subTest(message=message), self.assertRaisesRegex(
                SystemExit, message
            ):
                generate_ai_catalog.validate(invalid, "test")

    def test_generated_type_falls_back_to_media_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            entry = {
                "identifier": "urn:ai:example.com:test:item",
                "displayName": "Test",
                "type": "",
                "mediaType": "application/example",
                "url": "https://example.com",
            }
            (source / "item.json").write_text(json.dumps(entry), encoding="utf-8")
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
            ):
                rendered, _ = generate_ai_catalog.generate()

        self.assertEqual(json.loads(rendered)["entries"][0]["type"], "application/example")

    def test_generated_mcp_entry_uses_registry_github_display_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            (source / "item.json").write_text(
                json.dumps(
                    {
                        "identifier": "urn:ai:example.com:test:item",
                        "displayName": "Test",
                        "type": "application/example",
                        "url": "https://example.com",
                    }
                ),
                encoding="utf-8",
            )
            remote = {
                "identifier": "urn:ai:registry.modelcontextprotocol.io:owner:repo",
                "displayName": "owner/repo",
                "type": "application/mcp-server+json",
                "url": (
                    "https://api.mcp.github.com/v0.1/servers/"
                    "owner%2Frepo/versions/1.0.0"
                ),
                "version": "1.0.0",
            }
            registry_record = {
                "server": {
                    "name": "owner/repo",
                    "version": "1.0.0",
                    "title": "Registry title",
                    "_meta": {
                        "io.modelcontextprotocol.registry/publisher-provided": {
                            "github": {"displayName": "Publisher display name"}
                        }
                    },
                }
            }
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[remote]),
                patch.object(
                    generate_ai_catalog,
                    "load_mcp_registry_records",
                    return_value=[registry_record],
                ),
            ):
                rendered, _ = generate_ai_catalog.generate()

        entries = json.loads(rendered)["entries"]
        self.assertEqual(entries[1]["displayName"], "Publisher display name")

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            for filename, identifier in (
                ("zeta.json", "urn:ai:example.com:test:zeta"),
                ("alpha.json", "urn:ai:example.com:test:alpha"),
            ):
                (source / filename).write_text(
                    json.dumps(
                        {
                            "identifier": identifier,
                            "displayName": filename,
                            "mediaType": "application/ai-skill",
                            "url": f"https://example.com/{filename}",
                        }
                    ),
                    encoding="utf-8",
                )
            remote_entries = [
                {
                    "identifier": f"urn:ai:example.com:remote:{name}",
                    "displayName": name,
                    "type": "application/mcp-server+json",
                    "url": f"https://example.com/{name}",
                }
                for name in ("zeta", "alpha")
            ]
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(
                    generate_ai_catalog,
                    "load_mcp_entries",
                    side_effect=[remote_entries, list(reversed(remote_entries))],
                ),
                patch.object(
                    generate_ai_catalog,
                    "load_mcp_registry_records",
                    return_value=[],
                ),
            ):
                first, _ = generate_ai_catalog.generate()
                second, _ = generate_ai_catalog.generate()

        self.assertEqual(first, second)

    def test_registry_only_addition_and_version_update_refresh_catalog(self):
        def remote_entry(name, version):
            return {
                "identifier": f"urn:ai:registry.modelcontextprotocol.io:example:{name}",
                "displayName": name,
                "type": "application/mcp-server+json",
                "url": (
                    "https://api.mcp.github.com/v0.1/servers/"
                    f"example%2F{name}/versions/{version}"
                ),
                "version": version,
            }

        old = remote_entry("existing", "1.0.0")
        updated = remote_entry("existing", "2.0.0")
        added = remote_entry("new", "1.0.0")
        local = {
            "identifier": "urn:ai:example.com:local:skill",
            "displayName": "Local skill",
            "mediaType": "application/ai-skill",
            "url": "https://example.com/skill",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            path = source / "skill.json"
            path.write_text(json.dumps(local), encoding="utf-8")
            original_source = path.read_bytes()
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(
                    generate_ai_catalog,
                    "load_mcp_entries",
                    side_effect=[[old], [updated, added], [added, updated]],
                ),
                patch.object(
                    generate_ai_catalog, "load_mcp_registry_records", return_value=[]
                ),
            ):
                before, _ = generate_ai_catalog.generate()
                after, count = generate_ai_catalog.generate()
                repeated, _ = generate_ai_catalog.generate()
            self.assertEqual(path.read_bytes(), original_source)

        self.assertNotEqual(before, after)
        self.assertEqual(after, repeated)
        self.assertEqual(count, 3)
        entries = json.loads(after)["entries"]
        self.assertEqual(entries[0]["url"], local["url"])
        remote = {entry["displayName"]: entry for entry in entries[1:]}
        self.assertEqual(remote["existing"]["version"], "2.0.0")
        self.assertEqual(remote["existing"]["url"], updated["url"])
        self.assertEqual(remote["new"]["url"], added["url"])
        self.assertNotIn(old["url"], [entry["url"] for entry in entries])

    def test_power_bi_uses_only_registry_entry_across_version_updates(self):
        for version in ("1.0.0", "2.0.0"):
            with self.subTest(version=version):
                remote = {
                    "identifier": (
                        "urn:ai:registry.modelcontextprotocol.io:"
                        "com.microsoft:powerbi-modeling-mcp"
                    ),
                    "displayName": "Power BI Authoring MCP Server (Local)",
                    "type": "application/mcp-server+json",
                    "url": (
                        "https://api.mcp.github.com/v0.1/servers/"
                        f"com.microsoft%2Fpowerbi-modeling-mcp/versions/{version}"
                    ),
                    "version": version,
                    "metadata": {
                        "repository": "https://github.com/microsoft/powerbi-modeling-mcp.git",
                        "repositorySource": "github",
                    },
                }
                with (
                    patch.object(
                        generate_ai_catalog, "load_icon_declarations", return_value=[]
                    ),
                    patch.object(
                        generate_ai_catalog, "load_mcp_entries", return_value=[remote]
                    ),
                    patch.object(
                        generate_ai_catalog, "load_mcp_registry_records", return_value=[]
                    ),
                ):
                    rendered, _ = generate_ai_catalog.generate()

                power_bi_entries = [
                    entry
                    for entry in json.loads(rendered)["entries"]
                    if entry["type"] == "application/mcp-server+json"
                    and "powerbi-modeling-mcp" in entry["identifier"]
                ]
                self.assertEqual(
                    power_bi_entries,
                    [
                        remote
                        | {
                            "identifier": (
                                "urn:air:registry.modelcontextprotocol.io:"
                                "com.microsoft:powerbi-modeling-mcp"
                            )
                        }
                    ],
                )

    def test_generated_canvas_only_filter_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            canvas = self.canvas_entry()
            (source / "canvas.json").write_text(
                json.dumps(canvas),
                encoding="utf-8",
            )
            (source / "mixed.json").write_text(
                json.dumps(
                    {
                        "identifier": "urn:ai:example.com:test:mixed",
                        "displayName": "Mixed plugin",
                        "mediaType": generate_ai_catalog.CANVAS_PLUGIN_MEDIA_TYPE,
                        "url": "https://example.com/mixed",
                        "tags": ["canvas", "github-copilot"],
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
            ):
                rendered, _ = generate_ai_catalog.generate()

        entries = json.loads(rendered)["entries"]
        matches = [
            entry
            for entry in entries
            if entry["type"] == generate_ai_catalog.CANVAS_PLUGIN_MEDIA_TYPE
            and generate_ai_catalog.CANVAS_ONLY_REQUIRED_TAGS.issubset(
                entry.get("tags", ())
            )
        ]
        self.assertEqual(
            [entry["identifier"] for entry in matches],
            ["urn:air:example.com:test:canvas"],
        )

    def test_duplicate_entries_report_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            entry = {
                "identifier": "urn:ai:example.com:test:duplicate",
                "displayName": "Duplicate",
                "mediaType": "application/ai-skill",
                "url": "https://example.com/duplicate",
            }
            for filename in ("first.json", "second.json"):
                (source / filename).write_text(json.dumps(entry), encoding="utf-8")
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
                self.assertRaisesRegex(
                    SystemExit,
                    r"catalog/example/second\.json: duplicate identifier/version identity",
                ),
            ):
                generate_ai_catalog.generate()

    def test_invalid_json_reports_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog" / "example"
            source.mkdir(parents=True)
            (source / "invalid.json").write_text("{", encoding="utf-8")
            with (
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
                self.assertRaisesRegex(
                    SystemExit, r"catalog/example/invalid\.json: invalid JSON"
                ),
            ):
                generate_ai_catalog.generate()

    def test_load_mcp_registry_records_paginates_with_next_cursor(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self.payload

        first_page = {
            "servers": [{"server": {"name": "alpha", "version": "1.0.0"}}],
            "metadata": {"nextCursor": "page-two"},
        }
        second_page = {
            "servers": [{"server": {"name": "beta", "version": "2.0.0"}}],
            "metadata": {},
        }
        with patch.object(
            generate_ai_catalog,
            "urlopen",
            side_effect=[FakeResponse(first_page), FakeResponse(second_page)],
        ) as mocked_urlopen:
            records = generate_ai_catalog.load_mcp_registry_records()

        self.assertEqual(
            records,
            [
                {"server": {"name": "alpha", "version": "1.0.0"}},
                {"server": {"name": "beta", "version": "2.0.0"}},
            ],
        )
        self.assertEqual(mocked_urlopen.call_count, 2)

        first_url = mocked_urlopen.call_args_list[0].args[0].full_url
        second_url = mocked_urlopen.call_args_list[1].args[0].full_url
        self.assertEqual(parse_qs(urlparse(first_url).query), {"limit": ["100"]})
        self.assertEqual(parse_qs(urlparse(second_url).query), {"limit": ["100"], "cursor": ["page-two"]})


if __name__ == "__main__":
    unittest.main()
