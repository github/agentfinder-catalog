# Contributing to the Agentfinder Catalog

__Last Updated:__ 2026-10-13

Want to list your augment (skill or MCP server) in the catalog? Open a pull request following the steps below. Contributions to this project are released to the public under the project's open source license.

## Catalog Structure

```
catalog/
└── <publisher>/
    └── <augment-name>.json
```

Each augment is a single JSON file located under your publisher directory.

## How to Add Your Augment

### 1. Fork and clone the repository

```bash
gh repo fork github/agentfinder-catalog --clone
cd agentfinder-catalog
```

### 2. Create your publisher directory (if it doesn't exist)

Your publisher name should match your GitHub organization or username.

```bash
mkdir -p catalog/<your-publisher>
```

### 3. Create your augment JSON file

Create a file at `catalog/<your-publisher>/<augment-name>.json` with the following schema:

```json
{
  "identifier": "urn:ai:github.com:<publisher>:<repo>:<augment-name>",
  "displayName": "Human-Readable Name",
  "mediaType": "application/ai-skill",
  "url": "https://github.com/<publisher>/<repo>/blob/main/path/to/SKILL.md",
  "description": "A short description of what this augment does.",
  "tags": [
    "optional-tag"
  ],
  "metadata": {
    "sourceSet": "<repo>",
    "repoPath": "path/to/SKILL.md"
  }
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `identifier` | ✅ | A URN uniquely identifying the augment. Format: `urn:ai:github.com:<publisher>:<repo>:<name>` |
| `displayName` | ✅ | A human-readable display name |
| `mediaType` | ✅ | The type of augment (e.g., `application/ai-skill`) |
| `url` | ✅ | URL to the augment's definition file (e.g., SKILL.md) |
| `description` | ✅ | A brief description of the augment's purpose |
| `tags` | ❌ | Tags used to categorize and filter the augment |
| `metadata.sourceSet` | For GitHub-file references | The source repository name; omit for registry references |
| `metadata.repoPath` | For GitHub-file references | Path to the definition file within the repository; omit for registry references |

#### MCP registry entries

Before adding an MCP server, check whether it is already imported into `ai-catalog.json`
from the [GitHub MCP Registry](https://api.mcp.github.com/.well-known/ai-catalog.json).
Prefer that existing registry entry over a second contributor-managed entry for the same
server. Keeping the registry-supplied identifier avoids duplicate search resources and
lets the hourly refresh pick up new version references without a local entry shadowing them.

Agent Finder's current enrichment path for catalog MCP references accepts versioned
`https://api.mcp.github.com/v0.1/servers/<encoded-server-name>/versions/<version>` URLs.
Use the URL and matching version supplied by the registry. Raw GitHub descriptor URLs
are not supported by that reference resolver, even when they contain a valid MCP descriptor.
Do not create a copied descriptor to represent a server that is already imported from the registry.

Registry references do not identify a file in this repository. Do not attach
`metadata.sourceSet` or `metadata.repoPath` pointing to a copied descriptor.

#### Reviewed resource icons

Icons are optional. Declare them in the root `catalog-icons.json` overlay, for
both contributor-managed and registry-imported resources. Do not copy a registry
descriptor or create another resource entry to attach an icon. Use the exact
generated `urn:air:` identifier from `ai-catalog.json`, not the source `urn:ai:`
identifier, a display name, or a descriptor URL.

The tooling-only change does not add an overlay file; create it when adding the
first approved declarations. Artwork and production declarations are reviewed
in a separate change.
The following is a **synthetic example**, not an available asset, real digest,
or evidence of permission:

```json
{
  "icons": [
    {
      "identifier": "urn:air:registry.modelcontextprotocol.io:example:weather",
      "url": "https://raw.githubusercontent.com/github/agentfinder-catalog/0123456789abcdef0123456789abcdef01234567/icons/example/weather.png",
      "provenance": {
        "sourceUrl": "https://example.com/weather-artwork",
        "license": "CC0-1.0",
        "permissionUrl": "https://example.com/weather-artwork-permission",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    }
  ]
}
```

