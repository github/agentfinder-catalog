#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
SOURCE_DIR = ROOT / "catalog"
OUTPUT = ROOT / "ai-catalog.json"
MAX_ENTRIES = 10_000
MAX_BYTES = 10 * 1024 * 1024
MCP_CATALOG = "https://api.mcp.github.com/.well-known/ai-catalog.json"
MCP_REGISTRY = "https://api.mcp.github.com/v0.1/servers"
MCP_REGISTRY_PAGE_SIZE = 100
CANVAS_PLUGIN_MEDIA_TYPE = "application/vnd.github.copilot-plugin"
CANVAS_ONLY_REQUIRED_TAGS = frozenset(("canvas", "canvas-only", "github-copilot"))
NON_CANVAS_PLUGIN_TAGS = frozenset(("agent", "hook", "mcp-server", "skill"))
SOURCE_SET_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def fail(message):
    raise SystemExit(message)


def canonical_identifier(identifier, source):
    if identifier.startswith("urn:air:"):
        return identifier
    if identifier.startswith("urn:ai:"):
        return "urn:air:" + identifier[len("urn:ai:") :]
    fail(f"{source}: identifier must start with urn:air: or legacy urn:ai:")


def validate_canvas_only_tags(tags, source):
    missing_tags = CANVAS_ONLY_REQUIRED_TAGS.difference(tags)
    if missing_tags:
        fail(
            f"{source}: canvas-only entry is missing required tags "
            f"{', '.join(sorted(missing_tags))}"
        )
    conflicting_tags = NON_CANVAS_PLUGIN_TAGS.intersection(tags)
    if conflicting_tags:
        fail(
            f"{source}: canvas-only entry cannot include non-Canvas capability tags "
            f"{', '.join(sorted(conflicting_tags))}"
        )


def validate_repository_metadata(metadata, source):
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        fail(f"{source}: metadata must be an object")

    source_set = metadata.get("sourceSet")
    repo_path = metadata.get("repoPath")
    if source_set is None and repo_path is None:
        return
    if (
        not isinstance(source_set, str)
        or not SOURCE_SET_PATTERN.fullmatch(source_set)
        or any(part in (".", "..") for part in source_set.split("/"))
    ):
        fail(f"{source}: metadata.sourceSet must be an owner/repository name")
    if not isinstance(repo_path, str) or not repo_path.strip():
        fail(f"{source}: metadata.repoPath must be a non-empty relative path")
    if (
        "\\" in repo_path
        or unquote(repo_path) != repo_path
        or PurePosixPath(repo_path).is_absolute()
        or any(part in ("", ".", "..") for part in repo_path.split("/"))
    ):
        fail(f"{source}: metadata.repoPath must be a safe relative POSIX path")


def validate_canvas_only_source(entry, url, source):
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        fail(f"{source}: canvas-only entry metadata must be an object")
    source_set = metadata.get("sourceSet")
    repo_path = metadata.get("repoPath")
    if not isinstance(source_set, str) or not isinstance(repo_path, str):
        fail(
            f"{source}: canvas-only entry metadata must include sourceSet and repoPath"
        )

    decoded_path = unquote(url.path)
    prefix = f"/{source_set}/blob/"
    suffix = f"/{repo_path}"
    ref_and_path = (
        decoded_path[len(prefix) :] if decoded_path.startswith(prefix) else ""
    )
    if (
        url.netloc.lower() != "github.com"
        or unquote(decoded_path) != decoded_path
        or "\\" in decoded_path
        or any(part in (".", "..") for part in decoded_path.split("/"))
        or url.query
        or url.fragment
        or not ref_and_path
        or not decoded_path.endswith(suffix)
        or len(ref_and_path) <= len(suffix)
    ):
        fail(
            f"{source}: canvas-only entry url must point to metadata.repoPath "
            f"in the metadata.sourceSet GitHub repository"
        )


