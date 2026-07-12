
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Enlace fijo por defecto
default_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4Celsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotfV/pub?gid=420751890&single=true&output=csv"

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
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📦 Dashboard de Solicitudes de Traslado (SAP B1)</div>', unsafe_allow_html=True)

st.sidebar.header("🔗 Configuración de Datos")

gsheet_url = st.sidebar.text_input(
    "Enlace de Google Sheets (CSV publicado):",
    value=default_url
)

def clean_numeric_string(val):
    if pd.isna(val):
        return 0.0
    return str(val).replace(',', '').strip()

@st.cache_data(ttl=15)
def load_data(url):
    try:
        # Leer datos como texto plano
        df = pd.read_csv(url, dtype=str)
        
        # Crear un mapa de columnas normalizado (sin acentos, en minúsculas)
        cols_normalizadas = {
            str(c).lower().strip().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u'): c 
            for c in df.columns
        }
        
        # Buscar dinámicamente cuál columna corresponde a cada dato necesario
        def buscar_columna(lista_palabras_clave):
            for norm_c, orig_c in cols_normalizadas.items():
                if all(p in norm_c for p in lista_palabras_clave):
                    return orig_c
            return None

        col_origen = buscar_columna(['de', 'almacen']) or buscar_columna(['origen'])
        col_destino = buscar_columna(['codigo', 'almacen']) if col_origen != buscar_columna(['codigo', 'almacen']) else buscar_columna(['destino'])
        if not col_destino:
            # Búsqueda de respaldo para destino si se confunde con origen
            for c in df.columns:
                if "código de almacén" in c.lower() and c != col_origen:
                    col_destino = c

        col_fecha = buscar_columna(['fecha', 'vencimiento']) or buscar_columna(['fecha'])
        col_doc = buscar_columna(['numero', 'documento']) or buscar_columna(['documento'])
        col_art = buscar_columna(['numero', 'articulo']) or buscar_columna(['articulo'])
        col_desc = buscar_columna(['descripcion'])
        col_cant = buscar_columna(['cantidad'])
        col_aten = buscar_columna(['atendida'])
        col_pend = buscar_columna(['pendiente'])

        final_df = pd.DataFrame()
        
        # Asignar datos de manera segura sin tumbar la app si falta alguno
        final_df['numero_documento'] = df[col_doc] if col_doc else "S/N"
        final_df['fecha_vencimiento'] = df[col_fecha] if col_fecha else ""
        final_df['de_codigo_almacen'] = df[col_origen] if col_origen else "Principal"
        final_df['codigo_almacen'] = df[col_destino] if col_destino else "Destino"
        final_df['numero_articulo'] = df[col_art] if col_art else "S/C"
        final_df['descripcion_articulo'] = df[col_desc] if col_desc else "Sin Descripción"
        
        # Tratamiento estricto de números
        final_df['cantidad'] = df[col_cant].apply(clean_numeric_string) if col_cant else "0"
        final_df['cantidad_atendida'] = df[col_aten].apply(clean_numeric_string) if col_aten else "0"
        final_df['cantidad_pendiente'] = df[col_pend].apply(clean_numeric_string) if col_pend else "0"
        
        for num_col in ['cantidad', 'cantidad_atendida', 'cantidad_pendiente']:
            final_df[num_col] = pd.to_numeric(final_df[num_col], errors='coerce').fillna(0.0)
            
        # Limpiar formatos de almacén
        for alm_col in ['de_codigo_almacen', 'codigo_almacen']:
            final_df[alm_col] = final_df[alm_col].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
        final_df['fecha_vencimiento'] = pd.to_datetime(final_df['fecha_vencimiento'], errors='coerce').dt.date
        
        return final_df
    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
        return None