Omit `version` to cover all versions of that exact identifier. To restrict an
icon to one existing version, add a nonempty `version` string to the declaration.
Do not supply `null`. Duplicate or overlapping declarations fail validation,
including an identifier-wide declaration combined with an exact-version one.
Unmatched identifiers or versions also fail; explicitly maintain declarations
when a registry resource disappears or a version-specific reference rolls over.
Prefer identifier-wide declarations when the artwork legitimately covers all
versions.

The generator applies the overlay after normal entry selection and registry
imports, adding only the scalar
`metadata["com.github.agentfinder.icon.url"]`. It preserves identifiers, versions,
descriptor URLs, native data, and other metadata. Provenance is not published in
the generated entry. The icon key is reserved for the overlay: do not put it
directly in contributor-managed entries or registry inputs. Unknown overlay
fields and duplicate JSON keys are rejected. An absent overlay is treated as
empty for compatibility with older checkouts.

For the example above, the generated entry is:

```json
{
  "identifier": "urn:air:registry.modelcontextprotocol.io:example:weather",
  "displayName": "Weather",
  "type": "application/mcp-server+json",
  "version": "1.0.0",
  "url": "https://api.mcp.github.com/v0.1/servers/example%2Fweather/versions/1.0.0",
  "metadata": {
    "com.github.agentfinder.icon.url": "https://raw.githubusercontent.com/github/agentfinder-catalog/0123456789abcdef0123456789abcdef01234567/icons/example/weather.png"
  }
}
```

This input key is not a new client response field. Once service support is
deployed, Agent Finder emits the optional nested `metadata.github.icon.url`.
A supported curated URL takes precedence over a supported descriptor-declared
icon. Removing the curated declaration restores descriptor-icon fallback;
it does not suppress a descriptor icon. Invalid service-side declarations also
fall back. Invalid catalog-authored declarations instead fail generation.
Clients keep their resource-type fallback when no supported icon is available
or an image cannot be loaded.

##### Asset review and validation

- Place reviewed assets at `icons/<publisher>/<asset>.png`. Publisher and asset
  names start with an ASCII letter, digit, underscore, or hyphen; remaining
  characters may also include dots. Asset paths cannot contain symlinks.
- Use **static PNG** files, at most **256 KiB (262144 bytes)**, with width and
  height between **1 and 512 pixels**. Pillow verifies PNG integrity and decodes
  the image; animated images are rejected. Validation follows Pillow's PNG
  decoder rather than implementing a separate strict chunk grammar (for example,
  it does not reject otherwise decodable PNGs solely for trailing bytes).
  These checks are not image sanitization; reviewers must inspect the rendered image.
- URLs must use HTTPS and the exact `raw.githubusercontent.com` host, this
  repository, a full lowercase 40-hex commit reference, and the asset path.
  Mutable refs, credentials, explicit ports, query strings, fragments, encoded
  paths, other hosts/repositories, and other image formats are rejected.
- Supply `sourceUrl` identifying the original artwork, `license` identifying its
  license or explicit permission, `permissionUrl` pointing to reviewable evidence
  that redistribution of these bytes is permitted, and a lowercase `sha256` of
  the actual file. Alternatively, when approval is given without a URL, supply
  `sourceUrl`, `sha256`, and a nonempty `approval` attestation describing the
  explicit authorization for public redistribution; do not invent a license or
  permission link. These two provenance forms are mutually exclusive.
  Source and permission URLs must be absolute HTTPS without
  credentials or ports. Generator checks establish syntax and a matching local
  digest, **not legal permission, public availability, or ownership**. Reviewers
  must verify the evidence and any attribution or notice requirements.
- Do not infer logos from repository-owner avatars or acquire/copy vendor artwork
  without verified redistribution permission. The repository's MIT license
  does not establish permission for third-party artwork. An icon does not prove
  vendor ownership, endorsement, or official-product approval.

Compute a file's digest with:

```bash
shasum -a 256 icons/<publisher>/<asset>.png
```

##### Adding, replacing, and removing icons

