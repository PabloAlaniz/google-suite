# Playbook: make a project discoverable by AI agents

What made `gsuite-sdk` reach people: an agent skill on ClawHub got ~1,900
downloads and 53 installs while the PyPI package had ~12 downloads a month.
Agents (and their users) find tools through skill and MCP indexes, not PyPI.

Order: **1** is required, **2–4** are cheap and automatic, **5** is the
biggest channel but needs an MCP server, **6** needs manual submissions.

## 0. Is the project a fit?

- It is **public** and its terms allow automation (no client data, internal
  infra, paid-account credentials or scraping that breaks a site's terms).
- An agent can drive it non-interactively: a CLI with **JSON output**
  (`-o json` / `--json`) and exit codes, or a Python API. Add JSON output first
  if it's missing.
- Setup is explainable in a few lines (install, env vars, one login step).

## 1. The skill (required)

```
skills/<name>/
├── SKILL.md            # < 500 lines: setup, CLI-first usage, a short API tour, errors
└── references/*.md     # one focused page per area, loaded on demand
```

- `name`: lowercase-hyphenated, **equal to the folder name**; `description`
  says what it does *and when to use it* (≤ 1024 chars, with the keywords an
  agent would match).
- Optional `license`, `compatibility` (install/runtime needs).
- ClawHub reads `metadata.openclaw` (`requires.env`, `primaryEnv`, `install`
  with `bins`). Write it in **block style** (no `[a, b]` / `{...}` flow
  syntax): the reference validator rejects flow syntax.
- Links: relative inside the skill (`references/x.md`), absolute (GitHub/docs
  site) for anything else — the skill is installed away from the repo.
- Tell the agent what to confirm with the user (sending, sharing, deleting,
  paying) and how errors look.

Keep it correct with [`agent-skill-check`](README.md#agent-skill-check) in the
project's tests (spec, frontmatter, env vars, every Python call and CLI
option), and call the reusable `skill-validate.yml` workflow in CI.

## 2. skills.sh (Vercel's `npx skills`)

Nothing to submit: once the repo has `skills/<name>/SKILL.md`, anyone can run

```bash
npx skills add PabloAlaniz/<repo>
```

which installs it for Claude Code, Codex, Cursor, Gemini CLI, Copilot,
Windsurf and others; installs show up on skills.sh's leaderboard. Put that
command in the README.

## 3. Claude Code marketplace + claude-plugins.dev

Copy [`templates/.claude-plugin/`](templates/.claude-plugin/) to the repo root
(the repo is both the marketplace and the plugin: `source: "./"`; skills in
`skills/` are discovered). Validate with `claude plugin validate . --strict`.

- Users: `claude plugin marketplace add PabloAlaniz/<repo>` then
  `claude plugin install <name>@<name>`.
- claude-plugins.dev crawls public repos with `.claude-plugin/marketplace.json`
  hourly; per-skill install stats at
  `api.claude-plugins.dev/api/skills/<owner>/<repo>/<skill>/stats`.

## 4. Gemini CLI gallery, SkillsMP, GitHub topics

- [`templates/gemini-extension.json`](templates/gemini-extension.json) at the
  repo root (`name`, `version`, `description`; skills come from `skills/`) +
  the repo topic `gemini-cli-extension` → crawled daily into
  geminicli.com/extensions. Users: `gemini extensions install https://github.com/PabloAlaniz/<repo>`.
- SkillsMP indexes public repos with SKILL.md files **and ≥ 2 stars**.
- Topics: `agent-skills`, `claude-code-plugin`, `gemini-cli-extension`,
  `mcp-server` (if 5), plus the domain (`gmail`, `tor`, …).

## 5. MCP server → official MCP Registry (→ Glama, PulseMCP)

Only when the tools justify it (a skill wrapping a CLI is often enough).

1. A stdio server (Python: FastMCP) behind an extra and a console script,
   e.g. `pip install "my-lib[mcp]"`, `my-lib-mcp`. Annotate tools
   (`readOnlyHint`, `destructiveHint`, `openWorldHint`).
2. `<!-- mcp-name: io.github.PabloAlaniz/<name> -->` in the README that
   becomes the PyPI description (the registry checks it).
3. [`templates/server.json`](templates/server.json) at the root
   (`mcp-publisher validate` checks it); same version as the package.
4. After the PyPI release, call `mcp-registry-publish.yml` (GitHub OIDC, no
   secret). Versions are immutable: bump every release.
5. Glama and PulseMCP pick it up within ~a day; claim it on Glama with
   [`templates/glama.json`](templates/glama.json). Then add the server to
   `plugin.json` (`mcpServers`) and `gemini-extension.json`.

## 6. Manual submissions (reviewed)

Prepare the text once (name, one-liner, long description, install, screenshots
if any, privacy/permissions notes) and submit:

| Where | How |
|---|---|
| ClawHub | automatic from CI (`clawhub-publish.yml`, `CLAWHUB_TOKEN` in a `clawhub` environment) |
| Anthropic directory | claude.ai/directory/manage (paid plan; review) |
| Cursor | cursor.directory (community, fast) / cursor.com/marketplace/publish (curated) |
| Codex / ChatGPT plugins | submission portal (review) |
| awesome-mcp-servers | PR to punkpeye/awesome-mcp-servers after the Glama listing |
| Smithery | `smithery mcp publish ./server.mcpb` (local bundle) |
| Docker MCP Catalog | PR to docker/mcp-registry; last, needs a container-friendly auth |

## 7. Measure

Add the project to [`stats/projects.json`](stats/projects.json) and run
`python stats/stats.py` (or the weekly workflow) to compare channels.

## Release wiring (example)

```yaml
# .github/workflows/release.yml, after the PyPI job
  skill:
    needs: [release, publish-pypi]
    uses: PabloAlaniz/google-suite/.github/workflows/reusable-clawhub-publish.yml@<commit-sha>
    with:
      skill-path: skills/my-lib
      slug: my-lib
      version: ${{ needs.release.outputs.version }}
      ref: v${{ needs.release.outputs.version }}
    secrets: inherit   # CLAWHUB_TOKEN, an environment secret of "clawhub"

  mcp-registry:
    needs: [release, publish-pypi]
    permissions:
      contents: read
      id-token: write
    uses: PabloAlaniz/google-suite/.github/workflows/reusable-mcp-registry-publish.yml@<commit-sha>
    with:
      ref: v${{ needs.release.outputs.version }}
```
