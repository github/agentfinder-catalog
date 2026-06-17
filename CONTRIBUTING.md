# Contributing to the Agentfinder Catalog

Want to list your augment (skill or MCP server) in the catalog? Open a pull request following the steps below.

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
| `metadata.sourceSet` | ✅ | The source repository name |
| `metadata.repoPath` | ✅ | Path to the definition file within the repository |

### 4. Validate your JSON

Make sure your file is valid JSON:

```bash
python -m json.tool catalog/<your-publisher>/<augment-name>.json
```

### 5. Open a pull request

```bash
git checkout -b add-<augment-name>
git add catalog/
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
