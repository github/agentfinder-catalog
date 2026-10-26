# Agent Finder Catalog

The public catalog of augments (skills, MCP servers, and other agentic resources) discoverable by [GitHub Copilot's agent finder](https://github.com/agentfinder). This repository is the community-editable registry that powers agent finder's search results.

## What is Agent Finder?

Agent finder lets GitHub Copilot dynamically discover the right capability for a task at runtime. Instead of pre-loading every tool into the context window, Copilot searches this catalog—or a private registry you control—and surfaces ranked matches on demand.

Agent finder implements the open [Agentic Resource Discovery (ARD) specification](https://agenticresourcediscovery.org/), developed in collaboration with Google, GoDaddy, Hugging Face, Microsoft, and others.

Key properties:

- **Discovery, not installation** — Agent finder finds the right tool at the right time. It doesn't silently connect anything; you stay in control of what gets wired in.
- **Scoped to a registry** — Point agent finder at this public catalog or your own private registry. Agents only see what you permit.
- **Governed by managed settings** — The same place you govern Copilot is where you define which resources agents are allowed to discover.

Learn more in the [changelog announcement](https://github.blog/changelog/2026-06-17-agent-finder-for-github-copilot-now-available/).

## Catalog Structure

```
catalog/
└── <publisher>/
    └── <augment-name>.json
```

Each augment is a single JSON file under the publisher's directory. The publisher name matches the GitHub organization or username that owns the resource.

These per-entry files are the source of truth for contributor-managed entries. The root `ai-catalog.json` is a generated Agentic Resource Discovery (ARD) ingestion artifact that also includes missing entries from GitHub's public MCP catalog. Do not edit it by hand; regenerate it with `python3 scripts/generate_ai_catalog.py`.

Install the generator's image-validation dependency first with
`python3 -m pip install -r requirements.txt` (preferably in a virtual environment).

The Catalog workflow checks the [GitHub MCP Registry](https://api.mcp.github.com/.well-known/ai-catalog.json) hourly, independently of repository changes, and opens or updates the `automation/update-ai-catalog` pull request when the generated catalog changes. This refresh picks up registry additions and current server-version references; it does not query the general public MCP registry. Refresh changes still require the pull request to be merged before they reach the main-branch catalog. GitHub Actions schedules can be delayed, and a manual workflow run on `main` uses the same publication flow.

## Optional reviewed icons

`catalog-icons.json` is an identity-keyed overlay for both local and
registry-imported resources. This tooling-only change does not add the file;
artwork and production declarations are reviewed separately. A missing file
means no curated icons.
Declarations use the existing generated `urn:air:` identifier
and optional exact version, without duplicating resources or changing descriptor
URLs. Generation adds only the scalar `metadata["com.github.agentfinder.icon.url"]`;
source provenance stays in the overlay.

Reviewed assets belong under `icons/<publisher>/<asset>.png`, with recorded
redistribution permission or an explicit approval attestation, a matching SHA-256,
and immutable commit-pinned HTTPS
`raw.githubusercontent.com` URLs. Initial validation permits static PNG files up
to 256 KiB and 512 by 512 pixels. See
[the icon contribution guide](CONTRIBUTING.md#reviewed-resource-icons) for exact
fixtures, validation, and addition/replacement/removal instructions. Icons imply
neither endorsement nor official-product ownership.

Production publication of declarations follows deployed
[github/agentfinder#557](https://github.com/github/agentfinder/pull/557) and
[github/copilot-ecosystem#1625](https://github.com/github/copilot-ecosystem/issues/1625)
service support. Clients continue using optional `metadata.github.icon.url` and
their existing fallbacks. Catalog validation does not mean the service fetches or
validates image bytes.

## Contributing

Want to list your skill or MCP server in the catalog? See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide, including the JSON schema, validation steps, and PR process.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
