import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# URL que aparece en la ventana de publicación (con ...BpleKO79...)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4Celsd5d-OCORyKxWx11WAC1XHYSJH74oCgaww6Cc4dc_rWY-BpleKO79_6_7bhDcK_PxfotVF/pub?gid=420751890&single=true&output=csv"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        # Si el contenido empieza con "<!DOCTYPE", es que no es CSV, es HTML
        if content.strip().startswith('<!DOCTYPE'):
            st.error("La URL no está devolviendo un CSV, sino una página HTML. Asegúrate de publicar correctamente el archivo en formato CSV (Archivo → Compartir → Publicar en la web → seleccionar 'Hoja completa' y formato 'CSV').")
            return None
        # Leer CSV, saltando líneas problemáticas
        df = pd.read_csv(StringIO(content), encoding='utf-8', on_bad_lines='skip', engine='python')
        if df.empty:
            st.warning("El archivo CSV está vacío.")
            return None
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return None

df = load_data(CSV_URL)

if df is not None and not df.empty:
    # Mostrar columnas reales para depuración (opcional)
    with st.expander("🔍 Columnas disponibles en el archivo (depuración)"):
        st.write(df.columns.tolist())
    
    # Mapeo de nombres reales (tal como aparecen en el archivo) a nombres deseados
    # Los nombres reales los tomamos de la lista que apareció en el error
    column_mapping = {
        "NÃºmero de documento": "Número de documento",
        "Fecha de vencimiento": "Fecha de vencimiento",
        "NÃºmero de artÃ­culo": "Número de artículo",
        "DescripciÃ³n del artÃ­culo": "Descripción del artículo",
        "Cantidad": "Cantidad",
        "CantidadAtendida": "CantidadAtendida",
        "CantidadPendiente": "CantidadPendiente"
    }
    
    # Verificar qué columnas del mapeo existen realmente
    existing_mapping = {}
    for real_name, desired_name in column_mapping.items():
        if real_name in df.columns:
            existing_mapping[real_name] = desired_name
        else:
            st.warning(f"La columna real '{real_name}' no se encontró en el archivo. Puede que el nombre sea ligeramente diferente.")
    
    if not existing_mapping:
        st.error("No se encontró ninguna de las columnas esperadas. Verifica la publicación del archivo.")
        st.stop()
    
    # Renombrar columnas
    df_clean = df.rename(columns=existing_mapping)
    
    # Convertir fechas (formato DD/MM/YYYY)
    if "Fecha de vencimiento" in df_clean.columns:
        df_clean["Fecha de vencimiento"] = pd.to_datetime(
            df_clean["Fecha de vencimiento"],
            format='%d/%m/%Y',
            errors='coerce'
        )
    
    # Convertir cantidades a numérico
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    # Filtros en barra lateral
    st.sidebar.header("🔎 Filtros")
    
    # Para filtros de almacén, necesitamos los nombres reales también
    # Como puede que varíen, buscamos por coincidencia parcial
    col_de_almacen = None
    col_almacen = None
    for col in df.columns:
        if "cÃ³digo de almacÃ©n" in col.lower() or "de código" in col.lower():
            col_de_almacen = col
        if "código de almacén" in col.lower() or "cÃ³digo de almacÃ©n" in col.lower():
            if col != col_de_almacen:  # para evitar duplicar
                col_almacen = col
    # Si no se encontraron, intentar con otros nombres
    if col_de_almacen is None:
        for col in df.columns:
            if "de" in col.lower() and "almacén" in col.lower():
                col_de_almacen = col
                break
    if col_almacen is None:
        for col in df.columns:
            if "código" in col.lower() and "almacén" in col.lower():
                col_almacen = col
                break
    
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
    
    if filtro_de_almacen and col_de_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_de_almacen].astype(str).str.contains(filtro_de_almacen, case=False, na=False)]
    if filtro_almacen and col_almacen:
        df_filtrado = df_filtrado[df_filtrado[col_almacen].astype(str).str.contains(filtro_almacen, case=False, na=False)]
    if filtro_articulo and "Número de artículo" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["Número de artículo"].astype(str).str.contains(filtro_articulo, case=False, na=False)]
    if filtro_descripcion and "Descripción del artículo" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].astype(str).str.contains(filtro_descripcion, case=False, na=False)]
    if fecha_min and "Fecha de vencimiento" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
    if fecha_max and "Fecha de vencimiento" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]
    
    st.markdown(f"**Total de registros:** {len(df_filtrado)}")
    
    # Columnas a mostrar
    columnas_mostrar = ["Número de documento", "Fecha de vencimiento", "Número de artículo", 
                        "Descripción del artículo", "Cantidad", "CantidadAtendida", "CantidadPendiente"]
    existentes = [col for col in columnas_mostrar if col in df_filtrado.columns]
    
    if existentes:
        st.dataframe(df_filtrado[existentes], use_container_width=True)
    else:
        st.error("No se encontraron las columnas para mostrar.")
        st.write("Columnas disponibles después del renombrado:", df_filtrado.columns.tolist())
    
    if existentes:
        csv = df_filtrado[existentes].to_csv(index=False)
        st.download_button("📥 Descargar datos filtrados (CSV)", data=csv, file_name="solicitudes_filtrado.csv", mime="text/csv")

else:
    st.error("No se pudieron cargar los datos. Verifica la URL y la publicación.")
