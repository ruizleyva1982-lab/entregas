import streamlit as st
import pandas as pd
import requests
from io import StringIO
import unicodedata
import re

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# ⚠️ USA LA URL QUE APARECE EN LA VENTANA DE PUBLICACIÓN (CON ...BpleKO79...)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4Celsd5d-OCORyKxWx11WAC1XHYSJH74oCgaww6Cc4dc_rWY-BpleKO79_6_7bhDcK_PxfotVF/pub?gid=420751890&single=true&output=csv"

def normalize_column(name):
    """Normaliza un nombre de columna: quita acentos, convierte a minúsculas, elimina espacios."""
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'[^a-zA-Z0-9]', ' ', name)
    name = ' '.join(name.split())
    return name.strip().lower()

def find_column(df, search_names):
    """Busca una columna en el DataFrame que coincida (normalizada) con alguno de los nombres de búsqueda."""
    df_norm = {normalize_column(col): col for col in df.columns}
    for search in search_names:
        norm_search = normalize_column(search)
        if norm_search in df_norm:
            return df_norm[norm_search]
    return None

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        
        # Intentar con diferentes separadores y manejo de líneas malas
        for sep in [',', ';']:
            try:
                df = pd.read_csv(
                    StringIO(content),
                    sep=sep,
                    encoding='utf-8',
                    on_bad_lines='skip',  # <-- Salta líneas con número incorrecto de campos
                    engine='python'
                )
                if not df.empty:
                    return df
            except Exception:
                continue
        
        # Si falla, intentar con latin-1
        for sep in [',', ';']:
            try:
                df = pd.read_csv(
                    StringIO(content),
                    sep=sep,
                    encoding='latin-1',
                    on_bad_lines='skip',
                    engine='python'
                )
                if not df.empty:
                    return df
            except Exception:
                continue
        
        st.error("No se pudo leer el archivo con ningún separador.")
        return None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.error("❌ El enlace del archivo no es válido o no está publicado correctamente. Ve a Google Sheets → Archivo → Compartir → Publicar en la web, y copia el enlace de nuevo.")
        else:
            st.error(f"Error al cargar los datos: {e}")
        return None
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        return None

# Cargar datos
df = load_data(CSV_URL)

if df is not None and not df.empty:
    # Mapear nombres de columnas reales a las que necesitamos
    columnas_deseadas = {
        "Número de documento": ["documento", "num doc", "número doc"],
        "Fecha de vencimiento": ["vencimiento", "fecha venc", "fechavenc"],
        "Número de artículo": ["artículo", "num art", "número art"],
        "Descripción del artículo": ["descripción", "descrip", "desc art"],
        "Cantidad": ["cantidad", "cant"],
        "CantidadAtendida": ["atendida", "cant atendida"],
        "CantidadPendiente": ["pendiente", "cant pendiente"]
    }
    
    real_columns = {}
    for desired, search_terms in columnas_deseadas.items():
        col = find_column(df, search_terms + [desired])
        if col:
            real_columns[desired] = col
        else:
            st.warning(f"No se encontró la columna: {desired}")
    
    if len(real_columns) < 7:
        st.error("❌ Faltan columnas necesarias. Revisa los nombres en tu archivo.")
        st.write("Columnas disponibles en el archivo:", df.columns.tolist())
        st.stop()
    
    df_clean = df.rename(columns={real_columns[key]: key for key in real_columns})
    
    # 🔧 Convertir fechas con formato DD/MM/YYYY
    df_clean["Fecha de vencimiento"] = pd.to_datetime(
        df_clean["Fecha de vencimiento"], 
        format='%d/%m/%Y',  # <-- Día/Mes/Año
        errors='coerce'
    )
    
    # Convertir cantidades a numérico
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    st.sidebar.header("🔎 Filtros")
    
    col_de_almacen = find_column(df, ["de código de almacén", "de almacén", "almacen origen"])
    col_almacen = find_column(df, ["código de almacén", "almacén", "almacen destino"])
    
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
    if filtro_articulo:
        df_filtrado = df_filtrado[df_filtrado["Número de artículo"].astype(str).str.contains(filtro_articulo, case=False, na=False)]
    if filtro_descripcion:
        df_filtrado = df_filtrado[df_filtrado["Descripción del artículo"].astype(str).str.contains(filtro_descripcion, case=False, na=False)]
    if fecha_min:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] >= pd.Timestamp(fecha_min)]
    if fecha_max:
        df_filtrado = df_filtrado[df_filtrado["Fecha de vencimiento"] <= pd.Timestamp(fecha_max)]
    
    st.markdown(f"**Total de registros:** {len(df_filtrado)}")
    
    columnas_mostrar = ["Número de documento", "Fecha de vencimiento", "Número de artículo", 
                        "Descripción del artículo", "Cantidad", "CantidadAtendida", "CantidadPendiente"]
    
    existentes = [col for col in columnas_mostrar if col in df_filtrado.columns]
    if existentes:
        st.dataframe(df_filtrado[existentes], use_container_width=True)
    else:
        st.error("No se encontraron las columnas para mostrar.")
    
    if existentes:
        csv = df_filtrado[existentes].to_csv(index=False)
        st.download_button("📥 Descargar datos filtrados (CSV)", data=csv, file_name="solicitudes_filtrado.csv", mime="text/csv")
    
elif df is not None and df.empty:
    st.warning("El archivo está vacío. Verifica que tenga datos.")
else:
    st.error("No se pudo cargar el archivo. Verifica la URL.")
