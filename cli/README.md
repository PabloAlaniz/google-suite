# gsuite-cli

Unified command-line interface for Google Workspace.

## Installation

```bash
pip install "gsuite-sdk[cli]"
```

This installs all gsuite packages and the `gsuite` command.

## Quick Start

```bash
# Authenticate (opens browser)
gsuite auth login

# Check status
gsuite status

# Start using!
gsuite gmail list --unread
gsuite calendar today
```

## Authentication

```bash
# Interactive OAuth login (opens browser)
gsuite auth login

# Login with specific scopes
gsuite auth login --scopes gmail,calendar

# Login with all scopes
gsuite auth login --scopes all

# Check auth status
gsuite auth status

# Show current user info
gsuite auth whoami

# Logout (delete tokens)
gsuite auth logout

# Export token (for Cloud Run deployment)
gsuite auth export > token.json
```

## Gmail Commands

```bash
# List messages (table or json)
gsuite gmail list
gsuite gmail list --limit 20 --unread
gsuite gmail list --starred --from boss@company.com
gsuite gmail list -q "has:attachment newer_than:7d" -o json

# Search with Gmail query syntax
gsuite gmail search "from:boss@company.com has:attachment"

# Read a message
gsuite gmail read MESSAGE_ID
gsuite gmail read MESSAGE_ID --mark-read -o json

# Send (body from --body or stdin)
gsuite gmail send --to user@example.com --subject "Hello" --body "World"
gsuite gmail send --to user@example.com --subject "Report" --attach report.pdf --attach data.csv
echo "Body from a pipe" | gsuite gmail send --to user@example.com --subject "Piped"

# Reply in the same thread
gsuite gmail reply MESSAGE_ID --body "Thanks!"
gsuite gmail reply MESSAGE_ID --all --body "Thanks, all"

# Labels, marking, archiving
gsuite gmail labels
gsuite gmail mark MESSAGE_ID --read
gsuite gmail mark MESSAGE_ID --unread --star
gsuite gmail archive MESSAGE_ID
gsuite gmail trash MESSAGE_ID

gsuite gmail profile
```

## Calendar Commands

```bash
gsuite calendar today
gsuite calendar week
gsuite calendar list --days 14
gsuite calendar list --calendar work@company.com -o json
gsuite calendar calendars

# Create (naive times are in GSUITE_DEFAULT_TIMEZONE)
gsuite calendar create "Team Meeting" --start "2026-02-15 10:00" --end "2026-02-15 11:00"
gsuite calendar create "All Day Event" --start 2026-02-20 --all-day
gsuite calendar create "Sync" --start "2026-02-16 09:00" --meet -a ana@example.com --notify
gsuite calendar create "Standup" --start "2026-02-16 09:00" --repeat "FREQ=WEEKLY;BYDAY=MO,WE,FR"

# Quick add (natural language)
gsuite calendar quick "Lunch with John tomorrow at noon"

gsuite calendar delete EVENT_ID
```

## Drive Commands

```bash
# List files (newest first)
gsuite drive list
gsuite drive list FOLDER_ID
gsuite drive list --name "quarterly report"
gsuite drive list --trashed
gsuite drive list -o json

# File info and who has access
gsuite drive info FILE_ID

# Download (Google Docs/Sheets/Slides are exported; docx/xlsx/pptx by default)
gsuite drive download FILE_ID
gsuite drive download FILE_ID --out local_name.pdf
gsuite drive download DOC_ID --export pdf

# Upload (resumable, with a progress bar)
gsuite drive upload document.pdf
gsuite drive upload document.pdf --to FOLDER_ID --name "Q1 Report.pdf"

# Folders and moving
gsuite drive mkdir "New Folder" --in PARENT_ID
gsuite drive move FILE_ID FOLDER_ID

# Delete (to trash; --permanent asks for confirmation unless -y)
gsuite drive delete FILE_ID
gsuite drive delete FILE_ID --permanent -y

# Share
gsuite drive share FILE_ID user@example.com --role writer
gsuite drive share FILE_ID --anyone
```

`ls`, `mv` and `rm` work as aliases.

## Sheets Commands

SPREADSHEET can be a title, an ID or a URL.

```bash
# Spreadsheets and their worksheets
gsuite sheets list
gsuite sheets open SPREADSHEET
gsuite sheets create "Budget 2026"

# Read (table, json or csv)
gsuite sheets read SPREADSHEET
gsuite sheets read SPREADSHEET --sheet "Data" --range "A1:C10"
gsuite sheets read SPREADSHEET -o csv > data.csv

# Write and append (--raw stores "=..." as text instead of a formula)
gsuite sheets write SPREADSHEET --cell A1 --value "Hello"
gsuite sheets append SPREADSHEET -v Alice -v 30 -v NYC --sheet "Data"

# Find and replace (all sheets unless --sheet)
gsuite sheets replace SPREADSHEET "2025" "2026"
gsuite sheets replace SPREADSHEET "Mr\." "Mr" --regex

# Worksheets
gsuite sheets add-tab SPREADSHEET "Q2"
gsuite sheets rename-tab SPREADSHEET "Q2" "Q2 2026"
gsuite sheets delete-tab SPREADSHEET "Q2 2026"
gsuite sheets freeze SPREADSHEET --rows 1
```

## Server Commands

```bash
# Start REST API server
gsuite serve
gsuite serve --port 9000
gsuite serve --port 8080              # localhost only
gsuite serve --host 0.0.0.0 --port 8080   # reachable from your network

# With auto-reload (development)
gsuite serve --reload
```

## Global Options

```bash
# Verbose output
gsuite --verbose gmail list

# JSON output (for scripting)
gsuite --json calendar today

# Quiet mode (errors only)
gsuite --quiet gmail send ...

# Specify credentials file
gsuite --credentials /path/to/creds.json auth login

# Help
gsuite --help
gsuite gmail --help
gsuite gmail send --help
```

## Configuration

The CLI uses the same configuration as the Python library:

```bash
# Set via environment
export GSUITE_CREDENTIALS_FILE=/path/to/credentials.json
export GSUITE_TOKEN_DB_PATH=/path/to/tokens.db

# Or use flags
gsuite --credentials /path/to/creds.json auth login
```

## Scripting Examples

```bash
# Get unread count
UNREAD=$(gsuite --json gmail list --unread | jq length)
echo "You have $UNREAD unread messages"

# Export today's events to JSON
gsuite --json calendar today > today_events.json

# Send notification if calendar has events
if gsuite --quiet calendar today; then
  echo "You have events today!"
fi

# Batch download files
gsuite --json drive list --folder FOLDER_ID | \
  jq -r '.[].id' | \
  xargs -I {} gsuite drive download {}
```

## Shell Completion

```bash
# Bash
gsuite --install-completion bash

# Zsh
gsuite --install-completion zsh

# Fish
gsuite --install-completion fish
```

## License

MIT
