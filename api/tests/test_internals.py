"""Dependencies, logging setup and app lifespan."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from gsuite_api import dependencies
from gsuite_api.observability import JsonFormatter, RequestIdFilter, configure_logging
from gsuite_core import Settings
from gsuite_core.exceptions import NotAuthenticatedError


class TestAuthenticatedAuth:
    def test_valid_credentials(self):
        auth = MagicMock()
        auth.is_authenticated.return_value = True

        assert dependencies.get_authenticated_auth(auth) is auth
        auth.refresh.assert_not_called()

    def test_expired_credentials_are_refreshed(self):
        auth = MagicMock()
        auth.is_authenticated.return_value = False
        auth.needs_refresh.return_value = True

        assert dependencies.get_authenticated_auth(auth) is auth
        auth.refresh.assert_called_once_with()

    def test_no_credentials(self):
        auth = MagicMock()
        auth.is_authenticated.return_value = False
        auth.needs_refresh.return_value = False

        with pytest.raises(NotAuthenticatedError):
            dependencies.get_authenticated_auth(auth)


class TestGetAuth:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        dependencies.get_auth.cache_clear()
        yield
        dependencies.get_auth.cache_clear()

    def test_sqlite_store(self, tmp_path):
        settings = Settings(token_db_path=str(tmp_path / "tokens.db"), _env_file=None)
        with patch.object(dependencies, "get_settings", return_value=settings):
            auth = dependencies.get_auth()

        assert auth.token_store.db_path == tmp_path / "tokens.db"

    def test_secret_manager_store(self):
        settings = Settings(token_storage="secretmanager", gcp_project_id="proj", _env_file=None)
        with (
            patch.object(dependencies, "get_settings", return_value=settings),
            patch("gsuite_core.SecretManagerTokenStore") as store,
        ):
            dependencies.get_auth()

        store.assert_called_once_with(project_id="proj", secret_name="gsuite-token")

    def test_secret_manager_requires_project(self):
        settings = Settings(token_storage="secretmanager", _env_file=None)
        with (
            patch.object(dependencies, "get_settings", return_value=settings),
            pytest.raises(ValueError, match="GSUITE_GCP_PROJECT_ID"),
        ):
            dependencies.get_auth()


@pytest.mark.parametrize(
    ("factory", "cls"),
    [
        (dependencies.get_gmail, "Gmail"),
        (dependencies.get_calendar, "Calendar"),
        (dependencies.get_drive, "Drive"),
        (dependencies.get_sheets, "Sheets"),
    ],
)
def test_client_factories(factory, cls):
    auth = MagicMock()
    assert type(factory(auth)).__name__ == cls


@pytest.fixture
def restore_loggers():
    names = [
        "gsuite_api",
        "gsuite_core",
        "gsuite_gmail",
        "gsuite_calendar",
        "gsuite_drive",
        "gsuite_sheets",
    ]
    saved = {
        n: (
            logging.getLogger(n).handlers[:],
            logging.getLogger(n).level,
            logging.getLogger(n).propagate,
        )
        for n in names
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        log = logging.getLogger(name)
        log.handlers, log.level, log.propagate = handlers, level, propagate


class TestLogging:
    def _record(self, **extra):
        record = logging.LogRecord(
            "gsuite_api.x", logging.WARNING, __file__, 1, "hello %s", ("world",), None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        RequestIdFilter().filter(record)
        return record

    def test_json_formatter(self):
        line = JsonFormatter().format(self._record(status=200, duration_ms=1.5))

        assert json.loads(line) == {
            "severity": "WARNING",
            "message": "hello world",
            "logger": "gsuite_api.x",
            "request_id": "-",
            "status": 200,
            "duration_ms": 1.5,
        }

    def test_json_formatter_includes_exception(self):
        try:
            raise ValueError("bad")
        except ValueError:
            import sys

            record = self._record()
            record.exc_info = sys.exc_info()

        assert "ValueError: bad" in json.loads(JsonFormatter().format(record))["exception"]

    @pytest.mark.parametrize("fmt", ["text", "json"])
    def test_configure_logging(self, restore_loggers, fmt):
        configure_logging("debug", fmt)

        log = logging.getLogger("gsuite_api")
        assert log.level == logging.DEBUG
        assert log.propagate is False
        assert isinstance(log.handlers[0].formatter, JsonFormatter) is (fmt == "json")


class TestLifespan:
    @pytest.mark.parametrize(
        ("settings", "expected"),
        [
            (Settings(_env_file=None), "every API request will be rejected"),
            (Settings(allow_no_api_key=True, _env_file=None), "accepts requests without a key"),
        ],
    )
    def test_warns_about_missing_key(self, make_client, caplog, settings, expected):
        with (
            patch("gsuite_api.main.configure_logging"),
            caplog.at_level(logging.WARNING, logger="gsuite_api.main"),
            make_client(settings),
        ):
            pass

        assert expected in caplog.text

    def test_access_log_line(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="gsuite_api.access"):
            client.get("/health")

        record = next(r for r in caplog.records if r.name == "gsuite_api.access")
        assert record.getMessage() == "GET /health 200"
        assert record.status == 200
