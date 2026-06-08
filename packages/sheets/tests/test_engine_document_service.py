"""Tests aislados de ``DocumentService`` con un cliente falso (sin gspread real)."""

from unittest.mock import Mock

import pytest
from gspreadmanager.application.document_service import DocumentService


@pytest.fixture
def service():
    return DocumentService()


def test_create(service):
    client = Mock()
    result = service.create(client, "Nuevo", "folder123")
    client.create.assert_called_once_with("Nuevo", folder_id="folder123")
    assert result is client.create.return_value


def test_delete(service):
    client = Mock()
    service.delete(client, "file123")
    client.del_spreadsheet.assert_called_once_with("file123")


def test_copy(service):
    client = Mock()
    service.copy(client, "file123", "Copia", True, "folder456")
    client.copy.assert_called_once_with(
        "file123", title="Copia", copy_permissions=True, folder_id="folder456"
    )


def test_list(service):
    client = Mock()
    client.list_spreadsheet_files.return_value = [{"id": "1", "name": "A"}]
    result = service.list(client, "A", None)
    client.list_spreadsheet_files.assert_called_once_with(title="A", folder_id=None)
    assert result == [{"id": "1", "name": "A"}]
