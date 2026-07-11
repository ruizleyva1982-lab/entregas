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
    .metric-box { padding: 15px; background-color: #F3F4F6; border-radius: 10px; text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# Encabezado Principal
st.markdown('<div class="main-title">📦 Dashboard de Solicitudes de Traslado (SAP B1)</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Monitoreo en tiempo real de inventario regular, intermedios y materias primas en tránsito.</div>', unsafe_allow_html=True)

# URL de Google Sheets en formato CSV (reemplaza con tu enlace publicado)
# Para pruebas, el usuario puede pegar su propio enlace en la barra lateral
st.sidebar.header("🔗 Configuración de Datos")
gsheet_url = st.sidebar.text_input(
    "Enlace de Google Sheets (CSV publicado):",
    placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv"
)

# Función para cargar datos con caché para alta velocidad
@st.cache_data(ttl=60)  # Se actualiza cada 60 segundos si cambias la data
def load_data(url):
    try:
        df = pd.read_csv(url)
        # Limpieza y conversión de tipos de datos
        df['Fecha de vencimiento'] = pd.to_datetime(df['Fecha de vencimiento'], errors='coerce').dt.date
        df['De código de almacén'] = df['De código de almacén'].astype(str).str.replace(r'\.0$', '', regex=True)
        df['Código de almacén'] = df['Código de almacén'].astype(str).str.replace(r'\.0$', '', regex=True)
        df['Número de documento'] = df['Número de documento'].astype(str)
        df['Número de artículo'] = df['Número de artículo'].astype(str)
        
        # Llenar nulos en cantidades numéricas
        df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(0)
        df['CantidadAtendida'] = pd.to_numeric(df['CantidadAtendida'], errors='coerce').fillna(0)
        df['CantidadPendiente'] = pd.to_numeric(df['CantidadPendiente'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return None

# Validar si se ha ingresado una URL
if gsheet_url:
    df_raw = load_data(gsheet_url)
    
    if df_raw is not None:
        # ==================== BLOQUE DE FILTROS EN LA BARRA LATERAL ====================
        st.sidebar.header("🔍 Filtros de Búsqueda")
        
        # 1. Filtro de Fechas (Fecha de Vencimiento)
        min_date = df_raw['Fecha de vencimiento'].min() if not df_raw['Fecha de vencimiento'].dropna().empty else datetime.today().date()
        max_date = df_raw['Fecha de vencimiento'].max() if not df_raw['Fecha de vencimiento'].dropna().empty else datetime.today().date()
        
        date_range = st.sidebar.date_input(
            "Fecha de vencimiento (Rango):",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        
        # 2. Filtros de Almacenes (Multiselect)
        almacenes_origen = sorted(df_raw['De código de almacén'].unique())
        selected_origen = st.sidebar.multiselect("De código de almacén:", almacenes_origen, default=almacenes_origen)
        
        almacenes_destino = sorted(df_raw['Código de almacén'].unique())
        selected_destino = st.sidebar.multiselect("Código de almacén (Destino):", almacenes_destino, default=almacenes_destino)
        
        # 3. Filtro por Artículo o Descripción (Texto libre)
        search_query = st.sidebar.text_input("Buscar por Código o Descripción de Artículo:").strip().lower()
        
        # ==================== APLICACIÓN DE FILTROS ====================
        df_filtered = df_raw.copy()
        
        # Filtrar fechas
        if len(date_range) == 2:
            start_date, end_date = date_range
            df_filtered = df_filtered[(df_filtered['Fecha de vencimiento'] >= start_date) & (df_filtered['Fecha de vencimiento'] <= end_date)]
            
        # Filtrar almacenes
        df_filtered = df_filtered[df_filtered['De código de almacén'].isin(selected_origen)]
        df_filtered = df_filtered[df_filtered['Código de almacén'].isin(selected_destino)]
        
        # Filtrar por texto (Código o Descripción)
        if search_query:
            df_filtered = df_filtered[
                df_filtered['Número de artículo'].str.lower().str.contains(search_query) |
                df_filtered['Descripción del artículo'].str.lower().str.contains(search_query)
            ]
            
        # ==================== SECCIÓN DE VISTA / MÉTRICAS ====================
        # Columnas solicitadas específicas para la tabla final
        target_columns = [
            'Número de documento', 'Fecha de vencimiento', 'Número de artículo', 
            'Descripción del artículo', 'Cantidad', 'CantidadAtendida', 'CantidadPendiente'
        ]
        
        # Aseguramos que existan todas las columnas antes de mostrar
        df_display = df_filtered[[col for col in target_columns if col in df_filtered.columns]]
        
        # Fila de KPIs rápidos
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("Total Solicitudes", f"{df_display['Número de documento'].nunique()} uds")
        with kpi2:
            st.metric("Suma Cantidad Solicitada", f"{df_display['Cantidad'].sum():,.2f}")
        with kpi3:
            st.metric("Suma Cantidad Atendida", f"{df_display['CantidadAtendida'].sum():,.2f}", delta_color="normal")
        with kpi4:
            st.metric("Suma Cantidad Pendiente", f"{df_display['CantidadPendiente'].sum():,.2f}", delta=f"-{df_display['CantidadPendiente'].sum():,.2f}", delta_color="inverse")
            
        st.write("---")
        
        # ==================== TABLA PRINCIPAL DE DATOS ====================
        st.subheader(f"📊 Registros Filtrados ({len(df_display)} filas)")
        
        # Mostrar tabla interactiva con estilos de números integrados en Streamlit
        st.dataframe(
            df_display,
            column_config={
                "Número de documento": st.column_config.TextColumn("N° Documento"),
                "Fecha de vencimiento": st.column_config.DateColumn("F. Vencimiento", format="YYYY-MM-DD"),
                "Número de artículo": st.column_config.TextColumn("Código Artículo"),
                "Descripción del artículo": st.column_config.TextColumn("Descripción"),
                "Cantidad": st.column_config.NumberColumn("Cant. Solicitada", format="%.2f"),
                "CantidadAtendida": st.column_config.NumberColumn("Cant. Atendida", format="%.2f"),
                "CantidadPendiente": st.column_config.NumberColumn("Cant. Pendiente", format="%.2f"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # ==================== GRÁFICOS COMPLEMENTARIOS (¡Monstruosa!) ====================
        st.write("---")
        st.subheader("📈 Análisis de Carga por Almacén y Artículo")
        
        g1, g2 = st.columns(2)
        
        with g1:
            if not df_filtered.empty and 'De código de almacén' in df_filtered.columns:
                fig_almacen = px.bar(
                    df_filtered.groupby('De código de almacén')[['Cantidad', 'CantidadAtendida']].sum().reset_index(),
                    x='De código de almacén',
                    y=['Cantidad', 'CantidadAtendida'],
                    barmode='group',
                    title='Volumen de Traslado por Almacén de Origen',
                    labels={'value': 'Kilos / Unidades', 'De código de almacén': 'Almacén Origen'},
                    color_discrete_sequence=['#1E3A8A', '#10B981']
                )
                st.plotly_chart(fig_almacen, use_container_width=True)
                
        with g2:
            if not df_display.empty:
                top_articles = df_display.groupby('Descripción del artículo')['Cantidad'].sum().nlargest(10).reset_index()
                fig_articles = px.bar(
                    top_articles,
                    y='Descripción del artículo',
                    x='Cantidad',
                    orientation='h',
                    title='Top 10 Artículos Más Solicitados',
                    labels={'Cantidad': 'Total Solicitado', 'Descripción del artículo': 'Artículo'},
                    color_discrete_sequence=['#3B82F6']
                )
                fig_articles.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_articles, use_container_width=True)
                
    else:
        st.warning("La estructura del archivo cargado no es válida o está vacía.")
else:
    st.info("💡 Por favor, ingresa el enlace CSV de tu Google Sheet publicado en la barra lateral para empezar a visualizar los datos.")
