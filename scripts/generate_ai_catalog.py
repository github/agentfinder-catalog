#!/usr/bin/env python3

import argparse
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

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
CLAUDE_PLUGIN_MEDIA_TYPE = "application/vnd.anthropic.claude-plugin+json"
CLAUDE_PLUGIN_MANIFEST_PATH = ".claude-plugin/plugin.json"
CANVAS_ONLY_REQUIRED_TAGS = frozenset(("canvas", "canvas-only", "github-copilot"))
NON_CANVAS_PLUGIN_TAGS = frozenset(("agent", "hook", "mcp-server", "skill"))
SOURCE_SET_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ICON_METADATA_KEY = "com.github.agentfinder.icon.url"
ICON_OVERLAY = "catalog-icons.json"
MAX_ICON_BYTES = 256 * 1024
MAX_ICON_DIMENSION = 512
ICON_PATH_PATTERN = re.compile(
    r"/github/agentfinder-catalog/[0-9a-f]{40}/"
    r"(icons/[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.png)"
)


def validate_png(content, source):
    if len(content) > MAX_ICON_BYTES:
        fail(f"{source}: asset exceeds {MAX_ICON_BYTES} bytes")
    try:
        with Image.open(io.BytesIO(content), formats=["PNG"]) as image:
            if not all(1 <= dimension <= MAX_ICON_DIMENSION for dimension in image.size):
                fail(f"{source}: PNG dimensions must be between 1 and {MAX_ICON_DIMENSION}")
            image.verify()
        # Verification checks file integrity; reopening also exercises actual decoding.
        with Image.open(io.BytesIO(content), formats=["PNG"]) as image:
            if getattr(image, "is_animated", False):
                fail(f"{source}: animated PNGs are not supported")
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, IndexError,
            Image.DecompressionBombError) as error:
        fail(f"{source}: invalid PNG: {error}")


def validate_icon_url(value, source):
    if not isinstance(value, str):
        fail(f"{source}: url must be a string")
    try:
        url = urlparse(value)
        url.port
    except ValueError:
        fail(f"{source}: url must be a valid commit-pinned raw GitHub URL")
    match = ICON_PATH_PATTERN.fullmatch(url.path)
    if (
        url.scheme != "https" or url.netloc != "raw.githubusercontent.com"
        or url.query or url.fragment or "?" in value or "#" in value
        or not match or value != url.geturl()
    ):
        fail(
            f"{source}: url must be an HTTPS raw.githubusercontent.com URL for "
            "github/agentfinder-catalog/<40-hex-commit>/icons/<publisher>/<asset>.png"
        )
    return Path(match[1])


def validate_provenance_url(value, source):
    if not isinstance(value, str) or any(character.isspace() for character in value):
        fail(f"{source}: must be a public absolute HTTPS URL")
    try:
        url = urlparse(value)
        hostname = url.hostname
        port = url.port
    except ValueError:
        fail(f"{source}: must be a valid public absolute HTTPS URL")
    if (
        url.scheme != "https" or not hostname or "\\" in value
        or url.username is not None or url.password is not None or port is not None
    ):
        fail(f"{source}: must be a public absolute HTTPS URL without credentials or ports")


