"""Tests for OAuth scopes."""

from gsuite_core.auth.scopes import Scopes


class TestScopes:
    """Test Scopes class."""

    def test_gmail_scopes(self):
        """Gmail scopes should include read, send, modify, labels."""
        scopes = Scopes.gmail()
        assert len(scopes) == 4
        assert Scopes.GMAIL_READONLY in scopes
        assert Scopes.GMAIL_SEND in scopes
        assert Scopes.GMAIL_MODIFY in scopes
        assert Scopes.GMAIL_LABELS in scopes

    def test_calendar_scopes(self):
        """Calendar scopes should include full and events."""
        scopes = Scopes.calendar()
        assert Scopes.CALENDAR_FULL in scopes
        assert Scopes.CALENDAR_EVENTS in scopes

    def test_default_scopes(self):
        """Default scopes should be Gmail + Calendar."""
        scopes = Scopes.default()
        assert all(s in scopes for s in Scopes.gmail())
        assert all(s in scopes for s in Scopes.calendar())

    def test_all_scopes(self):
        """All scopes should include everything."""
        scopes = Scopes.all()
        assert all(s in scopes for s in Scopes.gmail())
        assert all(s in scopes for s in Scopes.calendar())
        assert all(s in scopes for s in Scopes.drive())
        assert all(s in scopes for s in Scopes.sheets())
