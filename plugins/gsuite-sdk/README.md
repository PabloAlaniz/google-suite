# gsuite-sdk plugin for Claude Code

Gmail, Google Calendar, Drive, Sheets, Tasks and Contacts for Claude, from
[gsuite-sdk](https://github.com/PabloAlaniz/google-suite) (MIT).

It ships:

- **The `gsuite-sdk` skill**: how to use the `gsuite` CLI (JSON output) and the
  Python SDK, with one reference page per service.
- **The `gsuite` MCP server**: [gsuite-mcp](https://pypi.org/project/gsuite-mcp/)
  from PyPI, run with `uvx` at a pinned version. It runs locally over stdio
  and exposes 23 tools (search and read mail, send and reply, list and create
  events, search, read, upload and share Drive files, read and write Sheets,
  tasks, contacts). Tools that send, share, overwrite or delete are marked
  as destructive in their MCP annotations.

## Setup

Log in once with your own Google OAuth client
([how to get one](https://pabloalaniz.github.io/google-suite/GETTING_CREDENTIALS/)):

```bash
pip install "gsuite-sdk[cli]"
gsuite auth login --scopes default,tasks,contacts
```

Set `GSUITE_TOKEN_DB_PATH` to the absolute path of the `tokens.db` that login
wrote, so the MCP server finds it.

## Data

- The server and the CLI talk only to Google: its APIs (`*.googleapis.com`)
  and its OAuth sign-in, with your own OAuth client and token. The token stays
  in the local `tokens.db`.
- Nothing is sent to the plugin author or any other server, and there is no
  telemetry.
- What Claude reads (emails, files, events) goes into the conversation like
  any other tool result.

This branch (`claude-plugin`) is generated from `plugins/gsuite-sdk` on `main`
by the release workflow; open issues and PRs against `main`.
