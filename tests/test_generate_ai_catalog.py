import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from scripts import generate_ai_catalog


class ValidateEntryTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.annotations_file = Path(directory.name) / "connector-annotations.json"
        self.enterContext(
            patch.object(generate_ai_catalog, "ANNOTATIONS_FILE", self.annotations_file)
        )

    def test_connector_annotations_preserve_remote_entries(self):
        identifier = "urn:ai:example.com:remote:connector"
        hints = {
            "aliases": ["example"],
            "fileExtensions": [],
            "urlDomains": ["example.com"],
        }
        self.annotations_file.write_text(
            json.dumps({identifier: {"connectorName": "example", "matchHints": hints}}),
            encoding="utf-8",
        )
        for tags in (None, [], ["mcp-server"], ["connector-available"]):
            with self.subTest(tags=tags):
                remote = [
                    {
                        "identifier": identifier,
                        "displayName": "Example",
                        "type": "application/mcp-server+json",
                        "url": f"https://example.com/{version}",
                        "version": version,
                        **({"tags": tags} if tags is not None else {}),
                    }
                    for version in ("1.0.0", "2.0.0")
                ]
                original = json.loads(json.dumps(remote))
                with (
                    patch.object(
                        generate_ai_catalog,
                        "SOURCE_DIR",
                        self.annotations_file.parent / "catalog",
                    ),
                    patch.object(generate_ai_catalog, "load_mcp_entries", return_value=remote),
                    patch.object(generate_ai_catalog, "load_mcp_registry_records", return_value=[]),
                ):
                    rendered, count = generate_ai_catalog.generate()
                self.assertEqual(count, 2)
                self.assertEqual(remote, original)
                expected = [
                    entry
                    | {
                        "identifier": identifier.replace("urn:ai:", "urn:air:", 1),
                        "tags": list(dict.fromkeys([*(tags or []), "connector-available"])),
                        "connector": {"available": True, "name": "example"},
                        "matchHints": hints,
                    }
                    for entry in remote
                ]
                self.assertEqual(json.loads(rendered)["entries"], expected)

    def test_connector_annotation_without_hints(self):
        identifier = "urn:ai:example.com:remote:connector"
        self.annotations_file.write_text(
            json.dumps({identifier: {"connectorName": "example"}}), encoding="utf-8"
        )
        remote = {
            "identifier": identifier,
            "displayName": "Example",
            "type": "application/mcp-server+json",
            "url": "https://example.com",
        }
        with (
            patch.object(generate_ai_catalog, "SOURCE_DIR", self.annotations_file.parent / "catalog"),
            patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[remote]),
            patch.object(generate_ai_catalog, "load_mcp_registry_records", return_value=[]),
        ):
            rendered, _ = generate_ai_catalog.generate()
        entry = json.loads(rendered)["entries"][0]
        self.assertEqual(entry["connector"], {"available": True, "name": "example"})
        self.assertNotIn("matchHints", entry)

    def test_missing_connector_annotation_identifier_fails(self):
        identifier = "urn:ai:example.com:missing:connector"
        self.annotations_file.write_text(
            json.dumps({identifier: {"connectorName": "example"}}), encoding="utf-8"
        )
        with (
            patch.object(generate_ai_catalog, "SOURCE_DIR", self.annotations_file.parent / "catalog"),
            patch.object(generate_ai_catalog, "load_mcp_entries", return_value=[]),
            self.assertRaises(SystemExit) as error,
        ):
            generate_ai_catalog.generate()
        self.assertEqual(
            str(error.exception),
            f"connector-annotations.json: identifiers not found in remote catalog: {[identifier]}",
        )

    def test_local_entry_overrides_connector_annotation(self):
        root = self.annotations_file.parent
        source = root / "catalog" / "example"
        source.mkdir(parents=True)
        local = {
            "identifier": "urn:ai:example.com:test:local",
            "displayName": "Local",
            "type": "application/mcp-server+json",
            "url": "https://example.com/local",
        }
        (source / "local.json").write_text(json.dumps(local), encoding="utf-8")
        self.annotations_file.write_text(
            json.dumps({local["identifier"]: {"connectorName": "example"}}),
            encoding="utf-8",
        )
        for remote in ([], [local | {"url": "https://example.com/remote"}]):
            with (
                self.subTest(remote=remote),
                patch.object(generate_ai_catalog, "ROOT", root),
                patch.object(generate_ai_catalog, "SOURCE_DIR", root / "catalog"),
                patch.object(generate_ai_catalog, "load_mcp_entries", return_value=remote),
                patch.object(generate_ai_catalog, "load_mcp_registry_records", return_value=[]),
            ):
                rendered, count = generate_ai_catalog.generate()
            self.assertEqual(count, 1)
            self.assertEqual(
                json.loads(rendered)["entries"],
                [local | {"identifier": local["identifier"].replace("urn:ai:", "urn:air:", 1)}],
            )

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
