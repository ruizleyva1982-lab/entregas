import streamlit as st
import pandas as pd
import requests
from io import StringIO
import datetime

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ⚠️ REEMPLAZA ESTA URL CON LA QUE OBTENGAS AL PUBLICAR TU HOJA EN GOOGLE SHEETS
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pub?output=csv"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

def preprocess_df(df):
    if df is None or df.empty:
        return df

    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = pd.to_datetime(df["Fecha de vencimiento"], errors="coerce")

    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# Cargar datos
df_raw = load_data(CSV_URL)

if df_raw is not None:
    df = preprocess_df(df_raw)

    # Mostrar columnas disponibles (comenta o elimina esta línea después de ajustar)
    # st.write("Columnas disponibles:", df.columns.tolist())

    if df.empty:
        st.warning("El archivo está vacío o no se pudo procesar.")
    else:
        st.sidebar.header("🔎 Filtros")

        filtro_de_almacen = st.sidebar.text_input("De código de almacén", "")
        filtro_almacen = st.sidebar.text_input("Código de almacén", "")
        filtro_articulo = st.sidebar.text_input("Número de artículo", "")
        filtro_descripcion = st.sidebar.text_input("Descripción del artículo", "")

        st.sidebar.subheader("Rango de fecha de vencimiento")
        fecha_min = st.sidebar.date_input("Fecha inicio", value=None)
        fecha_max = st.sidebar.date_input("Fecha fin", value=None)

        if st.sidebar.button("🔄 Reiniciar filtros"):
            st.cache_data.clear()
            st.rerun()

        df_filtrado = df.copy()

        if filtro_de_almacen and "De código de almacén" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["De código de almacén"].str.contains(filtro_de_almacen, case=False, na=False)]

        if filtro_almacen and "Código de almacén" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Código de almacén"].str.contains(filtro_almacen, case=False, na=False)]

        if filtro_articulo and "Número de artículo" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Número de artículo"].str.contains(filtro_articulo, case=False, na=False)]

        if filtro_descripcion and "Descripción del artículo" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].str.contains(filtro_descripcion, case=False, na=False)]

        if fecha_min is not None and "Fecha de vencimiento" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
        if fecha_max is not None and "Fecha de vencimiento" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]

        st.markdown(f"**Total de registros:** {len(df_filtrado)}")

        # 🔽 Definimos las columnas que queremos mostrar
        columnas_deseadas = [
            "Número de documento",
            "Fecha de vencimiento",
            "Número de artículo",
            "Descripción del artículo",
            "Cantidad",
            "CantidadAtendida",
            "CantidadPendiente"
        ]

        # Verificamos cuáles existen realmente
        columnas_existentes = [col for col in columnas_deseadas if col in df_filtrado.columns]

        if not columnas_existentes:
            st.error("No se encontraron las columnas necesarias. Verifica los nombres.")
            st.write("Columnas disponibles en el archivo:", df_filtrado.columns.tolist())
        else:
            # Mostrar DataFrame solo con las columnas existentes
            st.dataframe(df_filtrado[columnas_existentes], use_container_width=True)

            # Botón descarga
            csv = df_filtrado[columnas_existentes].to_csv(index=False)
            st.download_button(
                label="📥 Descargar datos filtrados (CSV)",
                data=csv,
                file_name="solicitudes_traslado_filtrado.csv",
                mime="text/csv"
            )
else:
    st.error("No se pudo cargar el archivo. Verifica la URL o tu conexión a internet.")
