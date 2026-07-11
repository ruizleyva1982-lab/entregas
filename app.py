import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Control de Traslados - SAP B1",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-title { font-size:32px; font-weight:bold; color:#1E3A8A; margin-bottom:5px; }
    .subtitle { font-size:16px; color:#4B5563; margin-bottom:25px; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📦 Dashboard de Solicitudes de Traslado (SAP B1)</div>', unsafe_allow_html=True)

st.sidebar.header("🔗 Configuración de Datos")
gsheet_url = st.sidebar.text_input(
    "Enlace de Google Sheets (CSV publicado):",
    value="https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4Celsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotfV/pub?gid=420751890&single=true&output=csv"
)

# Función para limpiar texto y evitar problemas de acentos/espacios
def clean_column_name(col):
    return str(col).strip().lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')

@st.cache_data(ttl=10) # Cache bajo para pruebas rápidas
def load_data(url):
    try:
        # Leer todo como string originalmente para no perder datos
        df = pd.read_csv(url, dtype=str)
        
        # Guardar nombres originales para mapeo
        original_cols = list(df.columns)
        
        # Limpiar nombres de columnas
        df.columns = [clean_column_name(c) for c in df.columns]
        
        # Mapeo flexible
        mapping = {
            'de codigo de almacen': ['de codigo de almacen', 'de codigo almacen', 'almacen origen', 'almacen de origen', 'de almacen'],
            'codigo de almacen': ['codigo de almacen', 'codigo almacen', 'almacen destino', 'almacen', 'a almacen'],
            'fecha de vencimiento': ['fecha de vencimiento', 'fecha vencimiento', 'f. vencimiento', 'vencimiento'],
            'numero de articulo': ['numero de articulo', 'numero articulo', 'articulo', 'codigo articulo', 'itemcode'],
            'descripcion del articulo': ['descripcion del articulo', 'descripcion articulo', 'descripcion', 'itemname'],
            'numero de documento': ['numero de documento', 'numero documento', 'documento', 'n° documento', 'docnum'],
            'cantidad': ['cantidad', 'cant'],
            'cantidadatendida': ['cantidadatendida', 'cantidad atendida', 'atendida'],
            'cantidadpendiente': ['cantidadpendiente', 'cantidad pendiente', 'pendiente']
        }
        
        final_df = pd.DataFrame()
        
        # Buscar y asignar columnas de forma flexible
        for de_col, alts in mapping.items():
            found = False
            for alt in alts:
                alt_clean = clean_column_name(alt)
                if alt_clean in df.columns:
                    final_df[de_col] = df[alt_clean]
                    found = True
                    break
            if not found:
                # Si no la encuentra, crearla vacía o con ceros para que no rompa la app
                if de_col in ['cantidad', 'cantidadatendida', 'cantidadpendiente']:
                    final_df[de_col] = 0.0
                else:
                    final_df[de_col] = ""
                    
        # Conversión de tipos de datos de forma segura
        final_df['cantidad'] = pd.to_numeric(final_df['cantidad'], errors='coerce').fillna(0)
        final_df['cantidadatendida'] = pd.to_numeric(final_df['cantidadatendida'], errors='coerce').fillna(0)
        final_df['cantidadpendiente'] = pd.to_numeric(final_df['cantidadpendiente'], errors='coerce').fillna(0)
        
        # Limpieza de almacenes (.0)
        final_df['de codigo de almacen'] = final_df['de codigo de almacen'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        final_df['codigo de almacen'] = final_df['codigo de almacen'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        # Intentar convertir fecha de manera inteligente
        final_df['fecha_original'] = final_df['fecha de vencimiento']
        final_df['fecha de vencimiento'] = pd.to_datetime(final_df['fecha de vencimiento'], errors='coerce').dt.date
        
        return final_df, original_cols
    except Exception as e:
        st.error(f"Error al procesar el archivo CSV: {e}")
        return None, []

if gsheet_url:
    df_raw, columnas_detectadas = load_data(gsheet_url)
    
    if df_raw is not None and not df_raw.empty:
        # SECCIÓN DE DIAGNÓSTICO EN CASO DE TABLA VACÍA
        with st.expander("🔍 Ver columnas leídas desde Google Sheets (Uso técnico si no ves datos)"):
            st.write("Columnas encontradas en tu archivo original:", columnas_detectadas)
            st.write("Muestra de datos sin filtrar:", df_raw.head(3))
            
        st.sidebar.header("🔍 Filtros de Búsqueda")
        
        # 1. Filtro de Fechas con switch para apagarlo si causa problemas
        usar_filtro_fecha = st.sidebar.checkbox("Filtrar por Rango de Fechas", value=False)
        
        dates_valid = df_raw['fecha de vencimiento'].dropna()
        min_date = dates_valid.min() if not dates_valid.empty else datetime.today().date()
        max_date = dates_valid.max() if not dates_valid.empty else datetime.today().date()
        
        if usar_filtro_fecha:
            if min_date == max_date:
                date_range = (min_date, max_date)
            else:
                date_range = st.sidebar.date_input("Rango de fechas:", value=(min_date, max_date))
        
        # 2. Filtros de Almacenes
        almacenes_origen = sorted(list(set([x for x in df_raw['de codigo de almacen'].unique() if x])))
        selected_origen = st.sidebar.multiselect("De código de almacén:", almacenes_origen, default=almacenes_origen)
        
        almacenes_destino = sorted(list(set([x for x in df_raw['codigo de almacen'].unique() if x])))
        selected_destino = st.sidebar.multiselect("Código de almacén (Destino):", almacenes_destino, default=almacenes_destino)
        
        # 3. Filtro de texto
        search_query = st.sidebar.text_input("Buscar por Artículo o Descripción:").strip().lower()
        
        # --- PROCESO DE FILTRADO ---
        df_filtered = df_raw.copy()
        
        if usar_filtro_fecha and len(date_range) == 2:
            df_filtered = df_filtered[(df_filtered['fecha de vencimiento'] >= date_range[0]) & (df_filtered['fecha de vencimiento'] <= date_range[1])]
            
        if selected_origen:
            df_filtered = df_filtered[df_filtered['de codigo de almacen'].isin(selected_origen)]
        if selected_destino:
            df_filtered = df_filtered[df_filtered['codigo de almacen'].isin(selected_destino)]
            
        if search_query:
            cond_art = df_filtered['numero de articulo'].astype(str).str.lower().str.contains(search_query)
            cond_desc = df_filtered['descripcion del articulo'].astype(str).str.lower().str.contains(search_query)
            df_filtered = df_filtered[cond_art | cond_desc]
            
        # --- PREPARAR INTERFAZ ---
        target_columns = {
            'numero de documento': 'Número de documento',
            'fecha de vencimiento': 'Fecha de vencimiento',
            'numero de articulo': 'Número de artículo',
            'descripcion del articulo': 'Descripción del artículo',
            'cantidad': 'Cantidad',
            'cantidadatendida': 'CantidadAtendida',
            'cantidadpendiente': 'CantidadPendiente'
        }
        
        df_display = df_filtered[list(target_columns.keys())].rename(columns=target_columns)
        
        # KPIs
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("Total Documentos", f"{df_filtered['numero de documento'].nunique()} uds")
        with kpi2:
            st.metric("Suma Cantidad", f"{df_filtered['cantidad'].sum():,.2f}")
        with kpi3:
            st.metric("Suma Atendida", f"{df_filtered['cantidadatendida'].sum():,.2f}")
        with kpi4:
            st.metric("Suma Pendiente", f"{df_filtered['cantidadpendiente'].sum():,.2f}")
            
        st.write("---")
        
        st.subheader(f"📊 Registros Filtrados ({len(df_display)} filas)")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
    else:
        st.warning("El archivo conectado está vacío o no contiene filas de datos.")
else:
    st.info("💡 Por favor, ingresa tu enlace de Google Sheets publicado como CSV en la barra lateral.")
