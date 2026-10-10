# MCP server

`gsuite-mcp` exposes the same capabilities as MCP tools, for clients that
prefer MCP over running the CLI (Claude Desktop, Cursor, VS Code, ...). It
runs locally over stdio and uses the login saved by `gsuite auth login`.

```bash
pip install "gsuite-sdk[cli]"
gsuite auth login --scopes default,tasks,contacts
claude mcp add gsuite -e GSUITE_TOKEN_DB_PATH="$PWD/tokens.db" -- uvx gsuite-mcp
```

For other clients, the server entry is `uvx gsuite-mcp` with
`GSUITE_TOKEN_DB_PATH` (and `GSUITE_CREDENTIALS_FILE`) set to **absolute**
paths: the server doesn't run from the directory where you logged in.

Tools (read-only ones are annotated so clients can run them without asking):

| Area | Tools |
|---|---|
| Account | `auth_status` |
| Gmail | `gmail_search`, `gmail_read`, `gmail_send`, `gmail_reply`, `gmail_create_draft` |
| Calendar | `calendar_list_events`, `calendar_create_event`, `calendar_delete_event`, `calendar_free_busy` |
| Drive | `drive_search`, `drive_read_file` (Docs as text, Sheets as CSV), `drive_upload`, `drive_share` |
| Sheets | `sheets_read`, `sheets_append`, `sheets_update`, `sheets_upsert` |
| Tasks | `tasks_list`, `tasks_add`, `tasks_complete` |
| Contacts | `contacts_search`, `contacts_get` |

List results come back as `{"count": n, "results": [...]}`. Errors are tool
errors with a hint: no login → run `gsuite auth login`; a missing scope →
`gsuite auth login --force --scopes default,tasks,contacts`.
