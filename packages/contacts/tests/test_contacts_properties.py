"""Property-based tests for gsuite_contacts.parser (see gsuite_contacts._testing.properties)."""

from hypothesis import given
from hypothesis import strategies as st

from gsuite_contacts._testing.properties import check_person_round_trip

texts = st.none() | st.text(max_size=30)
values = st.none() | st.lists(st.text(max_size=30), max_size=4)


@given(texts, texts, values, values, texts, texts, texts)
def test_build_then_parse_round_trips(given_name, family, emails, phones, org, title, notes):
    check_person_round_trip(given_name, family, emails, phones, org, title, notes)
