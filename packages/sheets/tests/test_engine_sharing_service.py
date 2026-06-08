"""Tests aislados de ``SharingService`` con un documento falso (sin gspread real)."""

from unittest.mock import Mock

import pytest
from gspreadmanager.application.sharing_service import SharingService


@pytest.fixture
def service():
    return SharingService()


def test_share(service):
    spreadsheet = Mock()
    service.share(spreadsheet, "a@b.com", "writer", "user", True, "hola", False)
    spreadsheet.share.assert_called_once_with(
        "a@b.com",
        perm_type="user",
        role="writer",
        notify=True,
        email_message="hola",
        with_link=False,
    )


def test_list_permissions(service):
    spreadsheet = Mock()
    spreadsheet.list_permissions.return_value = [{"id": "p1"}]
    assert service.list_permissions(spreadsheet) == [{"id": "p1"}]


def test_remove_permission(service):
    spreadsheet = Mock()
    spreadsheet.remove_permissions.return_value = ["p1"]
    result = service.remove_permission(spreadsheet, "a@b.com", "writer")
    spreadsheet.remove_permissions.assert_called_once_with("a@b.com", role="writer")
    assert result == ["p1"]