def validate_icon_asset(declaration, source):
    relative = validate_icon_url(declaration.get("url"), source)
    provenance = declaration.get("provenance")
    licensed_fields = {"sourceUrl", "license", "permissionUrl", "sha256"}
    approval_fields = {"sourceUrl", "approval", "sha256"}
    if (
        not isinstance(provenance, dict)
        or set(provenance) not in (licensed_fields, approval_fields)
    ):
        fail(
            f"{source}: provenance must contain sourceUrl and sha256, plus either "
            "license and permissionUrl, or an explicit approval attestation"
        )
    validate_provenance_url(provenance["sourceUrl"], f"{source}: provenance.sourceUrl")
    if "approval" in provenance:
        if not isinstance(provenance["approval"], str) or not provenance["approval"].strip():
            fail(f"{source}: provenance.approval must be a non-empty redistribution attestation")
    else:
        validate_provenance_url(provenance["permissionUrl"], f"{source}: provenance.permissionUrl")
        license_name = provenance["license"]
        if not isinstance(license_name, str) or not license_name.strip():
            fail(f"{source}: provenance.license must be a non-empty license or permission label")
    digest = provenance["sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        fail(f"{source}: provenance.sha256 must be a lowercase SHA-256 hex digest")
    path = ROOT / relative
    try:
        if any(
            (ROOT / Path(*relative.parts[:index])).is_symlink()
            for index in range(1, len(relative.parts) + 1)
        ):
            fail(f"{source}: asset path must not contain symlinks")
        if not path.resolve().is_relative_to((ROOT / "icons").resolve()):
            fail(f"{source}: asset must stay within icons/")
        with path.open("rb") as asset:
            content = asset.read(MAX_ICON_BYTES + 1)
    except OSError as error:
        fail(f"{source}: cannot read asset {relative}: {error}")
    if len(content) > MAX_ICON_BYTES:
        fail(f"{source}: asset exceeds {MAX_ICON_BYTES} bytes")
    if hashlib.sha256(content).hexdigest() != digest:
        fail(f"{source}: asset SHA-256 does not match provenance.sha256")
    validate_png(content, source)


def load_icon_declarations():
    path = ROOT / ICON_OVERLAY
    if path.is_symlink():
        fail(f"{ICON_OVERLAY}: overlay must not be a symlink")
    if not path.exists():
        return []

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"{ICON_OVERLAY}: duplicate JSON key {key}")
            result[key] = value
        return result

    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{ICON_OVERLAY}: cannot load JSON: {error}")
    if (
        not isinstance(document, dict) or set(document) != {"icons"}
        or not isinstance(document["icons"], list)
    ):
        fail(f"{ICON_OVERLAY}: expected an object containing only an icons array")
    seen = {}
    for index, declaration in enumerate(document["icons"]):
        source = f"{ICON_OVERLAY} icons[{index}]"
        if (
            not isinstance(declaration, dict)
            or not {"identifier", "url", "provenance"}.issubset(declaration)
            or set(declaration) - {"identifier", "version", "url", "provenance"}
        ):
            fail(f"{source}: expected identifier, optional version, url, and provenance")
        identifier = declaration["identifier"]
        if not isinstance(identifier, str) or not re.fullmatch(
            r"urn:air:[A-Za-z0-9.-]+(?::[A-Za-z0-9._-]+)+", identifier
        ):
            fail(f"{source}: identifier must be an exact generated urn:air: identity")
        version = declaration.get("version")
        if "version" in declaration and (
            not isinstance(version, str) or not version.strip()
        ):
            fail(f"{source}: version must be a non-empty string when supplied")
        versions = seen.setdefault(identifier, set())
        if version in versions or (versions and (version is None or None in versions)):
            fail(f"{source}: overlapping icon declarations for {identifier}")
        versions.add(version)
        validate_icon_asset(declaration, source)
    return document["icons"]


def apply_icon_declarations(entries, declarations):
    by_identifier = {}
    for entry in entries:
        by_identifier.setdefault(entry["identifier"], []).append(entry)
    for index, declaration in enumerate(declarations):
        matches = [
            entry for entry in by_identifier.get(declaration["identifier"], ())
            if "version" not in declaration or entry.get("version") == declaration["version"]
        ]
        if not matches:
            fail(
                f"{ICON_OVERLAY} icons[{index}]: unmatched icon declaration for "
                f"{declaration['identifier']} {declaration.get('version', '(all versions)')}"
            )
        for entry in matches:
            entry["metadata"] = {
                **(entry.get("metadata") or {}),
                ICON_METADATA_KEY: declaration["url"],
            }


def fail(message):
    raise SystemExit(message)


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


def canvas_only_media_type(entry):
    metadata = entry.get("metadata")
    repo_path = metadata.get("repoPath") if isinstance(metadata, dict) else None
    if isinstance(repo_path, str) and (
        repo_path == CLAUDE_PLUGIN_MANIFEST_PATH
        or repo_path.endswith(f"/{CLAUDE_PLUGIN_MANIFEST_PATH}")
    ):
        return CLAUDE_PLUGIN_MEDIA_TYPE
    return CANVAS_PLUGIN_MEDIA_TYPE


def validate_repository_metadata(metadata, source):
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        fail(f"{source}: metadata must be an object")
    if ICON_METADATA_KEY in metadata:
        fail(f"{source}: {ICON_METADATA_KEY} must be declared through {ICON_OVERLAY}")

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
    if not entry["identifier"].startswith("urn:ai:"):
        fail(f"{source}: identifier must start with urn:ai:")

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
        media_type = canvas_only_media_type(entry)
        if entry.get("mediaType") != media_type:
            fail(f"{source}: canvas-only entries must use mediaType {media_type}")
        entry_type = entry.get("type")
        if entry_type is not None and entry_type != media_type:
            fail(f"{source}: canvas-only entry type must match mediaType {media_type}")

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
    icon_declarations = load_icon_declarations()
    entries = []
    identities = set()
    local_identifiers = set()

    def add(entry, source):
        generated = dict(entry)
        generated["identifier"] = "urn:air:" + entry["identifier"][len("urn:ai:") :]
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
        local_identifiers.add(entry["identifier"])

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
        if entry["identifier"] not in local_identifiers:
            generated = dict(entry)
            record = registry_records.get(registry_record_key(entry))
            name = display_name(entry, record)
            if name:
                generated["displayName"] = name
            add(generated, source)

    apply_icon_declarations(entries, icon_declarations)

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
