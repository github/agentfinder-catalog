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

## Contributing

Want to list your skill or MCP server in the catalog? See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide, including the JSON schema, validation steps, and PR process.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
