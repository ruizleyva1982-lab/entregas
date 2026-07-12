import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ✅ URL CORRECTA (la que aparece en la imagen de publicación)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pub?output=csv"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

df = load_data(CSV_URL)

if df is not None and not df.empty:
    # Nombres de columnas EXACTOS según tu archivo
    columnas = [
        "Número de documento",
        "Fecha de vencimiento",
        "Número de artículo",
        "Descripción del artículo",
        "Cantidad",
        "CantidadAtendida",
        "CantidadPendiente"
    ]
    
    # Verificar que todas existan
    faltantes = [col for col in columnas if col not in df.columns]
    if faltantes:
        st.error(f"❌ Faltan columnas: {faltantes}")
        st.write("Columnas disponibles:", df.columns.tolist())
        st.stop()
    
    # Convertir fechas y números
    df["Fecha de vencimiento"] = pd.to_datetime(df["Fecha de vencimiento"], errors='coerce')
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Filtros en barra lateral
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
    
    if filtro_de_almacen:
        df_filtrado = df_filtrado[df_filtrado["De código de almacén"].astype(str).str.contains(filtro_de_almacen, case=False, na=False)]
    if filtro_almacen:
        df_filtrado = df_filtrado[df_filtrado["Código de almacén"].astype(str).str.contains(filtro_almacen, case=False, na=False)]
    if filtro_articulo:
        df_filtrado = df_filtrado[df_filtrado["Número de artículo"].astype(str).str.contains(filtro_articulo, case=False, na=False)]
    if filtro_descripcion:
        df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].astype(str).str.contains(filtro_descripcion, case=False, na=False)]
    if fecha_min:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
    if fecha_max:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]
    
    st.markdown(f"**Total de registros:** {len(df_filtrado)}")
    
    # Mostrar SOLO las 7 columnas
    st.dataframe(df_filtrado[columnas], use_container_width=True)
    
    # Botón de descarga
    csv = df_filtrado[columnas].to_csv(index=False)
    st.download_button("📥 Descargar datos filtrados (CSV)", data=csv, file_name="solicitudes_filtrado.csv", mime="text/csv")
    
elif df is not None and df.empty:
    st.warning("El archivo está vacío.")
else:
    st.error("No se pudo cargar el archivo. Verifica la URL.")