if gsheet_url:
    df_raw = load_data(gsheet_url)
    
    if df_raw is not None and not df_raw.empty:
        st.sidebar.header("🔍 Filtros de Búsqueda")
        
        usar_filtro_fecha = st.sidebar.checkbox("Filtrar por Rango de Fechas", value=False)
        dates_valid = df_raw['fecha_vencimiento'].dropna()
        min_date = dates_valid.min() if not dates_valid.empty else datetime.today().date()
        max_date = dates_valid.max() if not dates_valid.empty else datetime.today().date()
        
        if usar_filtro_fecha:
            date_range = st.sidebar.date_input("Rango de fechas:", value=(min_date, max_date))
            
        almacenes_origen = sorted(list(set([x for x in df_raw['de_codigo_almacen'].unique() if x])))
        selected_origen = st.sidebar.multiselect("De código de almacén:", almacenes_origen, default=almacenes_origen)
        
        almacenes_destino = sorted(list(set([x for x in df_raw['codigo_almacen'].unique() if x])))
        selected_destino = st.sidebar.multiselect("Código de almacén (Destino):", almacenes_destino, default=almacenes_destino)
        
        search_query = st.sidebar.text_input("Buscar por Artículo o Descripción:").strip().lower()
        
        # Filtrado de datos
        df_filtered = df_raw.copy()
        
        if usar_filtro_fecha and len(date_range) == 2:
            df_filtered = df_filtered[(df_filtered['fecha_vencimiento'] >= date_range[0]) & (df_filtered['fecha_vencimiento'] <= date_range[1])]
            
        if selected_origen:
            df_filtered = df_filtered[df_filtered['de_codigo_almacen'].isin(selected_origen)]
        if selected_destino:
            df_filtered = df_filtered[df_filtered['codigo_almacen'].isin(selected_destino)]
            
        if search_query:
            cond_art = df_filtered['numero_articulo'].astype(str).str.lower().str.contains(search_query)
            cond_desc = df_filtered['descripcion_articulo'].astype(str).str.lower().str.contains(search_query)
            df_filtered = df_filtered[cond_art | cond_desc]
            
        # Tabla limpia para mostrar
        df_display = df_filtered[[
            'numero_documento', 'fecha_vencimiento', 'numero_articulo', 
            'descripcion_articulo', 'cantidad', 'cantidad_atendida', 'cantidad_pendiente'
        ]].rename(columns={
            'numero_documento': 'Número de documento',
            'fecha_vencimiento': 'Fecha de vencimiento',
            'numero_articulo': 'Número de artículo',
            'descripcion_articulo': 'Descripción del artículo',
            'cantidad': 'Cantidad',
            'cantidad_atendida': 'CantidadAtendida',
            'cantidad_pendiente': 'CantidadPendiente'
        })
        
        # Bloque de indicadores (KPIs)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("Total Documentos", f"{df_filtered['numero_documento'].nunique()} uds")
        with kpi2:
            st.metric("Suma Cantidad", f"{df_filtered['cantidad'].sum():,.2f}")
        with kpi3:
            st.metric("Suma Atendida", f"{df_filtered['cantidad_atendida'].sum():,.2f}")
        with kpi4:
            st.metric("Suma Pendiente", f"{df_filtered['cantidad_pendiente'].sum():,.2f}")
            
        st.write("---")
        st.subheader(f"📊 Registros Filtrados ({len(df_display)} filas)")
        st.dataframe(df_display, width="stretch", hide_index=True)
        
        st.write("---")
        st.subheader("📈 Análisis Gráfico de Carga")
        g1, g2 = st.columns(2)
        
        with g1:
            if not df_filtered.empty:
                fig_almacen = px.bar(
                    df_filtered.groupby('de_codigo_almacen')[['cantidad', 'cantidad_atendida']].sum().reset_index(),
                    x='de_codigo_almacen', y=['cantidad', 'cantidad_atendida'], barmode='group',
                    title='Volumen por Almacén de Origen', color_discrete_sequence=['#1E3A8A', '#10B981']
                )
                st.plotly_chart(fig_almacen, use_container_width=True)
                
        with g2:
            if not df_filtered.empty:
                top_articles = df_filtered.groupby('descripcion_articulo')['cantidad'].sum().nlargest(10).reset_index()
                fig_articles = px.bar(
                    top_articles, y='descripcion_articulo', x='cantidad', orientation='h',
                    title='Top 10 Artículos Más Solicitados', color_discrete_sequence=['#3B82F6']
                )
                fig_articles.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_articles, use_container_width=True)
    else:
        st.warning("El archivo conectado está vacío o la estructura no devolvió registros.")
else:
    st.info("💡 Por favor, ingresa tu enlace de Google Sheets publicado como CSV en la barra lateral.")
