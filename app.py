import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Solicitudes de Traslado SAP BO", layout="wide")
st.title("📦 Solicitudes de Traslado SAP BO")
st.markdown("---")

# URL correcta (copia la que aparece en la ventana de publicación)
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWnV4CeIsd5d-OCORyKxWx11WAC1XHYSJH74oCgauw6Cc4dc_rWY-BpleK079_6_7bhDcK_PxfotVF/pubhtml"

@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        # Intentar con diferentes separadores y manejo de líneas malas
        for sep in [',', ';']:
            try:
                df = pd.read_csv(
                    StringIO(response.text),
                    sep=sep,
                    encoding='utf-8',
                    on_bad_lines='skip',
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
                    StringIO(response.text),
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
    # Los nombres reales de las columnas en el archivo (con codificación extraña)
    # Usamos los nombres exactos que aparecen en la lista de columnas disponibles
    col_documento = "NÃºmero de documento"
    col_fecha_venc = "Fecha de vencimiento"
    col_articulo = "NÃºmero de artÃ­culo"
    col_descripcion = "DescripciÃ³n del artÃ­culo"
    col_cantidad = "Cantidad"
    col_cantidad_atendida = "CantidadAtendida"
    col_cantidad_pendiente = "CantidadPendiente"
    col_de_almacen = "De cÃ³digo de almacÃ©n"
    col_almacen = "CÃ³digo de almacÃ©n"
    
    # Verificar que todas existan
    columnas_requeridas = [
        col_documento, col_fecha_venc, col_articulo, col_descripcion,
        col_cantidad, col_cantidad_atendida, col_cantidad_pendiente
    ]
    faltantes = [col for col in columnas_requeridas if col not in df.columns]
    if faltantes:
        st.error(f"Faltan columnas: {faltantes}")
        st.write("Columnas disponibles:", df.columns.tolist())
        st.stop()
    
    # Renombrar a nombres limpios
    df_clean = df.rename(columns={
        col_documento: "Número de documento",
        col_fecha_venc: "Fecha de vencimiento",
        col_articulo: "Número de artículo",
        col_descripcion: "Descripción del artículo",
        col_cantidad: "Cantidad",
        col_cantidad_atendida: "CantidadAtendida",
        col_cantidad_pendiente: "CantidadPendiente",
        col_de_almacen: "De código de almacén",
        col_almacen: "Código de almacén"
    })
    
    # Convertir fechas (formato DD/MM/YYYY)
    df_clean["Fecha de vencimiento"] = pd.to_datetime(
        df_clean["Fecha de vencimiento"],
        format='%d/%m/%Y',
        errors='coerce'
    )
    
    # Convertir cantidades a numérico
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
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
    df_filtrado = df_clean.copy()
    
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
    
    # Mostrar SOLO las 7 columnas deseadas
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
    
elif df is not None and df.empty:
    st.warning("El archivo está vacío. Verifica que tenga datos.")
else:
    st.error("No se pudo cargar el archivo. Verifica la URL.")
