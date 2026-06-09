"""Tests del backend de DataFrame pluggable: factory, adaptador polars y limpieza pura."""

import pytest
from gspreadmanager.domain.dataframe import prune_empty
from gspreadmanager.domain.errors import GSpreadManagerError
from gspreadmanager.infrastructure.dataframe_backend import build_dataframe_adapter
from gspreadmanager.infrastructure.pandas_adapter import PandasDataFrameAdapter
from gspreadmanager.infrastructure.polars_adapter import PolarsDataFrameAdapter

polars = pytest.importorskip("polars")


class TestPruneEmpty:
    def test_no_op_by_default(self):
        header, rows = prune_empty(["a", "b"], [["1", ""], ["", ""]])
        assert header == ["a", "b"]
        assert rows == [["1", ""], ["", ""]]

    def test_drop_empty_rows(self):
        _, rows = prune_empty(["a", "b"], [["1", ""], ["", ""], ["2", "3"]], drop_empty_rows=True)
        assert rows == [["1", ""], ["2", "3"]]

    def test_drop_empty_cols_also_trims_header(self):
        header, rows = prune_empty(["a", "b", "c"], [["1", "", "x"]], drop_empty_cols=True)
        assert header == ["a", "c"]
        assert rows == [["1", "x"]]

    def test_drop_both(self):
        header, rows = prune_empty(
            ["a", "b"], [["1", ""], ["", ""]], drop_empty_rows=True, drop_empty_cols=True
        )
        assert header == ["a"]
        assert rows == [["1"]]

    def test_ragged_rows_treated_as_empty_cells(self):
        header, rows = prune_empty(["a", "b"], [["1"]], drop_empty_cols=True)
        assert header == ["a"]
        assert rows == [["1"]]


class TestBackendFactory:
    def test_pandas(self):
        assert isinstance(build_dataframe_adapter("pandas"), PandasDataFrameAdapter)

    def test_polars(self):
        assert isinstance(build_dataframe_adapter("polars"), PolarsDataFrameAdapter)

    def test_case_insensitive(self):
        assert isinstance(build_dataframe_adapter("Polars"), PolarsDataFrameAdapter)

    def test_unknown_raises(self):
        with pytest.raises(GSpreadManagerError, match="desconocido"):
            build_dataframe_adapter("dask")


class TestPolarsAdapter:
    @pytest.fixture
    def adapter(self):
        return PolarsDataFrameAdapter()

    def test_from_rows_builds_dataframe(self, adapter):
        df = adapter.from_rows(["name", "age"], [["Ana", "3"], ["Bob", "4"]])
        assert df.columns == ["name", "age"]
        assert df.rows() == [("Ana", "3"), ("Bob", "4")]

    def test_from_rows_empty(self, adapter):
        df = adapter.from_rows(["a", "b"], [])
        assert df.columns == ["a", "b"]
        assert df.height == 0

    def test_from_rows_no_header(self, adapter):
        df = adapter.from_rows([], [])
        assert df.width == 0

    def test_index_col_ignored(self, adapter):
        df = adapter.from_rows(["id", "name"], [["1", "Ana"]], index_col="id")
        assert df.columns == ["id", "name"]

    def test_to_rows_with_and_without_header(self, adapter):
        df = polars.DataFrame({"name": ["Ana"], "age": ["3"]})
        assert adapter.to_rows(df, include_header=True) == [["name", "age"], ["Ana", "3"]]
        assert adapter.to_rows(df, include_header=False) == [["Ana", "3"]]

    def test_include_index_ignored(self, adapter):
        df = polars.DataFrame({"name": ["Ana"]})
        assert adapter.to_rows(df, include_header=False, include_index=True) == [["Ana"]]
