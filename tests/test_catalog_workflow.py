import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "catalog.yml"
).read_text(encoding="utf-8")
PUBLISH_STEP = WORKFLOW.split("- name: Open catalog refresh pull request\n", 1)[1]
PUBLISH_SCRIPT = textwrap.dedent(PUBLISH_STEP.split("        run: |\n", 1)[1])


class CatalogWorkflowTest(unittest.TestCase):
    def test_refresh_triggers_and_publication_guard(self):
        self.assertIn('  schedule:\n    - cron: "17 * * * *"\n', WORKFLOW)
        self.assertIn("  workflow_dispatch:\n", WORKFLOW)
        self.assertIn("  push:\n    branches:\n      - main\n", WORKFLOW)
        self.assertIn("  pull_request:\n    paths:\n", WORKFLOW)
        self.assertIn(
            "        if: (github.event_name == 'push' || "
            "github.event_name == 'schedule' || "
            "github.event_name == 'workflow_dispatch') && "
            "github.ref == 'refs/heads/main'\n",
            PUBLISH_STEP,
        )
        self.assertIn(
            "concurrency:\n  group: catalog-${{ github.ref }}\n"
            "  cancel-in-progress: false\n",
            WORKFLOW,
        )

    def run_publication(self, changed, open_prs):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            remote = root / "remote.git"
            log = root / "gh.log"
            binaries = root / "bin"
            binaries.mkdir()
            gh = binaries / "gh"
            gh.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$GH_LOG"\n'
                'if [ "$1 $2" = "pr list" ]; then\n'
                '  printf "%s\\n" "$OPEN_PRS"\nfi\n',
                encoding="utf-8",
            )
            gh.chmod(0o755)
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("GIT_")
            } | {
                "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
                "GH_LOG": str(log),
                "OPEN_PRS": str(open_prs),
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TEMPLATE_DIR": "",
            }

            def git(*args, cwd=repository):
                return subprocess.run(
                    ["git", *args],
                    cwd=cwd,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "--bare", str(remote), cwd=root)
            git("init", "--initial-branch=main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            catalog = repository / "ai-catalog.json"
            catalog.write_text('{"entries": []}\n', encoding="utf-8")
            git("add", "ai-catalog.json")
            git("commit", "-m", "Initial catalog")
            git("remote", "add", "origin", str(remote))
            git("push", "origin", "main")
            if open_prs:
                git("switch", "-c", "automation/update-ai-catalog")
                catalog.write_text('{"entries": ["previous"]}\n', encoding="utf-8")
                git("add", "ai-catalog.json")
                git("commit", "-m", "Previous refresh")
                git("push", "origin", "automation/update-ai-catalog")
                git("switch", "main")
                git("branch", "-D", "automation/update-ai-catalog")
            if changed:
                catalog.write_text('{"entries": ["updated"]}\n', encoding="utf-8")
            subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", PUBLISH_SCRIPT],
                cwd=repository,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
            if changed:
                self.assertEqual(
                    git("show", "automation/update-ai-catalog:ai-catalog.json", cwd=remote),
                    '{"entries": ["updated"]}',
                )
            self.assertEqual(
                git("show", "main:ai-catalog.json", cwd=remote), '{"entries": []}'
            )
            return calls

    def test_unchanged_catalog_does_not_publish(self):
        self.assertEqual(self.run_publication(changed=False, open_prs=0), "")

    def test_changed_catalog_opens_refresh_pr_and_dispatches_validation(self):
        calls = self.run_publication(changed=True, open_prs=0)
        self.assertIn("pr create --base main --head automation/update-ai-catalog", calls)
        self.assertIn("workflow run catalog.yml --ref automation/update-ai-catalog", calls)

    def test_changed_catalog_updates_existing_pr_without_creating_another(self):
        calls = self.run_publication(changed=True, open_prs=1)
        self.assertIn("pr list --head automation/update-ai-catalog --state open", calls)
        self.assertNotIn("pr create", calls)
        self.assertIn("workflow run catalog.yml --ref automation/update-ai-catalog", calls)


if __name__ == "__main__":
    unittest.main()
