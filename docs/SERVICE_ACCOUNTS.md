# Service Account Setup

Service accounts are useful for server-to-server authentication without user interaction.

## When to Use Service Accounts

- **Automated scripts** that run without user presence
- **Backend services** that access Google APIs
- **Domain-wide delegation** for G Suite/Workspace admins

## Creating a Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **IAM & Admin > Service Accounts**
4. Click **Create Service Account**
5. Fill in the details:
   - Name: `gsuite-service`
   - ID: auto-generated
6. Click **Create and Continue**
7. (Optional) Grant roles if needed
8. Click **Done**

## Generating a Key

1. Click on your new service account
2. Go to **Keys** tab
3. Click **Add Key > Create new key**
4. Select **JSON**
5. Save the file as `service-account.json`

> ⚠️ **Never commit this file!** It's in `.gitignore` by default.

## Using with google-suite

```python
from gsuite_core import GoogleAuth

# From service account file
auth = GoogleAuth.from_service_account("service-account.json")

# Use with any client
from gsuite_gmail import GmailClient
gmail = GmailClient(auth)
```

## Domain-Wide Delegation

For accessing other users' data in a Workspace domain:

1. In Google Cloud Console, edit your service account
2. Enable **Domain-wide delegation**
3. Note the **Client ID**
4. In Google Admin Console:
   - Go to **Security > API Controls > Domain-wide Delegation**
   - Add new API client
   - Enter the Client ID
   - Add required scopes

```python
# Impersonate a user
auth = GoogleAuth.from_service_account(
    "service-account.json",
    subject="user@yourdomain.com"  # User to impersonate
)
```

## Security Best Practices

- **Rotate keys** regularly
- **Use minimal scopes** required for your use case
- **Store keys securely** (Secret Manager, environment variables)
- **Never commit** service account keys to git
- **Audit usage** in Cloud Console

## Environment Variables

```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
```

Or configure in code:

```python
auth = GoogleAuth.from_service_account(
    credentials_file="path/to/service-account.json"
)
```
