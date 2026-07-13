import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ⚠️ URL CORRECTA (copia la que aparece en la ventana de publicación)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4Celsd5d-OCORyKxWx11WAC1XHYSJH74oCgaww6Cc4dc_rWY-BpleKO79_6_7bhDcK_PxfotVF/pub?gid=420751890&single=true&output=csv"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        if content.strip().startswith('<!DOCTYPE'):
            st.error("❌ La URL devuelve HTML, no CSV. Publica el archivo como CSV en Google Sheets.")
            return None
        df = pd.read_csv(StringIO(content), encoding='utf-8', on_bad_lines='skip', engine='python')
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

df = load_data(CSV_URL)

if df is not None and not df.empty:
    # Mostrar columnas para depuración (opcional)
    with st.expander("🔍 Columnas disponibles en el archivo (solo depuración)"):
        st.write(df.columns.tolist())

    # 1. Renombrar las 7 columnas de interés a nombres limpios
    #    Mapeo de nombres reales (con caracteres extraños) a nombres deseados
    column_mapping = {
        "NÃºmero de documento": "Número de documento",
        "Fecha de vencimiento": "Fecha de vencimiento",
        "NÃºmero de artÃ­culo": "Número de artículo",
        "DescripciÃ³n del artÃ­culo": "Descripción del artículo",
        "Cantidad": "Cantidad",
        "CantidadAtendida": "CantidadAtendida",
        "CantidadPendiente": "CantidadPendiente"
    }
    
    # Aplicar renombrado solo a las columnas que existen
    for old, new in column_mapping.items():
        if old in df.columns:
            df.rename(columns={old: new}, inplace=True)

    # 2. Convertir fechas (formato DD/MM/YYYY)
    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = pd.to_datetime(
            df["Fecha de vencimiento"],
            format='%d/%m/%Y',
            errors='coerce'
        )

    # 3. Limpiar y convertir cantidades (eliminar comas, espacios, etc.)
    def clean_number(val):
        if isinstance(val, str):
            val = val.replace(',', '').replace(' ', '').strip()
            if val == '':
                return None
        return val

    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 4. Encontrar las columnas de almacén (usando los nombres exactos con caracteres extraños)
    #    Estos son los nombres que aparecen en la lista de columnas del DataFrame original
    col_de_almacen = None
    col_almacen = None
    
    # Buscar exactamente los nombres con caracteres extraños
    for col in df.columns:
        if col == "De cÃ³digo de almacÃ©n":
            col_de_almacen = col
        elif col == "CÃ³digo de almacÃ©n":
            col_almacen = col
    
    # Si no se encontraron, buscar por coincidencia parcial (más flexible)
    if col_de_almacen is None:
        for col in df.columns:
            if "almacén" in col.lower() and "de" in col.lower():
                col_de_almacen = col
                break
    if col_almacen is None:
        for col in df.columns:
            if "almacén" in col.lower() and "código" in col.lower():
                col_almacen = col
                break

    # Mostrar en la barra lateral qué columnas se están usando
    st.sidebar.header("🔎 Filtros")
    st.sidebar.write(f"📌 Columna 'De código': **{col_de_almacen or 'No encontrada'}**")
    st.sidebar.write(f"📌 Columna 'Código': **{col_almacen or 'No encontrada'}**")

    # Advertencia si no se encontraron
    if col_de_almacen is None:
        st.sidebar.warning("⚠️ No se encontró la columna 'De código de almacén'. El filtro no funcionará.")
    if col_almacen is None:
        st.sidebar.warning("⚠️ No se encontró la columna 'Código de almacén'. El filtro no funcionará.")

    # ========= FILTROS =========
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

    # ========= Aplicar filtros =========
    df_filtrado = df.copy()

    if filtro_de_almacen and col_de_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_de_almacen].astype(str).str.contains(filtro_de_almacen, case=False, na=False)]
    if filtro_almacen and col_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_almacen].astype(str).str.contains(filtro_almacen, case=False, na=False)]
    if filtro_articulo:
        df_filtrado = df_filtrado[df_filtrado["Número de artículo"].astype(str).str.contains(filtro_articulo, case=False, na=False)]
    if filtro_descripcion:
        df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].astype(str).str.contains(filtro_descripcion, case=False, na=False)]
    if fecha_min:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
    if fecha_max:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]

    st.markdown(f"**Total de registros:** {len(df_filtrado)}")

    # ========= Mostrar datos =========
    columnas_mostrar = ["Número de documento", "Fecha de vencimiento", "Número de artículo", 
                        "Descripción del artículo", "Cantidad", "CantidadAtendida", "CantidadPendiente"]
    existentes = [col for col in columnas_mostrar if col in df_filtrado.columns]
    
    if existentes:
        st.dataframe(df_filtrado[existentes], use_container_width=True)
    else:
        st.error("No se encontraron las columnas para mostrar.")
    
    # Botón de descarga
    if existentes:
        csv = df_filtrado[existentes].to_csv(index=False)
        st.download_button("📥 Descargar datos filtrados (CSV)", data=csv, file_name="solicitudes_filtrado.csv", mime="text/csv")

else:
    st.error("No se pudieron cargar los datos. Verifica la URL y la publicación.")
