# Getting Google OAuth Credentials

This guide walks you through creating OAuth credentials to use google-suite.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Enter a project name (e.g., "My Google Suite App")
4. Click **Create**

## Step 2: Enable APIs

Enable the APIs you want to use:

1. Go to **APIs & Services > Library**
2. Search for and enable:
   - **Gmail API** (for gsuite-gmail)
   - **Google Calendar API** (for gsuite-calendar)
   - **Google Drive API** (for gsuite-drive)
   - **Google Sheets API** (for gsuite-sheets)
   - **Google Tasks API** (for gsuite-tasks)
   - **People API** (for gsuite-contacts)

Click each one and press **Enable**.

## Step 3: Configure OAuth Consent Screen

Before creating credentials, you need to configure the consent screen:

1. Go to **APIs & Services > OAuth consent screen**
2. Select **External** (or Internal if using Google Workspace)
3. Click **Create**
4. Fill in required fields:
   - **App name**: Your app name
   - **User support email**: Your email
   - **Developer contact**: Your email
5. Click **Save and Continue**

### Add Scopes

1. Click **Add or Remove Scopes**
2. Add the scopes you need:
   - Gmail: `https://www.googleapis.com/auth/gmail.modify`
   - Calendar: `https://www.googleapis.com/auth/calendar`
   - Drive: `https://www.googleapis.com/auth/drive`
   - Sheets: `https://www.googleapis.com/auth/spreadsheets`
3. Click **Save and Continue**

`gsuite auth login` requests all four by default. Sheets needs the Drive scope
too: opening a spreadsheet by title, listing, sharing and exporting go through
Drive. If you logged in with an older version (Drive wasn't in the default),
run `gsuite auth login --force` once to grant it.

### Add Test Users

While in testing mode, you must add users who can use your app:

1. Click **Add Users**
2. Enter email addresses (including your own)
3. Click **Save and Continue**

## Step 4: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Select **Desktop app** as the application type
4. Enter a name (e.g., "Desktop Client")
5. Click **Create**

## Step 5: Download Credentials

1. Find your new credential in the list
2. Click the download icon (⬇️) on the right
3. Save the file as `credentials.json`
4. Place it in your project directory

The file looks like this:

```json
{
  "installed": {
    "client_id": "xxxxx.apps.googleusercontent.com",
    "project_id": "your-project",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_secret": "GOCSPX-xxxxx",
    "redirect_uris": ["http://localhost"]
  }
}
```

## Step 6: First Authentication

Run authentication to get your OAuth tokens:

```bash
# Using CLI
gsuite auth login

# Or in Python
from gsuite_core import GoogleAuth
auth = GoogleAuth()
auth.authenticate()  # Opens browser
```

This will:
1. Open your browser
2. Ask you to sign in with Google
3. Request permission for the scopes you configured
4. Save the tokens locally for future use

### On a machine without a browser (SSH, a Raspberry Pi, a server)

```bash
gsuite auth login --no-browser
```

It prints the consent URL. Open it in any browser, allow access, and paste back
the address the browser ends on (a `http://localhost/...` page that doesn't
load; it carries the code). This works with **Desktop app** credentials.

An app that does this from its own UI uses the same two steps, with PKCE:

```python
from gsuite_core import AuthorizationRequest, GoogleAuth

# Client ID and secret from your settings page, env (GSUITE_CLIENT_ID /
# GSUITE_CLIENT_SECRET) or a credentials.json, whichever you have
auth = GoogleAuth.from_client_config(client_id, client_secret, token_store=MyStore())

request = auth.start_authorization()          # show request.url to the user
saved = request.to_dict()                     # keep it until they come back
...
auth.finish_authorization(AuthorizationRequest.from_dict(saved), pasted_code_or_url)
```

A web client passes its registered URI: `start_authorization("https://app.example/oauth/callback")`.

### Keeping tokens in your app's database

Tokens go to a `TokenStore`: SQLite by default, Secret Manager on Cloud Run,
or your own. Subclass it and pass it as `token_store`:

```python
from gsuite_core import TokenStore

class MyStore(TokenStore):
    def get_token(self, user_id="default"): ...      # the dict saved below, or None
    def save_token(self, token_data, user_id="default"): ...
    def delete_token(self, user_id="default"): ...   # True if one was deleted
    def exists(self, user_id="default"): ...
```

### Signing out

`auth.revoke()` (and `gsuite auth logout`) revokes the grant at Google, so the
app disappears from the account's permissions, and then deletes the stored
token. If Google can't be reached it logs a warning and still deletes the local
token. To only forget the token locally, use `auth.revoke(remote=False)` or
`gsuite auth logout --local-only`.

## Publishing Your App

While in **testing** mode:
- Only test users can authenticate
- Tokens expire after 7 days

To remove these limitations:
1. Go to **OAuth consent screen**
2. Click **Publish App**
3. Follow the verification process (may require review for sensitive scopes)

## Security Notes

⚠️ **Never commit `credentials.json` to version control!**

The credentials file contains your client secret. If exposed, anyone could impersonate your application.

Add to `.gitignore`:
```
credentials.json
**/credentials.json
token.json
**/token.json
tokens.db
**/tokens.db
```

## Troubleshooting

### "Access blocked: This app's request is invalid"

- Check that redirect_uris includes `http://localhost`
- Ensure you're using a Desktop app credential type

### "Error 403: access_denied"

- Your email isn't in the test users list
- The app is in testing mode and you need to add your email

### "The OAuth client was not found"

- The credentials file may be corrupted
- Re-download from Google Cloud Console

### Tokens expire after 7 days

- This happens in testing mode
- Publish your app to remove this limitation
- Or re-authenticate when tokens expire

## For Production / Cloud Run

For server-side deployments, use a **Service Account** instead:

1. Go to **Credentials > Create Credentials > Service Account**
2. Download the JSON key
3. Use domain-wide delegation for user data access

See [Service Account Setup](./SERVICE_ACCOUNTS.md) for details.
