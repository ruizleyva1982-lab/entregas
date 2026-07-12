import streamlit as st
import pandas as pd
import requests
from io import StringIO
import unicodedata

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pub?gid=420751890&single=true&output=csv"

# Función para normalizar texto (quitar acentos y convertir a minúsculas)
def normalize_text(text):
    if isinstance(text, str):
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        return text.lower().strip()
    return text

# Función para encontrar el nombre real de la columna buscando por coincidencia
def find_column(df, search_term):
    """
    Busca en las columnas del DataFrame una que coincida (ignorando acentos y mayúsculas)
    con el término de búsqueda. Devuelve el nombre exacto de la columna o None.
    """
    search_norm = normalize_text(search_term)
    for col in df.columns:
        if normalize_text(col) == search_norm:
            return col
    # Si no encuentra coincidencia exacta, busca la primera que contenga el término
    for col in df.columns:
        if search_norm in normalize_text(col):
            return col
    return None

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), encoding='utf-8')
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

df = load_data(CSV_URL)

if df is not None:
    # Mostrar datos depuración (comenta después de ajustar)
    st.write("🔍 **Primeras 5 filas del archivo:**")
    st.dataframe(df.head())
    st.write("📋 **Columnas disponibles:**", df.columns.tolist())

    # Detectar columnas principales por coincidencia
    col_documento = find_column(df, "Número de documento")
    col_fecha_venc = find_column(df, "Fecha de vencimiento")
    col_articulo = find_column(df, "Número de artículo")
    col_descripcion = find_column(df, "Descripción del artículo")
    col_cantidad = find_column(df, "Cantidad")
    col_cant_atendida = find_column(df, "CantidadAtendida")
    col_cant_pendiente = find_column(df, "CantidadPendiente")
    col_de_almacen = find_column(df, "De código de almacén")
    col_almacen = find_column(df, "Código de almacén")

    # Lista de columnas a mostrar (solo si se encontraron)
    columnas_mostrar = []
    if col_documento: columnas_mostrar.append(col_documento)
    if col_fecha_venc: columnas_mostrar.append(col_fecha_venc)
    if col_articulo: columnas_mostrar.append(col_articulo)
    if col_descripcion: columnas_mostrar.append(col_descripcion)
    if col_cantidad: columnas_mostrar.append(col_cantidad)
    if col_cant_atendida: columnas_mostrar.append(col_cant_atendida)
    if col_cant_pendiente: columnas_mostrar.append(col_cant_pendiente)

    if not columnas_mostrar:
        st.error("No se encontraron las columnas necesarias. Verifica los nombres.")
        st.stop()

    # Convertir fechas
    if col_fecha_venc:
        df[col_fecha_venc] = pd.to_datetime(df[col_fecha_venc], errors='coerce')

    # Convertir cantidades a numérico
    for col in [col_cantidad, col_cant_atendida, col_cant_pendiente]:
        if col:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Barra lateral con filtros
    st.sidebar.header("🔎 Filtros")
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

    # Aplicar filtros
    df_filtrado = df.copy()

    if filtro_de_almacen and col_de_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_de_almacen].astype(str).str.contains(filtro_de_almacen, case=False, na=False)]
    if filtro_almacen and col_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_almacen].astype(str).str.contains(filtro_almacen, case=False, na=False)]
    if filtro_articulo and col_articulo:
        df_filtrado = df_filtrado[df_filtrado[col_articulo].astype(str).str.contains(filtro_articulo, case=False, na=False)]
    if filtro_descripcion and col_descripcion:
        df_filtrado = df_filtrado[df_filtrado[col_descripcion].astype(str).str.contains(filtro_descripcion, case=False, na=False)]

    if fecha_min and col_fecha_venc:
        df_filtrado = df_filtrado[df_filtrado[col_fecha_venc] >= pd.Timestamp(fecha_min)]
    if fecha_max and col_fecha_venc:
        df_filtrado = df_filtrado[df_filtrado[col_fecha_venc] <= pd.Timestamp(fecha_max)]

    st.markdown(f"**Total de registros:** {len(df_filtrado)}")

    # Mostrar solo las columnas seleccionadas
    st.dataframe(df_filtrado[columnas_mostrar], use_container_width=True)

    # Botón descarga
    csv = df_filtrado[columnas_mostrar].to_csv(index=False)
    st.download_button("📥 Descargar datos filtrados (CSV)", data=csv, file_name="solicitudes_filtrado.csv", mime="text/csv")
else:
    st.error("No se pudo cargar el archivo.")
