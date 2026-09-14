# Contributing to the Agentfinder Catalog

Want to list a resource in the catalog? Open a pull request following the steps below. Contributions to this project are released to the public under the project's open source license.

## Catalog Structure

```
catalog/
└── <publisher>/
    └── <augment-name>.json
```

Each augment is a single JSON file located under your publisher directory.

New entries should use the canonical `urn:air:` identifier prefix and `type`.
Legacy `urn:ai:` and `mediaType` inputs remain accepted. Generation normalizes
the identifier once, and checks duplicates after normalization.

Resource-specific metadata may be an inline JSON object in `data` instead of a
`url`. Supply exactly one of them. An extension media type describes the payload;
it does not establish payload validity, runtime support, or execution permission.
For immutable source records, use a distinct identifier per selected revision
and retain the repository URI, environment path, and revision inside the payload.

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
  "identifier": "urn:air:github.com:<publisher>:<repo>:<augment-name>",
  "displayName": "Human-Readable Name",
  "type": "application/ai-skill",
  "url": "https://github.com/<publisher>/<repo>/blob/main/path/to/SKILL.md",
  "description": "A short description of what this augment does.",
  "tags": [
    "optional-tag"
  ],
  "metadata": {
    "sourceSet": "<publisher>/<repo>",
    "repoPath": "path/to/SKILL.md"
  }
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `identifier` | Yes | A unique canonical URN: `urn:air:github.com:<publisher>:<repo>:<name>`. Legacy `urn:ai:` is accepted for compatibility and normalized during generation. |
| `displayName` | Yes | A human-readable display name |
| `type` | Yes | The resource media type (e.g., `application/ai-skill`). Legacy `mediaType` is a compatibility-only alternative, not required alongside `type`. |
| `url` | Conditional | URL to the resource's definition file. Supply exactly one of `url` or `data`. |
| `data` | Conditional | Complete inline resource metadata as a JSON object, instead of `url`. |
| `description` | Recommended | A brief description of the resource's purpose |
| `tags` | No | Tags used to categorize and filter the resource |
| `metadata.sourceSet` | Conditional | Source repository in `owner/repository` form. Required with `metadata.repoPath`, and for canvas-only entries. |
| `metadata.repoPath` | Conditional | Safe repository-relative definition path. Required with `metadata.sourceSet`, and for canvas-only entries. |

#### Canvas-only plugins

Catalog entries for plugins whose functionality consists entirely of a GitHub Copilot
canvas keep the `application/vnd.github.copilot-plugin` media type and must include all
of these tags:

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
python3 scripts/generate_ai_catalog.py
python3 scripts/generate_ai_catalog.py --check
```

Files under `catalog/<publisher>/` remain the source of truth for contributor-managed entries. The root `ai-catalog.json` is generated for ARD ingestion, supplemented with missing entries from GitHub's public MCP catalog, and should not be edited by hand.

The pull request workflow regenerates `ai-catalog.json` automatically for branches in this repository. Fork workflows validate the catalog but cannot push changes; the main-branch fallback opens a follow-up pull request if regeneration is needed after merge.

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
- **Keep URL-carried definitions publicly accessible** so reviewers can inspect them. Inline records must preserve their source evidence without embedding credentials.

## Questions?

Open an [issue](https://github.com/github/agentfinder-catalog/issues/new) if you have questions or need help getting your augment listed.