**Add:** obtain permission and fulfill any required notices first. Publish the
reviewed asset in an asset-only commit, then use that existing commit's raw URL
in a separate declaration change. A declaration cannot pin the SHA of its own
containing commit. Reviewers must fetch the public pinned URL and verify its bytes
against the recorded SHA-256: the generator checks the file in the current
checkout, not the remote asset at that commit. Regenerate and review
`ai-catalog.json`; only the intended icon metadata should change.

**Replace:** publish the newly reviewed asset first, then update its immutable URL,
provenance, and digest together. Changed image bytes must have a changed URL.
Do not merely overwrite an asset while retaining an old pinned URL. If different
resource versions need different bytes, use distinct paths so all declared assets
can be checked in the current tree.

**Remove:** remove the overlay record and regenerate. Delete an unused current
asset only after removing all declarations that reference it. Historical pinned
bytes remain retrievable; deleting the current file does not revoke old URLs.
The service owner handles enrichment invalidation and reconciliation so an
addition, replacement, or removal takes effect in responses.

Validate icon changes with the normal generation commands below and:

```bash
python3 -m unittest discover -s tests
```

Tooling may land before service support only if the empty overlay leaves generated
resources unchanged. **Production declaration publication must follow deployed
github/agentfinder#557 foundation and github/copilot-ecosystem#1625 service
support**, plus verified redistribution permission. Catalog tooling alone is
not end-to-end icon delivery.

The current ARD specification is
[v0.91 (Proposal)](https://github.com/ards-project/ard-spec/blob/49eb4df6f3841ccecc5c31d5175117337b568bdf/spec/ard.md);
the catalog envelope remains `specVersion: "1.0"`. Both current entry and catalog
schemas permit scalar metadata extensions, which is why this declaration is flat.
This change does not adopt JSON-LD contexts or imply support for every behavior
in the latest proposal.

#### Canvas-only plugins

Catalog entries for plugins whose functionality consists entirely of a GitHub Copilot
canvas use the media type that matches their manifest layout and must include all of
these tags. Use `application/vnd.anthropic.claude-plugin+json` when `metadata.repoPath`
is a `.claude-plugin/plugin.json` manifest, and `application/vnd.github.copilot-plugin`
for other Copilot plugin manifests.

```json
"tags": [
  "canvas",
  "canvas-only",
  "github-copilot"
]
```

Do not use `canvas-only` for a plugin that still provides useful agents, skills, hooks,
or MCP servers when its canvas is unavailable. Canvas-only entries must not include
the corresponding `agent`, `skill`, `hook`, or `mcp-server` capability tags.

### 4. Validate your JSON

Make sure your file is valid JSON, then regenerate and check the ARD ingestion catalog:

```bash
python -m json.tool catalog/<your-publisher>/<augment-name>.json
python3 -m pip install -r requirements.txt
python3 scripts/generate_ai_catalog.py
python3 scripts/generate_ai_catalog.py --check
```

Files under `catalog/<publisher>/` remain the source of truth for contributor-managed entries. The root `ai-catalog.json` is generated for ARD ingestion, supplemented with missing entries from GitHub's public MCP catalog, and should not be edited by hand.

The pull request workflow regenerates `ai-catalog.json` automatically for branches in this repository. Fork workflows validate the catalog but cannot push changes; the main-branch fallback opens a follow-up pull request if regeneration is needed after merge. Hourly scheduled runs and manual runs on `main` also open or update that same refresh pull request for GitHub MCP Registry changes, even when no contributor files have changed. Manual runs on other branches regenerate and validate only, so the refresh branch's validation does not recursively publish another pull request.

### 5. Open a pull request

```bash
git checkout -b add-<augment-name>
git add catalog/ ai-catalog.json
git commit -m "Add <augment-name> to catalog"
git push origin add-<augment-name>
gh pr create --title "Add <augment-name>" --body "Adds <augment-name> to the agentfinder catalog."
```

## Guidelines

- **One file per augment** — don't bundle multiple augments into a single file.
- **Use kebab-case** for file names (e.g., `my-cool-skill.json`).
- **Keep descriptions concise** — one or two sentences.
- **Ensure your URL is publicly accessible** so reviewers can verify the augment definition.

## Questions?

Open an [issue](https://github.com/github/agentfinder-catalog/issues/new) if you have questions or need help getting your augment listed.
