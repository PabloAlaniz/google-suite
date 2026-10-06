# Security Policy

## Supported versions

Only the latest release of `gsuite-sdk` receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub Security Advisories](https://github.com/PabloAlaniz/google-suite/security/advisories/new).

Include the affected version, a description of the issue and steps to
reproduce it. You can expect an initial response within 7 days.

## Scope notes

This SDK handles Google OAuth tokens. Reports about token storage
(`SQLiteTokenStore`, `SecretManagerTokenStore`), the REST API's
authentication (`X-API-Key`, admin endpoints) or credential leakage in logs
are especially welcome.
