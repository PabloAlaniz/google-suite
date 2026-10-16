"""Google API OAuth scopes."""


class Scopes:
    """
    Google API OAuth scopes.

    Use these constants to request specific permissions.
    """

    # Gmail
    GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
    GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
    GMAIL_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
    GMAIL_LABELS = "https://www.googleapis.com/auth/gmail.labels"
    GMAIL_FULL = "https://mail.google.com/"

    # Calendar
    CALENDAR_FULL = "https://www.googleapis.com/auth/calendar"
    CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"
    CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"

    # Drive
    DRIVE_FULL = "https://www.googleapis.com/auth/drive"
    DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
    DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
    DRIVE_METADATA = "https://www.googleapis.com/auth/drive.metadata.readonly"

    # Sheets
    SHEETS_FULL = "https://www.googleapis.com/auth/spreadsheets"
    SHEETS_READONLY = "https://www.googleapis.com/auth/spreadsheets.readonly"

    # Tasks
    TASKS_FULL = "https://www.googleapis.com/auth/tasks"
    TASKS_READONLY = "https://www.googleapis.com/auth/tasks.readonly"

    # Contacts/People
    CONTACTS_FULL = "https://www.googleapis.com/auth/contacts"
    CONTACTS_READONLY = "https://www.googleapis.com/auth/contacts.readonly"

    # Search Console, Google Analytics, Tag Manager (read-only, opt-in)
    WEBMASTERS_READONLY = "https://www.googleapis.com/auth/webmasters.readonly"
    ANALYTICS_READONLY = "https://www.googleapis.com/auth/analytics.readonly"
    TAGMANAGER_READONLY = "https://www.googleapis.com/auth/tagmanager.readonly"

    # User info
    USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
    USERINFO_PROFILE = "https://www.googleapis.com/auth/userinfo.profile"

    @classmethod
    def gmail(cls) -> list[str]:
        """Standard Gmail scopes for read, send, modify."""
        return [
            cls.GMAIL_READONLY,
            cls.GMAIL_SEND,
            cls.GMAIL_MODIFY,
            cls.GMAIL_LABELS,
        ]

    @classmethod
    def calendar(cls) -> list[str]:
        """Standard Calendar scopes."""
        return [
            cls.CALENDAR_FULL,
            cls.CALENDAR_EVENTS,
        ]

    @classmethod
    def drive(cls) -> list[str]:
        """Standard Drive scopes."""
        return [
            cls.DRIVE_FULL,
        ]

    @classmethod
    def sheets(cls) -> list[str]:
        """Standard Sheets scopes."""
        return [
            cls.SHEETS_FULL,
        ]

    @classmethod
    def tasks(cls) -> list[str]:
        """Standard Tasks scopes."""
        return [
            cls.TASKS_FULL,
        ]

    @classmethod
    def contacts(cls) -> list[str]:
        """Standard Contacts (People API) scopes."""
        return [
            cls.CONTACTS_FULL,
        ]

    @classmethod
    def searchconsole(cls) -> list[str]:
        """Search Console, read-only."""
        return [cls.WEBMASTERS_READONLY]

    @classmethod
    def analytics(cls) -> list[str]:
        """Google Analytics 4 (Admin and Data APIs), read-only."""
        return [cls.ANALYTICS_READONLY]

    @classmethod
    def tagmanager(cls) -> list[str]:
        """Tag Manager, read-only."""
        return [cls.TAGMANAGER_READONLY]

    @classmethod
    def marketing(cls) -> list[str]:
        """Search Console + Analytics + Tag Manager, all read-only.

        Opt-in: not part of ``default()`` or ``all()``, so existing logins are
        not asked to re-consent. Add it with
        ``gsuite auth login --force --scopes default,marketing``.
        """
        return cls.searchconsole() + cls.analytics() + cls.tagmanager()

    @classmethod
    def all(cls) -> list[str]:
        """All standard scopes for full access."""
        return (
            cls.gmail() + cls.calendar() + cls.drive() + cls.sheets() + cls.tasks() + cls.contacts()
        )

    @classmethod
    def default(cls) -> list[str]:
        """Default scopes: Gmail, Calendar, Drive and Sheets.

        Drive used to be missing, so a default login got 403s from the Drive
        client and from the Sheets calls that go through Drive (open by title,
        list, share, export). Tokens created before need `gsuite auth login --force`.

        Tasks and Contacts are left out on purpose: contacts is a sensitive
        scope, and asking for both on every login would over-ask. Request them
        with `Scopes.all()` or `gsuite auth login --scopes all`.
        """
        return cls.gmail() + cls.calendar() + cls.drive() + cls.sheets()
