from __future__ import annotations

import warnings
from typing import Any

import gspread
from gspread.utils import ValueInputOption

from .application.data_service import DataService
from .application.dataframe_service import DataframeService
from .application.document_service import DocumentService
from .application.formatting_service import FormattingService
from .application.sharing_service import SharingService
from .application.validation_service import ValidationService
from .application.worksheet_service import WorksheetService
from .config import DEFAULT_VALUE_INPUT_OPTION
from .domain.values import CellFormat, Color
from .infrastructure.auth import build_auth_strategy
from .infrastructure.gspread_client import GspreadClientAdapter
from .infrastructure.pandas_adapter import PandasDataFrameAdapter
from .infrastructure.request_builders import grid_range
from .retry import retry_on_rate_limit

_SHEET_DEPRECATION_MSG = (
    "El parámetro 'sheet' está obsoleto y se eliminará en una versión futura. "
    "Se usa la hoja activa del conector (self.sheet) por defecto."
)


class GoogleSheetConector:
    """
    Clase para conectar y manipular hojas de cálculo de Google Sheets.

    Esta clase proporciona una interfaz para interactuar con un documento específico de Google Sheets, permitiendo leer y escribir datos en él.

    Atributos:
        sheet_title (str): Nombre del documento de Google Sheets.
        json_google_file (str): Ruta al archivo JSON con las credenciales de Google.
        tab_name (str, opcional): Nombre de la hoja específica en el documento. Por defecto es None.
        sheet: Objeto que representa la hoja de cálculo conectada.
        options (dict): Opciones para la entrada de valores en la hoja de cálculo.

    Métodos:
        connect_to_sheet: Establece una conexión con una hoja de cálculo de Google Sheets.

    Ejemplo:
        conector = GoogleSheetConector("MiDocumento", "credenciales.json", "Hoja1")
        # Aquí se pueden realizar operaciones con el conector, como leer o escribir datos.
    """

    def __init__(
        self,
        doc_name: str,
        json_google_file: str | None = None,
        sheet_name: str | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        *,
        credentials: Any = None,
        client: Any = None,
        service_account_info: dict[str, Any] | None = None,
        use_adc: bool = False,
    ) -> None:
        """
        Inicializa un nuevo objeto GoogleSheetConector.

        Acepta múltiples métodos de autenticación (se usa el primero que se proporcione, en
        este orden): `client` ya autorizado, `credentials` de google-auth,
        `service_account_info` (dict), `json_google_file` (ruta a un service account) o
        `use_adc=True` (Application Default Credentials).

        El cliente y el documento se cachean: cambiar de pestaña ya no re-autentica ni
        reabre el documento.

        Parámetros:
            doc_name (str): Nombre del documento de Google Sheets a conectar.
            json_google_file (str, opcional): Ruta al archivo JSON de un service account.
            sheet_name (str, opcional): Nombre de la hoja específica. Por defecto la primera.
            max_retries (int, opcional): Reintentos ante errores transitorios (429/500/503). Por defecto 3.
            retry_backoff (float, opcional): Backoff exponencial base en segundos. Por defecto 1.0.
            credentials (opcional): Objeto de credenciales de google-auth ya construido.
            client (opcional): Cliente de gspread ya autorizado.
            service_account_info (dict, opcional): Credenciales de service account como diccionario.
            use_adc (bool, opcional): Si es True, usa Application Default Credentials.
        """
        warnings.warn(
            "GoogleSheetConector está obsoleto y se eliminará en la 3.0. Usá SheetManager: "
            "mgr = SheetManager(doc); ws = mgr.worksheet('Hoja1'); ws.append(...). "
            "SheetManager no tiene 'hoja activa' mutable ni el parámetro 'sheet'.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.max_retries: int = max_retries
        self.retry_backoff: float = retry_backoff
        self.sheet_title: str = doc_name
        self.json_google_file: str | None = json_google_file
        self.tab_name: str | None = sheet_name
        auth = build_auth_strategy(
            credentials=credentials,
            service_account_info=service_account_info,
            json_google_file=json_google_file,
            client=client,
            use_adc=use_adc,
        )
        self._gspread_client = GspreadClientAdapter(auth)
        self._data_service = DataService()
        self._formatting_service = FormattingService()
        self._validation_service = ValidationService()
        self._worksheet_service = WorksheetService()
        self._document_service = DocumentService()
        self._sharing_service = SharingService()
        self._dataframe_service = DataframeService(PandasDataFrameAdapter())
        self.sheet: gspread.Worksheet = self.connect_to_sheet(self.sheet_title, self.tab_name)
        self.options: dict[str, Any] = {"valueInputOption": "USER_ENTERED"}

    def _get_client(self) -> Any:
        """Devuelve el cliente de gspread (autorizado y cacheado por el adaptador)."""
        return self._gspread_client.client()

    def _get_spreadsheet(self, doc_name: str) -> gspread.Spreadsheet:
        """Devuelve el documento abierto, cacheado por nombre por el adaptador."""
        return self._gspread_client.open(doc_name)

    def _resolve_spreadsheet(self, doc_name: str | None) -> gspread.Spreadsheet:
        """Devuelve el documento indicado por nombre, o el documento activo si es None."""
        if doc_name is not None:
            return self._get_spreadsheet(doc_name)
        return self.sheet.spreadsheet

    def _resolve_sheet(self, sheet: gspread.Worksheet | None) -> gspread.Worksheet:
        """Devuelve la hoja a usar, advirtiendo si se pasó el parámetro 'sheet' obsoleto."""
        if sheet is not None:
            warnings.warn(_SHEET_DEPRECATION_MSG, DeprecationWarning, stacklevel=3)
            return sheet
        return self.sheet

    def __enter__(self) -> GoogleSheetConector:
        """Permite usar el conector como context manager (``with ... as conn:``)."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Sale del context manager sin suprimir excepciones.

        Las operaciones se aplican de inmediato, por lo que no hay cambios pendientes
        que descartar.
        """
        return

    @retry_on_rate_limit
    def connect_to_sheet(self, doc_name: str, sheet_name: str | None = None) -> gspread.Worksheet:
        """
        Establece una conexión con una hoja específica en un documento de Google Sheets.

        Esta función utiliza las credenciales de la cuenta de servicio de Google para autenticarse y obtener acceso al documento de Google Sheets especificado. Luego, según se especifique, conecta a la primera hoja del documento o a una hoja específica por su nombre.

        Parámetros:
            doc_name (str): Nombre del documento de Google Sheets a conectar.
            sheet_name (str, opcional): Nombre de la hoja específica dentro del documento. Si no se proporciona, se conecta a la primera hoja del documento. Por defecto es None.

        Devuelve:
            Un objeto que representa la hoja de cálculo conectada. Este objeto permite realizar operaciones como leer y escribir datos en la hoja de cálculo.

        Ejemplo:
            # Conexión a la primera hoja del documento "MiDocumento".
            primera_hoja = conector.connect_to_sheet("MiDocumento")

            # Conexión a la hoja llamada "HojaEspecifica" del documento "MiDocumento".
            hoja_especifica = conector.connect_to_sheet("MiDocumento", "HojaEspecifica")

        Nota:
            El cliente y el documento se reutilizan entre llamadas (caché), por lo que
            cambiar de pestaña no vuelve a autenticar ni a reabrir el documento.
        """
        spreadsheet = self._get_spreadsheet(doc_name)
        if sheet_name:
            return spreadsheet.worksheet(sheet_name)
        return spreadsheet.sheet1

    @retry_on_rate_limit
    def update_cell(
        self,
        row_index: int,
        col_index: int,
        value: Any,
        sheet: gspread.Worksheet | None = None,
    ) -> None:
        """
        Actualiza el valor de una celda específica en la hoja de cálculo dada.

        Esta función modifica el contenido de una celda identificada por su índice de fila y columna en la hoja de cálculo proporcionada. El nuevo valor de la celda se especifica en el parámetro 'value'.

        Parámetros:
            sheet: Objeto de hoja de cálculo en el que se realizará la actualización. Este objeto debe ser obtenido a través de la función 'connect_to_sheet'.
            row_index (int): Índice de la fila de la celda a actualizar. El índice comienza en 1 (no en 0).
            col_index (int): Índice de la columna de la celda a actualizar. Al igual que el índice de fila, comienza en 1.
            value: Valor nuevo para la celda especificada. Puede ser de tipo string, número, o cualquier otro valor soportado por Google Sheets.
            sheet (opcional): OBSOLETO. Se mantiene por compatibilidad; se usa la hoja activa del conector por defecto.

        Ejemplo:
            # Actualizar la celda en la fila 2, columna 3 con el valor "Hola Mundo"
            conector.update_cell(2, 3, "Hola Mundo")
        """
        target = self._resolve_sheet(sheet)
        self._data_service.update_cell(target, row_index, col_index, value)

    @retry_on_rate_limit
    def update_row(
        self,
        row_index: int,
        data: list[Any],
        start_column: int | None = None,
        sheet: gspread.Worksheet | None = None,
    ) -> None:
        """
        Actualiza una fila completa o una parte de ella en la hoja de cálculo especificada.

        Esta función recorre una lista de valores (data) y actualiza las celdas correspondientes en la fila especificada de la hoja de cálculo. La actualización comienza desde la columna indicada por 'start_column' o desde la primera columna si 'start_column' no se especifica.

        Parámetros:
            sheet: Objeto de hoja de cálculo en el que se realizará la actualización. Este objeto debe ser obtenido a través de la función 'connect_to_sheet'.
            contact_row (int): Índice de la fila en la que se realizarán las actualizaciones. El índice comienza en 1.
            data (list): Lista de valores que se utilizarán para actualizar la fila. Cada elemento de la lista corresponde a una celda en la fila.
            start_column (int, opcional): Índice de la columna desde la cual comenzará la actualización. Si no se proporciona, se asume que la actualización comienza desde la primera columna. El índice comienza en 1.
            sheet (opcional): OBSOLETO. Se mantiene por compatibilidad; se usa la hoja activa del conector por defecto.

        Ejemplo:
            # Actualizar la fila 5 con los valores ["Nombre", "Correo", "Teléfono"], comenzando desde la columna 2
            conector.update_row(5, ["Nombre", "Correo", "Teléfono"], start_column=2)

        Nota:
            Ten en cuenta que esta función actualizará cada celda en la fila de forma individual, lo que puede resultar en múltiples llamadas a la API de Google Sheets.
        """
        target = self._resolve_sheet(sheet)
        self._data_service.update_row(target, row_index, data, start_column)

    @retry_on_rate_limit
    def spreadsheet_read_range(
        self,
        tab_name: str,
        fila_start: int,
        fila_end: int,
        column_start: str,
        column_end: str,
        sheet: gspread.Worksheet | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lee un rango específico de celdas desde una hoja de cálculo de Google Sheets.

        Esta función recupera los datos de un rango definido por los índices de fila y columna de inicio y fin. El rango es especificado en una hoja y pestaña determinadas. Devuelve una lista de diccionarios, cada uno representando una fila con su índice y los valores contenidos.

        Parámetros:
            sheet: Objeto de hoja de cálculo conectado a través de la función 'connect_to_sheet'.
            tab_name (str): Nombre de la pestaña dentro de la hoja de cálculo de donde se leerán los datos.
            fila_start (int): Índice de la fila inicial del rango a leer.
            fila_end (int): Índice de la fila final del rango a leer.
            column_start (str): Letra o identificador de la columna inicial (ej. 'A').
            column_end (str): Letra o identificador de la columna final (ej. 'D').
            sheet (opcional): OBSOLETO. Se mantiene por compatibilidad; se usa la hoja activa del conector por defecto.

        Devuelve:
            Una lista de diccionarios, donde cada diccionario contiene el número de fila ('fila') y una lista de valores ('values') para esa fila.

        Ejemplo:
            # Leer datos desde la fila 1 a la 5, de la columna A a la D, en la pestaña 'Hoja1'
            datos = conector.spreadsheet_read_range('Hoja1', 1, 5, 'A', 'D')

        Nota:
            Asegúrate de que las letras de columna y los índices de fila proporcionados correspondan a un rango válido en la hoja de cálculo.
        """
        target = self._resolve_sheet(sheet)
        # Construir el rango en notación A1 (ej. 'Hoja1!A1:D5')
        data_range = f"{tab_name}!{column_start}{fila_start}:{column_end}{fila_end}"
        return self._data_service.read_range(target.spreadsheet, data_range, fila_start)

    @retry_on_rate_limit
    def read_sheet_data(
        self, tab_name: str | None = None, skiprows: int = 0, output_format: str = "list"
    ) -> Any:
        """
        Lee datos de una pestaña específica de una hoja de cálculo de Google Sheets y los devuelve en varios formatos.

        Parámetros:
            tab_name (str, opcional): Nombre de la pestaña de donde se leerán los datos. Si no se proporciona, se utiliza la pestaña actualmente conectada.
            skiprows (int, opcional): Número de filas iniciales a omitir. Por defecto es 0.
            output_format (str, opcional): Formato de salida de los datos. Puede ser 'list', 'dict' o 'pandas'. Por defecto es 'list'.

        Devuelve:
            Los datos de la hoja de cálculo en el formato especificado: lista de listas, lista de diccionarios, o DataFrame de pandas.

        Ejemplo:
            # Leer datos en formato de lista
            datos_lista = conector.read_sheet_data('Hoja1', output_format='list')

            # Leer datos en formato de diccionario
            datos_dict = conector.read_sheet_data('Hoja1', output_format='dict')

            # Leer datos en formato DataFrame de pandas
            datos_df = conector.read_sheet_data('Hoja1', output_format='pandas')
        """
        # Conectar a la pestaña especificada
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        all_values = self._data_service.read_values(self.sheet, skiprows)

        # Devolver los datos en el formato especificado
        if output_format == "dict":
            return self._data_service.as_dicts(all_values)

        if output_format == "pandas":
            return self._dataframe_service.from_rows(all_values[0], all_values[1:])

        # output_format == 'list'
        return all_values

    @retry_on_rate_limit
    def spreadsheet_append(self, data: list[list[Any]], tab_name: str | None = None) -> Any:
        """
        Agrega una o más filas de datos al final de la hoja de cálculo especificada.

        Esta función añade nuevos datos al final de una pestaña dada en la hoja de cálculo de Google Sheets. Si se proporciona un nombre de pestaña, la función se conecta primero a esa pestaña. Los datos se añaden manteniendo el formato del usuario ('USER_ENTERED').

        Parámetros:
            data (list): Una lista de listas, donde cada lista interna representa una fila de datos a agregar.
            tab_name (str, opcional): Nombre de la pestaña dentro de la hoja de cálculo donde se agregarán los datos. Si no se proporciona, se utiliza la pestaña actualmente conectada.

        Devuelve:
            El resultado de la operación de añadir filas, que incluye detalles sobre las filas afectadas.

        Ejemplo:
            # Agregar filas de datos a la pestaña 'Hoja1'
            datos = [["Nombre", "Correo"], ["Ana", "ana@example.com"]]
            resultado = conector.spreadsheet_append(datos, 'Hoja1')

        Nota:
            Si se cambia la pestaña con 'tab_name', la nueva pestaña se convierte en la pestaña activa para operaciones futuras en esta instancia de la clase.
        """
        # Conectar a la pestaña especificada, si se proporciona una
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        return self._data_service.append(
            self.sheet, data, ValueInputOption(DEFAULT_VALUE_INPUT_OPTION)
        )

    @retry_on_rate_limit
    def get_rows_where_column_equals(self, column: int, value: Any) -> list[tuple[int, list[Any]]]:
        """
        Obtiene las filas donde una columna específica tiene un valor dado.

        Además, incluye el número de fila en la hoja de cálculo.

        Parámetros:
            column (int): Índice de la columna a verificar. El índice comienza en 0 (0 para la primera columna).
            value: Valor a buscar en la columna especificada.

        Devuelve:
            Una lista de tuplas, donde cada tupla contiene el número de fila (comenzando en 1) y la fila (lista de celdas).

        Ejemplo:
            # Obtener todas las filas donde la primera columna (índice 0) tiene el valor "Ejemplo"
            filas = conector.get_column_with_value(0, "Ejemplo")
        """
        return self._data_service.rows_where_column_equals(self.sheet, column, value)

    @retry_on_rate_limit
    def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str = DEFAULT_VALUE_INPUT_OPTION
    ) -> None:
        """
        Realiza actualizaciones en lote en la hoja de cálculo de Google Sheets.

        Esta función permite actualizar varios rangos de celdas simultáneamente. Es útil para optimizar el rendimiento cuando se necesitan realizar múltiples actualizaciones en una hoja de cálculo. Cada actualización en el lote puede especificar un rango de celdas y los valores a aplicar.

        Parámetros:
            range_data (list): Una lista de diccionarios, donde cada diccionario representa una actualización y debe contener las claves 'range' y 'values'. 'range' especifica el rango de celdas a actualizar y 'values' es una lista de listas con los datos a insertar.
            value_input_option (str, opcional): Determina cómo se interpretan los datos de entrada (p. ej., 'USER_ENTERED' o 'RAW'). Por defecto es 'USER_ENTERED'.

        Ejemplo:
            # Actualizar dos rangos diferentes en una hoja de cálculo
            updates = [
                {"range": "Hoja1!A1:C2", "values": [["Valor1", "Valor2", "Valor3"], ["Valor4", "Valor5", "Valor6"]]},
                {"range": "Hoja1!D1:F2", "values": [["Valor7", "Valor8", "Valor9"], ["Valor10", "Valor11", "Valor12"]]}
            ]
            conector.batch_update(updates)

        Nota:
            La clave 'range' en cada diccionario debe seguir el formato de notación A1 de Google Sheets.
        """
        self._data_service.batch_update(
            self.sheet, range_data, ValueInputOption(value_input_option)
        )

    @retry_on_rate_limit
    def get_last_row(self, tab_name: str | None = None) -> int:
        """
        Obtiene el índice de la última fila con datos en una pestaña específica de una hoja de cálculo de Google Sheets.

        Si se especifica un nombre de pestaña, la función primero cambia a esa pestaña. Luego, cuenta el número de filas que contienen datos. Si la hoja está vacía, devuelve 0.

        Parámetros:
            tab_name (str, opcional): Nombre de la pestaña dentro de la hoja de cálculo a consultar. Si no se proporciona, se utiliza la pestaña actualmente conectada.

        Devuelve:
            Un entero que representa el índice de la última fila con datos en la pestaña especificada. El índice comienza en 1. Si la hoja está vacía, devuelve 0.

        Ejemplo:
            # Obtener el índice de la última fila con datos en la pestaña 'Hoja1'
            ultima_fila = conector.get_last_row('Hoja1')

        Nota:
            Si se cambia la pestaña con 'tab_name', la nueva pestaña se convierte en la pestaña activa para operaciones futuras en esta instancia de la clase.
        """
        # Cambiar a la pestaña especificada, si se proporciona
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        return self._data_service.last_row(self.sheet)

    @retry_on_rate_limit
    def get_row_with_empty_in_column(
        self, column_letter: str, sheet: gspread.Worksheet | None = None
    ) -> tuple[list[Any] | None, int | None]:
        """
        Encuentra la primera fila con una celda vacía en una columna específica.

        Parámetros:
            column_letter (str): Letra de la columna en la que buscar la celda vacía.
            sheet (opcional): OBSOLETO. Se mantiene por compatibilidad; se usa la hoja activa del conector por defecto.

        Devuelve:
            Una tupla que contiene la fila completa donde se encontró la primera celda vacía y el índice de esa fila, o (None, None) si no se encuentra una celda vacía.

        Ejemplo:
            fila, indice = conector.get_row_with_empty_in_column('B')

        Nota:
            Si no se encuentra una celda vacía en la columna especificada, se devuelve (None, None).
        """
        target = self._resolve_sheet(sheet)
        return self._data_service.row_with_empty_in_column(target, column_letter)

    @retry_on_rate_limit
    def spreadsheet_insert(
        self,
        sheet_name: str,
        worksheet_name: str,
        data: list[list[Any]],
        fila: int | None = None,
    ) -> Any:
        """
        Inserta un conjunto de datos en una hoja de cálculo de Google Sheets, en la fila especificada o al final.

        Parámetros:
            sheet_name (str): Nombre del documento de Google Sheets.
            worksheet_name (str): Nombre de la hoja específica.
            data (list of list): Datos a insertar, donde cada sublista representa una fila.
            fila (int, opcional): Índice de la fila donde comenzar la inserción. Si es None, los datos se insertarán al final.

        Devuelve:
            El resultado de la operación de inserción de datos.

        Ejemplo:
            datos = [["Nombre", "Correo"], ["Ana", "ana@example.com"]]
            conector.spreadsheet_insert("MiDocumento", "Hoja1", datos, fila=5)
        """
        sheet = self.connect_to_sheet(sheet_name, worksheet_name)
        return self._data_service.insert(sheet, worksheet_name, data, fila)

    # ------------------------------------------------------------------
    # Gestión de hojas (worksheets)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def create_sheet(
        self,
        title: str,
        rows: int = 100,
        cols: int = 26,
        index: int | None = None,
        activate: bool = False,
    ) -> gspread.Worksheet:
        """
        Crea una nueva hoja (pestaña) dentro del documento actual.

        Parámetros:
            title (str): Nombre de la nueva hoja.
            rows (int, opcional): Cantidad de filas iniciales. Por defecto 100.
            cols (int, opcional): Cantidad de columnas iniciales. Por defecto 26.
            index (int, opcional): Posición de la pestaña. Si es None, se agrega al final.
            activate (bool, opcional): Si es True, la nueva hoja pasa a ser la hoja activa del conector.

        Devuelve:
            El objeto worksheet recién creado.

        Ejemplo:
            nueva = conector.create_sheet("Reporte 2026", rows=500, cols=10)
        """
        worksheet = self._worksheet_service.create(self.sheet.spreadsheet, title, rows, cols, index)
        if activate:
            self.sheet = worksheet
            self.tab_name = title
        return worksheet

    @retry_on_rate_limit
    def delete_sheet(self, title: str) -> None:
        """
        Elimina una hoja (pestaña) del documento actual por su nombre.

        Parámetros:
            title (str): Nombre de la hoja a eliminar.

        Ejemplo:
            conector.delete_sheet("Hoja temporal")
        """
        self._worksheet_service.delete(self.sheet.spreadsheet, title)

    # ------------------------------------------------------------------
    # Limpieza y búsqueda
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def clear_range(
        self, ranges: str | list[str] | None = None, tab_name: str | None = None
    ) -> None:
        """
        Limpia el contenido de uno o más rangos, o de toda la hoja.

        Parámetros:
            ranges (str | list[str], opcional): Rango en notación A1 (ej. 'A1:C10') o lista de
                rangos. Si es None, se limpia toda la hoja activa.
            tab_name (str, opcional): Pestaña sobre la que operar. Si se indica, pasa a ser la
                hoja activa del conector.

        Ejemplo:
            conector.clear_range('A1:C10')
            conector.clear_range(['A1:A5', 'C1:C5'])
            conector.clear_range()  # limpia toda la hoja
        """
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)
        self._worksheet_service.clear(self.sheet, ranges)

    @retry_on_rate_limit
    def find_cell(self, query: str, case_sensitive: bool = True) -> gspread.Cell | None:
        """
        Busca la primera celda cuyo valor coincide con el texto dado.

        Parámetros:
            query (str): Texto a buscar.
            case_sensitive (bool, opcional): Si la búsqueda distingue mayúsculas/minúsculas. Por defecto True.

        Devuelve:
            El objeto Cell encontrado (con atributos `row`, `col` y `value`), o None si no hay coincidencias.

        Ejemplo:
            celda = conector.find_cell("Total")
            if celda:
                print(celda.row, celda.col, celda.value)
        """
        return self._worksheet_service.find(self.sheet, query, case_sensitive)

    # ------------------------------------------------------------------
    # Integración con pandas
    # ------------------------------------------------------------------

    def from_gsheet(self, tab_name: str | None = None, skiprows: int = 0) -> Any:
        """
        Lee la hoja como un DataFrame de pandas (atajo de read_sheet_data).

        Requiere la dependencia opcional pandas (`pip install GSpreadManager[pandas]`).

        Parámetros:
            tab_name (str, opcional): Pestaña a leer. Si no se indica, usa la hoja activa.
            skiprows (int, opcional): Número de filas iniciales a omitir. Por defecto 0.

        Devuelve:
            Un DataFrame de pandas con la primera fila como encabezados.
        """
        return self.read_sheet_data(tab_name=tab_name, skiprows=skiprows, output_format="pandas")

    @retry_on_rate_limit
    def to_gsheet(
        self,
        df: Any,
        tab_name: str | None = None,
        include_header: bool = True,
        clear: bool = True,
    ) -> Any:
        """
        Escribe un DataFrame de pandas en la hoja, empezando en A1.

        Requiere la dependencia opcional pandas (`pip install GSpreadManager[pandas]`).

        Parámetros:
            df: DataFrame de pandas a volcar.
            tab_name (str, opcional): Pestaña destino. Si se indica, pasa a ser la hoja activa.
            include_header (bool, opcional): Si se escriben los nombres de columna como primera fila. Por defecto True.
            clear (bool, opcional): Si se limpia la hoja antes de escribir. Por defecto True.

        Devuelve:
            El resultado de la operación de actualización de gspread.

        Ejemplo:
            conector.to_gsheet(df, tab_name='Resultados')
        """
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        return self._dataframe_service.write(
            self.sheet,
            df,
            include_header,
            clear,
            ValueInputOption(DEFAULT_VALUE_INPUT_OPTION),
        )

    # ------------------------------------------------------------------
    # Formato de celdas (implementación propia sobre el transporte de gspread)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def format_range(
        self,
        ranges: str | list[str],
        cell_format: CellFormat,
        tab_name: str | None = None,
    ) -> Any:
        """
        Aplica un formato a uno o más rangos.

        Parámetros:
            ranges (str | list[str]): Rango(s) en notación A1 (ej. 'A1:C1').
            cell_format (CellFormat): Formato a aplicar.
            tab_name (str, opcional): Pestaña destino; si se indica, pasa a ser la hoja activa.

        Ejemplo:
            from gspreadmanager import CellFormat, TextFormat, Color
            fmt = CellFormat(text_format=TextFormat(bold=True),
                             background_color=Color.from_hex("#D9EAD3"))
            conector.format_range("A1:C1", fmt)
        """
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)
        return self._formatting_service.apply(self.sheet, ranges, cell_format)

    def format_header(
        self,
        range_name: str = "1:1",
        background_hex: str | None = "#D9EAD3",
        tab_name: str | None = None,
    ) -> Any:
        """
        Atajo para dar formato de encabezado (negrita + color de fondo) a una fila/rango.

        Parámetros:
            range_name (str): Rango del encabezado. Por defecto la primera fila ('1:1').
            background_hex (str, opcional): Color de fondo en hex. None para no aplicar fondo.
            tab_name (str, opcional): Pestaña destino.
        """
        fmt = self._formatting_service.header_format(background_hex)
        return self.format_range(range_name, fmt, tab_name=tab_name)

    def set_background(
        self, ranges: str | list[str], color: Color, tab_name: str | None = None
    ) -> Any:
        """Aplica un color de fondo a uno o más rangos."""
        return self.format_range(ranges, CellFormat(background_color=color), tab_name=tab_name)

    def set_text_format(
        self,
        ranges: str | list[str],
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        font_size: int | None = None,
        color: Color | None = None,
        tab_name: str | None = None,
    ) -> Any:
        """Aplica formato de texto (negrita, itálica, tamaño, color) a uno o más rangos."""
        fmt = self._formatting_service.text_format(
            bold=bold, italic=italic, font_size=font_size, color=color
        )
        return self.format_range(ranges, fmt, tab_name=tab_name)

    def set_number_format(
        self,
        ranges: str | list[str],
        pattern: str,
        number_type: str = "NUMBER",
        tab_name: str | None = None,
    ) -> Any:
        """
        Aplica un formato numérico a uno o más rangos.

        Parámetros:
            pattern (str): Patrón (ej. '#,##0.00', '0.00%', 'dd/mm/yyyy').
            number_type (str): Tipo: NUMBER, CURRENCY, PERCENT, DATE, TIME, DATE_TIME, SCIENTIFIC.
        """
        fmt = self._formatting_service.number_format(pattern, number_type)
        return self.format_range(ranges, fmt, tab_name=tab_name)

    @retry_on_rate_limit
    def freeze(
        self, rows: int | None = None, cols: int | None = None, tab_name: str | None = None
    ) -> Any:
        """Congela ``rows`` filas y/o ``cols`` columnas en la hoja."""
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)
        return self._formatting_service.freeze(self.sheet, rows, cols)

    @retry_on_rate_limit
    def merge(
        self, range_name: str, merge_type: str = "MERGE_ALL", tab_name: str | None = None
    ) -> Any:
        """Combina las celdas de un rango. ``merge_type``: MERGE_ALL, MERGE_COLUMNS, MERGE_ROWS."""
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)
        return self._formatting_service.merge(self.sheet, range_name, merge_type)

    # ------------------------------------------------------------------
    # Validación de datos
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def set_data_validation(
        self,
        range_name: str,
        condition_type: str,
        values: list[Any] | None = None,
        strict: bool = True,
        show_custom_ui: bool = True,
        tab_name: str | None = None,
    ) -> Any:
        """
        Aplica una regla de validación de datos a un rango.

        Parámetros:
            condition_type (str): Tipo de condición de la Sheets API (ej. ONE_OF_LIST, BOOLEAN,
                NUMBER_BETWEEN, TEXT_CONTAINS, …).
            values (list, opcional): Valores de la condición.
            strict (bool): Si rechaza entradas inválidas. Por defecto True.
            show_custom_ui (bool): Si muestra el control (dropdown/checkbox). Por defecto True.
            tab_name (str, opcional): Pestaña destino.
        """
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        grid = grid_range(range_name, self.sheet.id)
        return self._validation_service.set_data_validation(
            self.sheet, grid, condition_type, values, strict, show_custom_ui
        )

    def add_dropdown(
        self,
        range_name: str,
        values: list[Any],
        strict: bool = True,
        tab_name: str | None = None,
    ) -> Any:
        """Agrega un desplegable (lista de opciones) a un rango."""
        return self.set_data_validation(
            range_name, "ONE_OF_LIST", values=values, strict=strict, tab_name=tab_name
        )

    def add_checkbox(self, range_name: str, tab_name: str | None = None) -> Any:
        """Agrega casillas de verificación (checkbox) a un rango."""
        return self.set_data_validation(range_name, "BOOLEAN", tab_name=tab_name)

    # ------------------------------------------------------------------
    # Formato condicional
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def add_conditional_format(
        self,
        range_name: str,
        condition_type: str,
        values: list[Any],
        cell_format: CellFormat,
        index: int = 0,
        tab_name: str | None = None,
    ) -> Any:
        """
        Agrega una regla de formato condicional (booleana) a un rango.

        Parámetros:
            condition_type (str): Tipo (ej. NUMBER_GREATER, TEXT_CONTAINS, CUSTOM_FORMULA, …).
            values (list): Valores de la condición.
            cell_format (CellFormat): Formato a aplicar cuando se cumple la condición.
            index (int): Prioridad de la regla. Por defecto 0 (mayor prioridad).
            tab_name (str, opcional): Pestaña destino.

        Ejemplo:
            fmt = CellFormat(background_color=Color.from_hex("#F4CCCC"))
            conector.add_conditional_format("B2:B100", "NUMBER_LESS", [0], fmt)
        """
        if tab_name:
            self.sheet = self.connect_to_sheet(self.sheet_title, tab_name)

        grid = grid_range(range_name, self.sheet.id)
        return self._validation_service.add_conditional_format(
            self.sheet, grid, condition_type, values, cell_format, index
        )

    # ------------------------------------------------------------------
    # Operaciones a nivel documento (Drive)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def create_spreadsheet(self, title: str, folder_id: str | None = None) -> gspread.Spreadsheet:
        """
        Crea un nuevo documento de Google Sheets.

        Parámetros:
            title (str): Título del nuevo documento.
            folder_id (str, opcional): ID de la carpeta de Drive donde crearlo.

        Devuelve:
            El objeto Spreadsheet recién creado.
        """
        return self._document_service.create(self._get_client(), title, folder_id)

    @retry_on_rate_limit
    def delete_spreadsheet(self, file_id: str) -> None:
        """
        Elimina un documento de Google Sheets por su ID.

        Parámetros:
            file_id (str): ID del documento a eliminar.
        """
        self._document_service.delete(self._get_client(), file_id)

    @retry_on_rate_limit
    def copy_spreadsheet(
        self,
        file_id: str,
        title: str | None = None,
        copy_permissions: bool = False,
        folder_id: str | None = None,
    ) -> gspread.Spreadsheet:
        """
        Crea una copia de un documento existente.

        Parámetros:
            file_id (str): ID del documento a copiar.
            title (str, opcional): Título de la copia.
            copy_permissions (bool, opcional): Si copia también los permisos. Por defecto False.
            folder_id (str, opcional): ID de la carpeta de Drive destino.

        Devuelve:
            El objeto Spreadsheet de la copia.
        """
        return self._document_service.copy(
            self._get_client(), file_id, title, copy_permissions, folder_id
        )

    @retry_on_rate_limit
    def list_spreadsheets(
        self, title: str | None = None, folder_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Lista los documentos de Google Sheets accesibles (vía Drive).

        Parámetros:
            title (str, opcional): Filtra por título.
            folder_id (str, opcional): Filtra por carpeta de Drive.

        Devuelve:
            Una lista de diccionarios con metadatos de cada documento (id, name, etc.).
        """
        return self._document_service.list(self._get_client(), title, folder_id)

    # ------------------------------------------------------------------
    # Permisos / compartir
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def share(
        self,
        email_address: str,
        role: str = "reader",
        perm_type: str = "user",
        notify: bool = True,
        email_message: str | None = None,
        with_link: bool = False,
        doc_name: str | None = None,
    ) -> Any:
        """
        Comparte el documento con un usuario, grupo, dominio o con cualquiera.

        Parámetros:
            email_address (str): Email del usuario/grupo/dominio (ignorado si perm_type='anyone').
            role (str): Rol: 'reader', 'writer', 'commenter' u 'owner'. Por defecto 'reader'.
            perm_type (str): Tipo: 'user', 'group', 'domain' o 'anyone'. Por defecto 'user'.
            notify (bool): Si notifica por email. Por defecto True.
            email_message (str, opcional): Mensaje del email de notificación.
            with_link (bool, opcional): Si comparte con enlace. Por defecto False.
            doc_name (str, opcional): Documento sobre el que operar; por defecto el activo.

        Devuelve:
            La respuesta de la API de Drive.
        """
        spreadsheet = self._resolve_spreadsheet(doc_name)
        return self._sharing_service.share(
            spreadsheet, email_address, role, perm_type, notify, email_message, with_link
        )

    @retry_on_rate_limit
    def list_permissions(self, doc_name: str | None = None) -> list[dict[str, Any]]:
        """
        Lista los permisos del documento.

        Parámetros:
            doc_name (str, opcional): Documento sobre el que operar; por defecto el activo.

        Devuelve:
            Una lista de diccionarios, uno por permiso.
        """
        spreadsheet = self._resolve_spreadsheet(doc_name)
        return self._sharing_service.list_permissions(spreadsheet)

    @retry_on_rate_limit
    def remove_permission(
        self, value: str, role: str = "any", doc_name: str | None = None
    ) -> list[str]:
        """
        Quita el permiso de un usuario/grupo/dominio del documento.

        Parámetros:
            value (str): Email o dominio cuyo permiso se quita.
            role (str): Rol a quitar ('any' para cualquiera). Por defecto 'any'.
            doc_name (str, opcional): Documento sobre el que operar; por defecto el activo.

        Devuelve:
            Lista de IDs de permisos eliminados.
        """
        spreadsheet = self._resolve_spreadsheet(doc_name)
        return self._sharing_service.remove_permission(spreadsheet, value, role)