def validate(entry, source):
    if not isinstance(entry, dict):
        fail(f"{source}: entry must be a JSON object")

    # ponytail: mirror the current ingestion contract without adding a schema dependency.
    for field in ("identifier", "displayName"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            fail(f"{source}: {field} must be a non-empty string")
    if not any(
        isinstance(entry.get(field), str) and entry[field].strip()
        for field in ("type", "mediaType")
    ):
        fail(f"{source}: type or mediaType must be a non-empty string")
    has_url = entry.get("url") is not None
    has_data = entry.get("data") is not None
    if has_url == has_data:
        fail(f"{source}: exactly one of url or data is required")
    if has_url and (not isinstance(entry["url"], str) or not entry["url"].strip()):
        fail(f"{source}: url must be a non-empty string")
    if has_url:
        try:
            url = urlparse(entry["url"])
            hostname = url.hostname
            url.port
        except ValueError:
            fail(f"{source}: url must be a valid absolute HTTP(S) URL")
        if (
            url.scheme not in ("http", "https")
            or not url.netloc
            or not hostname
            or "\\" in url.netloc
        ):
            fail(f"{source}: url must be an absolute HTTP(S) URL")
        if url.username is not None or url.password is not None:
            fail(f"{source}: url must not contain credentials")
    if has_data and not isinstance(entry["data"], dict):
        fail(f"{source}: data must be an object")
    canonical_identifier(entry["identifier"], source)

    version = entry.get("version")
    if version is not None and (
        not isinstance(version, str) or not version.strip()
    ):
        fail(f"{source}: version must be a non-empty string")

    tags = entry.get("tags")
    if tags is not None and (
        not isinstance(tags, list)
        or not all(isinstance(tag, str) and tag.strip() for tag in tags)
    ):
        fail(f"{source}: tags must be an array of non-empty strings")
    if isinstance(tags, list) and len(tags) != len(set(tags)):
        fail(f"{source}: tags must not contain duplicates")
    if isinstance(tags, list) and "canvas-only" in tags:
        validate_canvas_only_tags(tags, source)
        if not has_url:
            fail(f"{source}: canvas-only entries must use a GitHub descriptor url")
        legacy_type = entry.get("mediaType")
        if legacy_type is not None and legacy_type != CANVAS_PLUGIN_MEDIA_TYPE:
            fail(
                f"{source}: canvas-only entries must use mediaType "
                f"{CANVAS_PLUGIN_MEDIA_TYPE}"
            )
        entry_type = entry.get("type")
        if entry_type is not None and entry_type != CANVAS_PLUGIN_MEDIA_TYPE:
            fail(
                f"{source}: canvas-only entry type must match mediaType "
                f"{CANVAS_PLUGIN_MEDIA_TYPE}"
            )

    validate_repository_metadata(entry.get("metadata"), source)
    if isinstance(tags, list) and "canvas-only" in tags:
        validate_canvas_only_source(entry, url, source)


def load_mcp_entries():
    try:
        request = Request(MCP_CATALOG, headers={"User-Agent": "agentfinder-catalog-generator"})
        with urlopen(request, timeout=30) as response:
            document = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        fail(f"{MCP_CATALOG}: {error}")
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        fail(f"{MCP_CATALOG}: expected a catalog document with an entries array")
    return document["entries"]


def load_mcp_registry_records():
    records = []
    cursor = None
    while True:
        query = {"limit": MCP_REGISTRY_PAGE_SIZE}
        if cursor:
            query["cursor"] = cursor
        url = f"{MCP_REGISTRY}?{urlencode(query)}"
        try:
            request = Request(url, headers={"User-Agent": "agentfinder-catalog-generator"})
            with urlopen(request, timeout=30) as response:
                document = json.load(response)
        except (OSError, URLError, json.JSONDecodeError) as error:
            fail(f"{MCP_REGISTRY}: {error}")
        if not isinstance(document, dict) or not isinstance(document.get("servers"), list):
            fail(f"{url}: expected a registry document with a servers array")
        records.extend(document["servers"])
        metadata = document.get("metadata")
        cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
        if not cursor:
            return records


def registry_record_key(entry):
    url = entry.get("url")
    if not isinstance(url, str):
        return None
    path = [unquote(part) for part in urlparse(url).path.split("/") if part]
    try:
        servers_index = path.index("servers")
        return path[servers_index + 1], path[servers_index + 3]
    except (ValueError, IndexError):
        return None


def display_name(entry, registry_record=None):
    server = registry_record.get("server", {}) if isinstance(registry_record, dict) else {}
    if not isinstance(server, dict):
        server = {}
    metadata = server.get("_meta", {})
    publisher = (
        metadata.get("io.modelcontextprotocol.registry/publisher-provided", {})
        if isinstance(metadata, dict)
        else {}
    )
    github = publisher.get("github", {}) if isinstance(publisher, dict) else {}
    if not isinstance(github, dict):
        github = {}
    candidates = (
        github.get("displayName"),
        server.get("title"),
        entry.get("title"),
        entry.get("displayName"),
        entry.get("name"),
    )
    return next((value for value in candidates if isinstance(value, str) and value.strip()), None)


def generate():
    entries = []
    identities = set()
    local_identifiers = set()

    def add(entry, source):
        generated = dict(entry)
        generated["identifier"] = canonical_identifier(entry["identifier"], source)
        if not isinstance(generated.get("type"), str) or not generated["type"].strip():
            generated["type"] = entry.get("mediaType")
        version = entry.get("version")
        identity = (generated["identifier"], version)
        if identity in identities:
            fail(
                f"{source}: duplicate identifier/version identity "
                f"{generated['identifier']} {version or ''}"
            )
        identities.add(identity)
        entries.append(generated)

    for path in sorted(SOURCE_DIR.glob("*/*.json"), key=lambda item: item.as_posix()):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            fail(f"{path.relative_to(ROOT)}: invalid JSON: {error}")
        validate(entry, path.relative_to(ROOT))
        add(entry, path.relative_to(ROOT))
        local_identifiers.add(canonical_identifier(entry["identifier"], path.relative_to(ROOT)))

    remote_entries = sorted(
        load_mcp_entries(),
        key=lambda entry: (str(entry.get("identifier")), str(entry.get("version"))),
    )
    registry_records = {
        (record["server"].get("name"), record["server"].get("version")): record
        for record in load_mcp_registry_records()
        if isinstance(record, dict)
        and isinstance(record.get("server"), dict)
        and isinstance(record["server"].get("name"), str)
        and isinstance(record["server"].get("version"), str)
    } if remote_entries else {}
    for index, entry in enumerate(remote_entries):
        source = f"{MCP_CATALOG} entry {index}"
        validate(entry, source)
        if canonical_identifier(entry["identifier"], source) not in local_identifiers:
            generated = dict(entry)
            record = registry_records.get(registry_record_key(entry))
            name = display_name(entry, record)
            if name:
                generated["displayName"] = name
            add(generated, source)

    if len(entries) > MAX_ENTRIES:
        fail(f"catalog has {len(entries)} entries; limit is {MAX_ENTRIES}")

    document = {
        "specVersion": "1.0",
        "host": {"displayName": "GitHub Agent Finder Catalog"},
        "entries": entries,
    }
    rendered = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
    if len(rendered) > MAX_BYTES:
        fail(f"generated catalog is {len(rendered)} bytes; limit is {MAX_BYTES}")
    return rendered, len(entries)


def main():
    parser = argparse.ArgumentParser(description="Generate the ARD ingestion catalog")
    parser.add_argument("--check", action="store_true", help="fail if output is missing or stale")
    args = parser.parse_args()

    rendered, count = generate()
    if args.check:
        if not OUTPUT.exists():
            fail(f"{OUTPUT.name} is missing; run {SCRIPT.relative_to(ROOT)}")
        if OUTPUT.read_bytes() != rendered:
            fail(f"{OUTPUT.name} is stale; run {SCRIPT.relative_to(ROOT)}")
    else:
        OUTPUT.write_bytes(rendered)

    print(f"{OUTPUT.name}: {count} entries, {len(rendered)} bytes")


if __name__ == "__main__":
    main()
