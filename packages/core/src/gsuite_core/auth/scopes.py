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
    CONTACTS_READONLY = "https://www.googleapis.com/auth/contacts.readonly"

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
    def all(cls) -> list[str]:
        """All standard scopes for full access."""
        return cls.gmail() + cls.calendar() + cls.drive() + cls.sheets()

    @classmethod
    def default(cls) -> list[str]:
        """Default scopes (Gmail + Calendar)."""
        return cls.gmail() + cls.calendar()
