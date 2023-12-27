import gspread
from oauth2client.service_account import ServiceAccountCredentials
from .config import DEFAULT_VALUE_INPUT_OPTION
import pandas as pd

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

    def __init__(self, doc_name, json_google_file, sheet_name=None):
        """
        Inicializa un nuevo objeto GoogleSheetConector.

        Parámetros:
            doc_name (str): Nombre del documento de Google Sheets a conectar.
            json_google_file (str): Ruta al archivo JSON con las credenciales de Google.
            sheet_name (str, opcional): Nombre de la hoja específica en el documento. Por defecto es None y toma la primer hoja.
        """
        self.sheet_title = doc_name
        self.json_google_file = json_google_file
        self.tab_name = sheet_name
        self.sheet = self.connect_to_sheet(self.sheet_title, self.tab_name)
        self.options = {'valueInputOption': 'USER_ENTERED'}

    def connect_to_sheet(self, doc_name, sheet_name=None):
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
            Es necesario tener un archivo JSON con las credenciales de la cuenta de servicio de Google correctamente configuradas y accesibles para la instancia de GoogleSheetConector.
        """
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_google_file, scope)
        client = gspread.authorize(creds)
        if sheet_name:
            return client.open(doc_name).worksheet(sheet_name)
        else:
            return client.open(doc_name).sheet1


    def update_cell(self, sheet, row_index, col_index, value):
        """
        Actualiza el valor de una celda específica en la hoja de cálculo dada.

        Esta función modifica el contenido de una celda identificada por su índice de fila y columna en la hoja de cálculo proporcionada. El nuevo valor de la celda se especifica en el parámetro 'value'.

        Parámetros:
            sheet: Objeto de hoja de cálculo en el que se realizará la actualización. Este objeto debe ser obtenido a través de la función 'connect_to_sheet'.
            row_index (int): Índice de la fila de la celda a actualizar. El índice comienza en 1 (no en 0).
            col_index (int): Índice de la columna de la celda a actualizar. Al igual que el índice de fila, comienza en 1.
            value: Valor nuevo para la celda especificada. Puede ser de tipo string, número, o cualquier otro valor soportado por Google Sheets.

        Ejemplo:
            # Actualizar la celda en la fila 2, columna 3 con el valor "Hola Mundo"
            hoja = conector.connect_to_sheet("MiDocumento", "Hoja1")
            conector.update_cell(hoja, 2, 3, "Hola Mundo")

        Nota:
            Asegúrate de que la hoja de cálculo proporcionada esté conectada y accesible a través de la instancia de GoogleSheetConector.
        """
        sheet.update_cell(row_index, col_index, value)

    def update_row(self, sheet, row_index, data, start_column=None):
        """
        Actualiza una fila completa o una parte de ella en la hoja de cálculo especificada.

        Esta función recorre una lista de valores (data) y actualiza las celdas correspondientes en la fila especificada de la hoja de cálculo. La actualización comienza desde la columna indicada por 'start_column' o desde la primera columna si 'start_column' no se especifica.

        Parámetros:
            sheet: Objeto de hoja de cálculo en el que se realizará la actualización. Este objeto debe ser obtenido a través de la función 'connect_to_sheet'.
            contact_row (int): Índice de la fila en la que se realizarán las actualizaciones. El índice comienza en 1.
            data (list): Lista de valores que se utilizarán para actualizar la fila. Cada elemento de la lista corresponde a una celda en la fila.
            start_column (int, opcional): Índice de la columna desde la cual comenzará la actualización. Si no se proporciona, se asume que la actualización comienza desde la primera columna. El índice comienza en 1.

        Ejemplo:
            # Actualizar la fila 5 con los valores ["Nombre", "Correo", "Teléfono"], comenzando desde la columna 2
            hoja = conector.connect_to_sheet("MiDocumento", "Hoja1")
            conector.update_row(hoja, 5, ["Nombre", "Correo", "Teléfono"], start_column=2)

        Nota:
            Ten en cuenta que esta función actualizará cada celda en la fila de forma individual, lo que puede resultar en múltiples llamadas a la API de Google Sheets.
        """
        for index, value in enumerate(data, start=(start_column or 1)):
            sheet.update_cell(row_index, index, value)

    def spreadsheet_read_range(self, sheet, tab_name, fila_start, fila_end, column_start, column_end):
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

        Devuelve:
            Una lista de diccionarios, donde cada diccionario contiene el número de fila ('fila') y una lista de valores ('values') para esa fila.

        Ejemplo:
            # Leer datos desde la fila 1 a la 5, de la columna A a la D, en la pestaña 'Hoja1'
            datos = conector.spreadsheet_read_range(sheet, 'Hoja1', 1, 5, 'A', 'D')

        Nota:
            Asegúrate de que las letras de columna y los índices de fila proporcionados correspondan a un rango válido en la hoja de cálculo.
        """
        # Conversión de índices de fila a string para construir el rango de celdas
        fila_start_str = str(fila_start)
        fila_end_str = str(fila_end)

        # Obtención de datos del rango especificado
        data_range = tab_name + "!" + column_start + fila_start_str + ":" + column_end + fila_end_str
        data = sheet.values_get(data_range)
        content = []

        # Procesamiento de los datos obtenidos
        if "values" in data:
            for row_values in data['values']:
                row_data = {"fila": fila_start, "values": row_values}
                content.append(row_data)
                fila_start += 1

        return content

    def read_sheet_data(self, tab_name=None, skiprows=0, output_format='list'):
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

        # Obtener todos los valores de la hoja de cálculo
        all_values = self.sheet.get_all_values()[skiprows:]

        # Devolver los datos en el formato especificado
        if output_format == 'dict':
            if not all_values:
                return []
            headers = all_values[0]
            return [dict(zip(headers, row)) for row in all_values[1:]]

        elif output_format == 'pandas':
            return pd.DataFrame(all_values[1:], columns=all_values[0])

        else:  # output_format == 'list'
            return all_values

    def spreadsheet_append(self, data, tab_name=None):
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

        # Añadir los datos a la hoja de cálculo
        result = self.sheet.append_rows(data, value_input_option=DEFAULT_VALUE_INPUT_OPTION)

        return result

    def get_rows_where_column_equals(self, column, value):
        """
        Obtiene todas las filas de la hoja de cálculo donde una columna específica tiene un valor dado.
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
        data = self.sheet.get_all_values()
        rows_with_value = []

        # Agregamos 1 al índice porque los índices de las filas en la hoja de cálculo comienzan en 1
        for index, row in enumerate(data, start=1):
            if len(row) > column and row[column] == value:
                rows_with_value.append((index, row))  # Guarda el número de fila y la fila

        return rows_with_value

    def batch_update(self, range_data, value_input_option=DEFAULT_VALUE_INPUT_OPTION):
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
        # Realizar las actualizaciones en lote
        self.sheet.batch_update(range_data, value_input_option=value_input_option)

    def get_last_row(self, tab_name=None):
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

        # Obtener todos los valores de la hoja
        all_values = self.sheet.get_all_values()

        # Devolver el índice de la última fila con datos
        return len(all_values)

    def get_row_with_empty_in_column(self, sheet, column_letter):
        """
        Encuentra la primera fila con una celda vacía en una columna específica.

        Parámetros:
            sheet: Objeto de hoja de cálculo en el que se realizará la búsqueda.
            column_letter (str): Letra de la columna en la que buscar la celda vacía.

        Devuelve:
            Una tupla que contiene la fila completa donde se encontró la primera celda vacía y el índice de esa fila, o (None, None) si no se encuentra una celda vacía.

        Ejemplo:
            fila, indice = conector.get_row_with_empty_in_column(sheet, 'B')

        Nota:
            Si no se encuentra una celda vacía en la columna especificada, se devuelve (None, None).
        """
        # Obtener el rango de la columna especificada hasta la última fila con datos
        total_rows = len(sheet.col_values(1))
        target_column_values = sheet.range(f'{column_letter}1:{column_letter}{total_rows}')
        target_column_values = [cell.value for cell in target_column_values]

        # Buscar el primer valor vacío en la columna
        try:
            empty_index = target_column_values.index('') + 1
            return sheet.row_values(empty_index), empty_index
        except ValueError:
            return None, None

    def spreadsheet_insert(self, sheet_name, worksheet_name, data, fila=None):
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

        # Validar la entrada de datos
        if not all(isinstance(row, list) for row in data):
            raise ValueError("Los datos deben ser una lista de listas.")
        if not all(len(row) == len(data[0]) for row in data):
            raise ValueError("Todas las filas de datos deben tener la misma longitud.")

        # Calcular la fila de inicio y el rango de inserción
        if fila is None:
            # Si la fila no se especifica, insertar al final
            fila = len(sheet.get_all_values()) + 1
        fila_end = fila + len(data) - 1
        column_end_letter = chr(ord('A') + len(data[0]) - 1)  # Asumiendo que data[0] representa el ancho de los datos
        rango = f'{worksheet_name}!A{fila}:{column_end_letter}{fila_end}'

        try:
            insert = {'values': data}
            result = sheet.values_append(rango, self.options, insert)
            return result
        except Exception as e:
            raise Exception(f"Error al insertar datos en {worksheet_name}: {e}")
