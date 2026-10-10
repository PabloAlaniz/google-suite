# gsuite-mcp

<!-- mcp-name: io.github.PabloAlaniz/gsuite-sdk -->

An [MCP](https://modelcontextprotocol.io) server for Google Workspace: Gmail,
Calendar, Drive, Sheets, Tasks and Contacts, built on
[gsuite-sdk](https://pypi.org/project/gsuite-sdk/). It runs locally over stdio
and uses your own Google login.

## Setup

1. Get an OAuth client file from Google Cloud
   ([guide](https://pabloalaniz.github.io/google-suite/GETTING_CREDENTIALS/))
   and log in once with the gsuite CLI:

   ```bash
   pip install "gsuite-sdk[cli]"
   gsuite auth login                                   # Gmail, Calendar, Drive, Sheets
   gsuite auth login --force --scopes default,tasks,contacts   # + Tasks and Contacts
   ```

   The token is saved to `tokens.db` in the current directory (or
   `GSUITE_TOKEN_DB_PATH`).

2. Add the server to your MCP client, pointing at that token with absolute
   paths:

   ```json
   {
     "mcpServers": {
       "gsuite": {
         "command": "uvx",
         "args": ["gsuite-mcp"],
         "env": {
           "GSUITE_TOKEN_DB_PATH": "/Users/you/gsuite/tokens.db",
           "GSUITE_CREDENTIALS_FILE": "/Users/you/gsuite/credentials.json",
           "GSUITE_DEFAULT_TIMEZONE": "America/Argentina/Buenos_Aires"
         }
       }
     }
   }
   ```

   Claude Code: `claude mcp add gsuite -e GSUITE_TOKEN_DB_PATH=/Users/you/gsuite/tokens.db -- uvx gsuite-mcp`

## Tools

| Area | Tools |
|---|---|
| Account | `auth_status` |
| Gmail | `gmail_search`, `gmail_read`, `gmail_send`, `gmail_reply`, `gmail_create_draft` |
| Calendar | `calendar_list_events`, `calendar_create_event`, `calendar_delete_event`, `calendar_free_busy` |
| Drive | `drive_search`, `drive_read_file`, `drive_upload`, `drive_share` |
| Sheets | `sheets_read`, `sheets_append`, `sheets_update`, `sheets_upsert` |
| Tasks | `tasks_list`, `tasks_add`, `tasks_complete` |
| Contacts | `contacts_search`, `contacts_get` |

Read tools are annotated read-only; tools that send, share, overwrite or
delete are marked so clients can ask before running them. Dates are ISO 8601;
times without an offset use `GSUITE_DEFAULT_TIMEZONE` (UTC by default).

The same capabilities are available as an [agent skill](https://github.com/PabloAlaniz/google-suite/tree/main/skills/gsuite-sdk),
a CLI and a REST API: see [gsuite-sdk](https://pabloalaniz.github.io/google-suite/).

## License

MIT
