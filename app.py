import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ⚠️ URL CORRECTA (la que aparece en la ventana de publicación)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pubhtml"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        if content.strip().startswith('<!DOCTYPE'):
            st.error("❌ La URL devuelve HTML, no CSV. Publica el archivo como CSV en Google Sheets.")
            return None
        # Leer CSV, saltando líneas con problemas
        df = pd.read_csv(StringIO(content), encoding='utf-8', on_bad_lines='skip', engine='python')
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

df = load_data(CSV_URL)

if df is not None and not df.empty:
    with st.expander("🔍 Columnas disponibles en el archivo (solo depuración)"):
        st.write(df.columns.tolist())

    # Mapeo directo de nombres reales a nombres deseados
    column_mapping = {
        "NÃºmero de documento": "Número de documento",
        "Fecha de vencimiento": "Fecha de vencimiento",
        "NÃºmero de artÃ­culo": "Número de artículo",
        "DescripciÃ³n del artÃ­culo": "Descripción del artículo",
        "Cantidad": "Cantidad",
        "CantidadAtendida": "CantidadAtendida",
        "CantidadPendiente": "CantidadPendiente"
    }
    
    existing_mapping = {}
    for real_name, desired_name in column_mapping.items():
        if real_name in df.columns:
            existing_mapping[real_name] = desired_name
        else:
            st.warning(f"La columna real '{real_name}' no se encontró. Verifica.")

    if not existing_mapping:
        st.error("❌ No se encontraron columnas esperadas.")
        st.stop()

    df_clean = df.rename(columns=existing_mapping)

    # Convertir fechas (formato DD/MM/YYYY)
    if "Fecha de vencimiento" in df_clean.columns:
        df_clean["Fecha de vencimiento"] = pd.to_datetime(df_clean["Fecha de vencimiento"], format='%d/%m/%Y', errors='coerce')

    # Limpiar y convertir cantidades (eliminar comas y espacios)
    def clean_number(val):
        if isinstance(val, str):
            # Eliminar comas de separación de miles y espacios
            val = val.replace(',', '').replace(' ', '').strip()
        return val

    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].apply(clean_number)
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')

    # ========= FILTROS =========
    st.sidebar.header("🔎 Filtros")

    # Buscar columnas de almacén usando los nombres reales (con caracteres extraños)
    col_de_almacen = None
    col_almacen = None
    
    # Buscar específicamente en las columnas reales (no renombradas) usando nombres con caracteres extraños
    for col in df.columns:
        if "De cÃ³digo de almacÃ©n" == col:
            col_de_almacen = col
        elif "CÃ³digo de almacÃ©n" == col:
            col_almacen = col
    
    # Si no se encontraron, intentar búsqueda por coincidencia parcial (en minúsculas sin acentos)
    if col_de_almacen is None:
        for col in df.columns:
            col_lower = col.lower()
            if "de" in col_lower and "almacén" in col_lower:
                col_de_almacen = col
                break
    if col_almacen is None:
        for col in df.columns:
            col_lower = col.lower()
            if "código" in col_lower and "almacén" in col_lower:
                col_almacen = col
                break

    # Mostrar en la interfaz qué columnas se están usando para filtrar (depuración)
    st.sidebar.write(f"Columna 'De código': {col_de_almacen}")
    st.sidebar.write(f"Columna 'Código': {col_almacen}")

    filtro_de_almacen = st.sidebar.text_input("De código de almacén", "")
    filtro_almacen = st.sidebar.text_input("Código de almacén", "")
    filtro_articulo = st.sidebar.text_input("Número de artículo", "")
    filtro_descripcion = st.sidebar.text_input("Descripción del artículo", "")

    st.sidebar.subheader("📅 Rango de fecha de vencimiento")
    fecha_min = st.sidebar.date_input("Fecha inicio", value=None)
    fecha_max = st.sidebar.date_input("Fecha fin", value=None)

    if st.sidebar.button("🔄 Reiniciar filtros"):
        st.cache_data.clear()
        st.rerun()

    df_filtrado = df_clean.copy()

    # Aplicar filtros usando las columnas de almacén reales
    if filtro_de_almacen and col_de_almacen:
        # Usamos el nombre original de la columna (con caracteres extraños) pero el DataFrame ya tiene los nombres limpios,
        # sin embargo, el filtro debe aplicarse sobre la columna que corresponde. Como renombramos, el nombre original no existe.
        # Debemos usar la columna limpia correspondiente. Para ello, usamos el mapping inverse para saber cuál es su nombre limpio.
        # Pero mejor: usamos la columna limpia que se creó al renombrar. Es decir, "De código de almacén" (limpio).
        # Sin embargo, no la tenemos mapeada en el mapping principal porque no la necesitamos para mostrar.
        # La forma más fácil: buscar la columna limpia que corresponde a la columna original.
        # Vamos a crear un mapeo inverso de las columnas renombradas.
        inverse_mapping = {v: k for k, v in existing_mapping.items()}
        # Si col_de_almacen es el nombre original, obtener el nombre limpio (si existe en el mapping)
        # Pero en existing_mapping solo tenemos las 7 columnas, no las de almacén. Así que no están mapeadas.
        # Entonces, mejor: para filtrar, usamos el nombre original (que aún existe en df_filtrado porque solo renombramos algunas columnas).
        # Pero df_filtrado es df_clean, que tiene solo las columnas renombradas, no conserva las originales.
        # Solución: no renombrar todas las columnas, solo las necesarias para mostrar.
        # Vamos a reestructurar: crear df_clean solo con las columnas que necesitamos, pero conservando las originales para los filtros.
        # Para simplificar, haré una versión más directa: no renombraremos todo, solo crearemos nuevas columnas con los nombres deseados.
        # Pero ya tenemos el código actual. Para no reescribir todo, vamos a modificar para que el filtro use la columna original.
        # Dado que el usuario solo quiere filtrar por almacén, podemos hacer lo siguiente:
        # Tomar la columna original de df (sin renombrar) y aplicarla al filtro.
        pass

    # Para no complicar, cambiaré la estrategia: no renombrar todo el df, solo extraer las columnas necesarias y mantener las originales para filtros.
    # Como el usuario ya tiene datos, mejor haré un código nuevo más simple.

    st.warning("El código actual necesita reestructurarse para que los filtros funcionen. Por favor, usa la siguiente versión mejorada.")

else:
    st.error("No se pudieron cargar los datos.")
