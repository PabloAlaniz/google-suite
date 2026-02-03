"""Tests for Gmail query builder."""

from gsuite_gmail import query as q


class TestQueryBuilder:
    """Tests for query builder functions."""

    def test_from_query(self):
        """Test from_ query."""
        query = q.from_("sender@example.com")
        assert str(query) == "from:sender@example.com"

    def test_to_query(self):
        """Test to query."""
        query = q.to("recipient@example.com")
        assert str(query) == "to:recipient@example.com"

    def test_subject_simple(self):
        """Test subject query without spaces."""
        query = q.subject("hello")
        assert str(query) == "subject:hello"

    def test_subject_with_spaces(self):
        """Test subject query with spaces (should quote)."""
        query = q.subject("hello world")
        assert str(query) == 'subject:"hello world"'

    def test_is_unread(self):
        """Test is_unread query."""
        query = q.is_unread()
        assert str(query) == "is:unread"

    def test_is_starred(self):
        """Test is_starred query."""
        query = q.is_starred()
        assert str(query) == "is:starred"

    def test_has_attachment(self):
        """Test has_attachment query."""
        query = q.has_attachment()
        assert str(query) == "has:attachment"

    def test_newer_than_days(self):
        """Test newer_than with days."""
        query = q.newer_than(days=7)
        assert str(query) == "newer_than:7d"

    def test_newer_than_months(self):
        """Test newer_than with months."""
        query = q.newer_than(months=3)
        assert str(query) == "newer_than:3m"

    def test_older_than(self):
        """Test older_than query."""
        query = q.older_than(days=30)
        assert str(query) == "older_than:30d"

    def test_label(self):
        """Test label query."""
        query = q.label("Work")
        assert str(query) == "label:Work"

    def test_label_with_spaces(self):
        """Test label query with spaces."""
        query = q.label("My Projects")
        assert str(query) == 'label:"My Projects"'

    def test_in_inbox(self):
        """Test in_inbox query."""
        query = q.in_inbox()
        assert str(query) == "in:inbox"

    def test_and_combination(self):
        """Test combining queries with AND."""
        query = q.is_unread() & q.from_("boss@company.com")
        assert str(query) == "is:unread from:boss@company.com"

    def test_or_combination(self):
        """Test combining queries with OR."""
        query = q.from_("alice@example.com") | q.from_("bob@example.com")
        assert str(query) == "(from:alice@example.com) OR (from:bob@example.com)"

    def test_negation(self):
        """Test negating a query."""
        query = ~q.is_starred()
        assert str(query) == "-(is:starred)"

    def test_complex_query(self):
        """Test complex query combination."""
        query = q.is_unread() & q.newer_than(days=7) & q.has_attachment()
        assert "is:unread" in str(query)
        assert "newer_than:7d" in str(query)
        assert "has:attachment" in str(query)

    def test_raw_query(self):
        """Test raw query string."""
        query = q.raw("category:promotions larger:1M")
        assert str(query) == "category:promotions larger:1M"


class TestConstructQuery:
    """Tests for construct_query function."""

    def test_empty_query(self):
        """Test empty construct_query."""
        query = q.construct_query()
        assert str(query) == ""

    def test_unread_only(self):
        """Test unread parameter."""
        query = q.construct_query(unread=True)
        assert str(query) == "is:unread"

    def test_from_parameter(self):
        """Test from_ parameter."""
        query = q.construct_query(from_="sender@example.com")
        assert str(query) == "from:sender@example.com"

    def test_multiple_parameters(self):
        """Test multiple parameters."""
        query = q.construct_query(
            unread=True,
            from_="boss@company.com",
            newer_than=(7, "day"),
        )
        result = str(query)
        assert "is:unread" in result
        assert "from:boss@company.com" in result
        assert "newer_than:7d" in result

    def test_labels_parameter(self):
        """Test labels parameter."""
        query = q.construct_query(labels=["Work", "Important"])
        result = str(query)
        assert "label:Work" in result
        assert "label:Important" in result

    def test_exclude_starred(self):
        """Test exclude_starred parameter."""
        query = q.construct_query(exclude_starred=True)
        assert str(query) == "-is:starred"
