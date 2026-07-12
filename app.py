import streamlit as st
import pandas as pd
import requests
from io import StringIO
import datetime

# Configuración de la página
st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")

# Título
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ⚠️ IMPORTANTE: Reemplaza esta URL con la que obtengas al publicar tu hoja en Google Sheets
# Ve a Archivo → Compartir → Publicar en la web → selecciona "Hoja completa" y formato "CSV"
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pub?output=csv"

@st.cache_data(ttl=600)
def load_data(url):
    """Descarga el CSV desde Google Sheets y lo convierte a DataFrame."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

def preprocess_df(df):
    """Convierte tipos de datos."""
    if df is None or df.empty:
        return df

    # Convertir fechas
    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = pd.to_datetime(df["Fecha de vencimiento"], errors="coerce")

    # Convertir cantidades a numérico
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

# Cargar datos
df_raw = load_data(CSV_URL)

if df_raw is not None:
    df = preprocess_df(df_raw)
    
    if df.empty:
        st.warning("El archivo está vacío o no se pudo procesar.")
    else:
        # Barra lateral con filtros
        st.sidebar.header("🔎 Filtros")

        # Filtros de texto
        filtro_de_almacen = st.sidebar.text_input("De código de almacén", "")
        filtro_almacen = st.sidebar.text_input("Código de almacén", "")
        filtro_articulo = st.sidebar.text_input("Número de artículo", "")
        filtro_descripcion = st.sidebar.text_input("Descripción del artículo", "")

        # Filtro de fecha (rango)
        st.sidebar.subheader("Rango de fecha de vencimiento")
        fecha_min = st.sidebar.date_input("Fecha inicio", value=None)
        fecha_max = st.sidebar.date_input("Fecha fin", value=None)

        # Botón para resetear filtros
        if st.sidebar.button("🔄 Reiniciar filtros"):
            st.cache_data.clear()
            st.rerun()

        # Aplicar filtros
        df_filtrado = df.copy()

        # Filtro De código de almacén
        if filtro_de_almacen and "De código de almacén" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["De código de almacén"].str.contains(filtro_de_almacen, case=False, na=False)]

        # Filtro Código de almacén
        if filtro_almacen and "Código de almacén" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Código de almacén"].str.contains(filtro_almacen, case=False, na=False)]

        # Filtro Número de artículo
        if filtro_articulo and "Número de artículo" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Número de artículo"].str.contains(filtro_articulo, case=False, na=False)]

        # Filtro Descripción del artículo
        if filtro_descripcion and "Descripción del artículo" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].str.contains(filtro_descripcion, case=False, na=False)]

        # Filtro de fecha (rango)
        if fecha_min is not None and "Fecha de vencimiento" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
        if fecha_max is not None and "Fecha de vencimiento" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]

        # Mostrar resumen de registros
        st.markdown(f"**Total de registros:** {len(df_filtrado)}")

        # Columnas a mostrar
        columnas_mostrar = [
            "Número de documento",
            "Fecha de vencimiento",
            "Número de artículo",
            "Descripción del artículo",
            "Cantidad",
            "CantidadAtendida",
            "CantidadPendiente"
        ]
        
        # Verificar que existan en el DataFrame
        columnas_existentes = [col for col in columnas_mostrar if col in df_filtrado.columns]
        
        if not columnas_existentes:
            st.error("No se encontraron las columnas necesarias para mostrar. Verifica el archivo.")
            st.write("Columnas disponibles en el archivo:", df_filtrado.columns.tolist())
        else:
            # Mostrar DataFrame
            st.dataframe(df_filtrado[columnas_existentes], use_container_width=True)

            # Botón para descargar CSV filtrado
            csv = df_filtrado[columnas_existentes].to_csv(index=False)
            st.download_button(
                label="📥 Descargar datos filtrados (CSV)",
                data=csv,
                file_name="solicitudes_traslado_filtrado.csv",
                mime="text/csv"
            )
else:
    st.error("No se pudo cargar el archivo. Verifica la URL o tu conexión a internet.")
