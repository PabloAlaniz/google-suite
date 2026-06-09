"""Tests aislados de ``DataframeService`` (puerto falso) y ``PandasDataFrameAdapter``."""

from unittest.mock import Mock

import pandas as pd
import pytest
from gspreadmanager.application.dataframe_service import DataframeService
from gspreadmanager.infrastructure.pandas_adapter import PandasDataFrameAdapter


class TestDataframeService:
    def test_from_rows_delegates_to_port(self):
        frames = Mock()
        service = DataframeService(frames)
        result = service.from_rows(["a", "b"], [["1", "2"]])
        frames.from_rows.assert_called_once_with(["a", "b"], [["1", "2"]], index_col=None)
        assert result is frames.from_rows.return_value

    def test_from_rows_prunes_empty_before_building(self):
        frames = Mock()
        service = DataframeService(frames)
        service.from_rows(
            ["a", "b"], [["1", ""], ["", ""]], drop_empty_rows=True, drop_empty_cols=True
        )
        frames.from_rows.assert_called_once_with(["a"], [["1"]], index_col=None)

    def test_from_rows_passes_index_col(self):
        frames = Mock()
        DataframeService(frames).from_rows(["id", "v"], [["1", "x"]], index_col="id")
        frames.from_rows.assert_called_once_with(["id", "v"], [["1", "x"]], index_col="id")

    def test_write_clears_and_updates(self):
        frames = Mock()
        frames.to_rows.return_value = [["a"], ["1"]]
        ws = Mock()
        service = DataframeService(frames)

        service.write(ws, df="DF", include_header=True, clear=True, value_input_option="RAW")

        frames.to_rows.assert_called_once_with("DF", True, include_index=False)
        ws.clear.assert_called_once_with()
        ws.update.assert_called_once_with([["a"], ["1"]], "RAW", range_name=None)

    def test_write_with_anchor_and_index(self):
        frames = Mock()
        frames.to_rows.return_value = [["a"], ["1"]]
        ws = Mock()
        DataframeService(frames).write(
            ws, "DF", True, False, "RAW", include_index=True, start_cell="B2"
        )
        frames.to_rows.assert_called_once_with("DF", True, include_index=True)
        ws.clear.assert_not_called()
        ws.update.assert_called_once_with([["a"], ["1"]], "RAW", range_name="B2")

    def test_write_without_clear(self):
        frames = Mock()
        frames.to_rows.return_value = [["x"]]
        ws = Mock()
        DataframeService(frames).write(ws, "DF", False, False, "USER_ENTERED")
        ws.clear.assert_not_called()
        ws.update.assert_called_once()


class TestPandasDataFrameAdapter:
    @pytest.fixture
    def adapter(self):
        return PandasDataFrameAdapter()

    def test_from_rows_builds_dataframe(self, adapter):
        df = adapter.from_rows(["name", "age"], [["Ana", "3"], ["Bob", "4"]])
        assert list(df.columns) == ["name", "age"]
        assert df.values.tolist() == [["Ana", "3"], ["Bob", "4"]]

    def test_to_rows_with_header(self, adapter):
        df = pd.DataFrame([["Ana", "3"]], columns=["name", "age"])
        assert adapter.to_rows(df, include_header=True) == [["name", "age"], ["Ana", "3"]]

    def test_to_rows_without_header(self, adapter):
        df = pd.DataFrame([["Ana", "3"]], columns=["name", "age"])
        assert adapter.to_rows(df, include_header=False) == [["Ana", "3"]]

    def test_from_rows_with_index_col(self, adapter):
        df = adapter.from_rows(["id", "name"], [["1", "Ana"], ["2", "Bob"]], index_col="id")
        assert df.index.name == "id"
        assert list(df.columns) == ["name"]

    def test_to_rows_with_index(self, adapter):
        df = pd.DataFrame([["Ana"]], columns=["name"], index=pd.Index(["1"], name="id"))
        assert adapter.to_rows(df, include_header=True, include_index=True) == [
            ["id", "name"],
            ["1", "Ana"],
        ]
