# gsuite-cli

Unified command-line interface for Google Workspace.

## Installation

```bash
pip install gsuite-cli
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
# List recent messages
gsuite gmail list
gsuite gmail list --max 20

# List unread messages
gsuite gmail list --unread

# List starred messages  
gsuite gmail list --starred

# Search messages
gsuite gmail search "from:boss@company.com has:attachment"
gsuite gmail search --from boss@company.com --newer 7d

# Read a message
gsuite gmail read MESSAGE_ID
gsuite gmail read MESSAGE_ID --format json

# Send email
gsuite gmail send --to user@example.com --subject "Hello" --body "World"
gsuite gmail send --to user@example.com --subject "Report" --attach report.pdf

# Interactive compose
gsuite gmail compose

# List labels
gsuite gmail labels

# Mark as read/unread
gsuite gmail mark MESSAGE_ID --read
gsuite gmail mark MESSAGE_ID --unread

# Archive message
gsuite gmail archive MESSAGE_ID

# Trash message
gsuite gmail trash MESSAGE_ID
```

## Calendar Commands

```bash
# Today's events
gsuite calendar today

# This week's events
gsuite calendar week

# Upcoming events
gsuite calendar list
gsuite calendar list --days 14

# Specific date range
gsuite calendar list --from 2026-02-01 --to 2026-02-28

# List all calendars
gsuite calendar calendars

# Events from specific calendar
gsuite calendar list --calendar work@company.com

# Create event
gsuite calendar create "Team Meeting" --start "2026-02-15 10:00" --end "2026-02-15 11:00"
gsuite calendar create "All Day Event" --start 2026-02-20 --all-day

# Quick add (natural language)
gsuite calendar quick "Lunch with John tomorrow at noon"

# Delete event
gsuite calendar delete EVENT_ID
```

## Drive Commands

```bash
# List files
gsuite drive list
gsuite drive list --folder FOLDER_ID

# Search files
gsuite drive search "quarterly report"

# File info
gsuite drive info FILE_ID

# Download file
gsuite drive download FILE_ID
gsuite drive download FILE_ID --output local_name.pdf

# Upload file
gsuite drive upload document.pdf
gsuite drive upload document.pdf --folder FOLDER_ID

# Create folder
gsuite drive mkdir "New Folder"
gsuite drive mkdir "Subfolder" --parent FOLDER_ID

# Delete file (to trash)
gsuite drive delete FILE_ID

# Share file
gsuite drive share FILE_ID --email user@example.com --role reader
```

## Sheets Commands

```bash
# List worksheets in spreadsheet
gsuite sheets list SPREADSHEET_ID

# Read data
gsuite sheets read SPREADSHEET_ID
gsuite sheets read SPREADSHEET_ID --sheet "Sheet1" --range "A1:C10"

# Read as table
gsuite sheets read SPREADSHEET_ID --format table

# Read as JSON
gsuite sheets read SPREADSHEET_ID --format json

# Write data
gsuite sheets write SPREADSHEET_ID --sheet "Sheet1" --range "A1" --value "Hello"

# Write from CSV
gsuite sheets import SPREADSHEET_ID data.csv
gsuite sheets import SPREADSHEET_ID data.csv --sheet "Imported"

# Export to CSV
gsuite sheets export SPREADSHEET_ID --output data.csv
```

## Server Commands

```bash
# Start REST API server
gsuite serve
gsuite serve --port 9000
gsuite serve --host 0.0.0.0 --port 8080

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
