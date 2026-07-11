import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Configuración de la página de Streamlit
st.set_page_config(
    page_title="Control de Traslados - SAP B1",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado para mejorar la interfaz
st.markdown("""
    <style>
    .main-title { font-size:32px; font-weight:bold; color:#1E3A8A; margin-bottom:5px; }
    .subtitle { font-size:16px; color:#4B5563; margin-bottom:25px; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📦 Dashboard de Solicitudes de Traslado (SAP B1)</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Monitoreo en tiempo real de inventario regular, intermedios y materias primas en tránsito.</div>', unsafe_allow_html=True)

st.sidebar.header("🔗 Configuración de Datos")
gsheet_url = st.sidebar.text_input(
    "Enlace de Google Sheets (CSV publicado):",
    placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv"
)

# Función para limpiar texto y evitar problemas de acentos/espacios
def clean_column_name(col):
    return str(col).strip().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')

@st.cache_data(ttl=60)
def load_data(url):
    try:
        # Forzar lectura como texto para evitar pérdida de ceros a la izquierda
        df = pd.read_csv(url, dtype=str)
        
        # Normalizar nombres de columnas (limpiar espacios y acentos)
        df.columns = [clean_column_name(c) for c in df.columns]
        
        # Mapeo de columnas esperadas a lo que pueda venir en el CSV
        column_mapping = {
            'De codigo de almacen': ['De código de almacén', 'De codigo de almacen', 'De codigo almacen'],
            'Codigo de almacen': ['Código de almacén', 'Codigo de almacen', 'Codigo almacen'],
            'Fecha de vencimiento': ['Fecha de vencimiento', 'Fecha vencimiento'],
            'Numero de articulo': ['Número de artículo', 'Numero de articulo', 'Numero articulo', 'Articulo'],
            'Descripcion del articulo': ['Descripción del artículo', 'Descripcion del articulo', 'Descripcion articulo', 'Descripcion'],
            'Numero de documento': ['Número de documento', 'Numero de documento', 'Numero documento', 'Documento'],
            'Cantidad': ['Cantidad'],
            'CantidadAtendida': ['CantidadAtendida', 'Cantidad Atendida'],
            'CantidadPendiente': ['CantidadPendiente', 'Cantidad Pendiente']
        }
        
        # Renombrar dinámicamente si encuentra alguna coincidencia
        for key, alternatives in column_mapping.items():
            for alt in alternatives:
                alt_clean = clean_column_name(alt)
                if alt_clean in df.columns and alt_clean != key:
                    df = df.rename(columns={alt_clean: key})
                    break

        # Conversión de Fechas de forma segura
        if 'Fecha de vencimiento' in df.columns:
            df['Fecha de vencimiento'] = pd.to_datetime(df['Fecha de vencimiento'], errors='coerce').dt.date
        else:
            df['Fecha de vencimiento'] = datetime.today().date()

        # Limpieza de códigos de almacén para quitar decimales como '.0'
        for col in ['De codigo de almacen', 'Codigo de almacen']:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # Asegurar tipos numéricos para las cantidades
        for col in ['Cantidad', 'CantidadAtendida', 'CantidadPendiente']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else:
                df[col] = 0.0
                
        return df
    except Exception as e:
        st.error(f"Error al procesar los datos: {e}")
        return None

if gsheet_url:
    df_raw = load_data(gsheet_url)
    
    if df_raw is not None:
        st.sidebar.header("🔍 Filtros de Búsqueda")
        
        # 1. Filtro de Fechas seguro
        dates_valid = df_raw['Fecha de vencimiento'].dropna()
        min_date = dates_valid.min() if not dates_valid.empty else datetime.today().date()
        max_date = dates_valid.max() if not dates_valid.empty else datetime.today().date()
        
        if min_date == max_date:
            st.sidebar.info(f"Fecha única detectada: {min_date}")
            date_range = (min_date, max_date)
        else:
            date_range = st.sidebar.date_input("Fecha de vencimiento (Rango):", value=(min_date, max_date))
        
        # 2. Filtros de Almacenes
        almacenes_origen = sorted([x for x in df_raw['De codigo de almacen'].unique() if x]) if 'De codigo de almacen' in df_raw.columns else []
        selected_origen = st.sidebar.multiselect("De código de almacén:", almacenes_origen, default=almacenes_origen)
        
        almacenes_destino = sorted([x for x in df_raw['Codigo de almacen'].unique() if x]) if 'Codigo de almacen' in df_raw.columns else []
        selected_destino = st.sidebar.multiselect("Código de almacén (Destino):", almacenes_destino, default=almacenes_destino)
        
        # 3. Filtro por Artículo o Descripción
        search_query = st.sidebar.text_input("Buscar por Código o Descripción de Artículo:").strip().lower()
        
        # --- Aplicar Filtros ---
        df_filtered = df_raw.copy()
        
        if len(date_range) == 2:
            df_filtered = df_filtered[(df_filtered['Fecha de vencimiento'] >= date_range[0]) & (df_filtered['Fecha de vencimiento'] <= date_range[1])]
            
        if selected_origen:
            df_filtered = df_filtered[df_filtered['De codigo de almacen'].isin(selected_origen)]
        if selected_destino:
            df_filtered = df_filtered[df_filtered['Codigo de almacen'].isin(selected_destino)]
            
        if search_query:
            cond_art = df_filtered['Numero de articulo'].astype(str).str.lower().str.contains(search_query) if 'Numero de articulo' in df_filtered.columns else False
            cond_desc = df_filtered['Descripcion del articulo'].astype(str).str.lower().str.contains(search_query) if 'Descripcion del articulo' in df_filtered.columns else False
            df_filtered = df_filtered[cond_art | cond_desc]
            
        # --- Despliegue de Columnas Solicitadas ---
        target_columns = {
            'Numero de documento': 'N° Documento',
            'Fecha de vencimiento': 'F. Vencimiento',
            'Numero de articulo': 'Código Artículo',
            'Descripcion del articulo': 'Descripción',
            'Cantidad': 'Cant. Solicitada',
            'CantidadAtendida': 'Cant. Atendida',
            'CantidadPendiente': 'Cant. Pendiente'
        }
        
        # Filtrar solo columnas existentes y renombrar para mostrar limpio
        cols_to_use = [c for c in target_columns.keys() if c in df_filtered.columns]
        df_display = df_filtered[cols_to_use].rename(columns={c: target_columns[c] for c in cols_to_use})
        
        # KPIs rápidos
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
