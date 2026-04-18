import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador Interactivo - Heredia", page_icon="🏭", layout="wide")

# --- INICIALIZACIÓN DE LISTA DE PEDIDOS ---
if 'lista_pedidos' not in st.session_state:
    st.session_state.lista_pedidos = []

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, hora_lun_jue, hora_vie):
    hora_fin = hora_lun_jue if dt.weekday() <= 3 else hora_vie
    return dt.replace(hour=hora_fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, lista_feriados, hora_inicio_turno, hora_lun_jue, hora_vie):
    while True:
        dia_semana = dt.weekday()
        fecha_actual_str = dt.strftime("%Y-%m-%d")
        if dia_semana >= 5 or fecha_actual_str in lista_feriados:
            dt = (dt + timedelta(days=1)).replace(hour=hora_inicio_turno, minute=0, second=0)
            continue
        hora_salida = hora_lun_jue if dia_semana <= 3 else hora_vie
        if dt.hour >= hora_salida:
            dt = (dt + timedelta(days=1)).replace(hour=hora_inicio_turno, minute=0, second=0)
            continue
        if dt.hour < hora_inicio_turno:
            dt = dt.replace(hour=hora_inicio_turno, minute=0, second=0)
        return dt

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_inicio = st.sidebar.number_input("Hora Inicio (7am)", 0, 23, 7)
h_lun_jue = st.sidebar.number_input("Salida L-J (5pm)", 0, 23, 17)
h_vie = st.sidebar.number_input("Salida Vie (3pm)", 0, 23, 15)
feriados_sel = st.sidebar.date_input("Feriados", value=[])
lista_feriados = [d.strftime("%Y-%m-%d") for d in feriados_sel]

# --- CUERPO PRINCIPAL ---
st.title("🏭 Gestión de Producción en Vivo")

# 1. Cargar el Catálogo (Esencial para validar códigos)
file_cat = st.file_uploader("Primero, sube el Catálogo de Productos", type=["xlsx"])

if file_cat:
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    catalogo = df_cat.set_index('Código').to_dict('index')

    st.divider()
    
    # 2. Formulario de Ingreso Manual
    st.subheader("➕ Agregar Nuevo Pedido")
    with st.form("formulario_pedido"):
        col_id, col_cant, col_set = st.columns([2, 1, 1])
        
        codigo_input = col_id.text_input("Código de Producto")
        cantidad_input = col_cant.number_input("Cantidad (kg)", min_value=0.0, step=100.0)
        setup_input = col_set.number_input("Setup (horas)", min_value=0.0, step=0.5)
        
        # Mostrar el nombre del producto en tiempo real si el código existe
        nombre_prod = "Código no encontrado"
        if codigo_input in catalogo:
            nombre_prod = catalogo[codigo_input]['Producto']
            st.info(f"Producto detectado: **{nombre_prod}**")
        
        btn_agregar = st.form_submit_button("Agregar a la lista")
        
        if btn_agregar:
            if codigo_input in catalogo:
                st.session_state.lista_pedidos.append({
                    "Código": codigo_input,
                    "Producto": nombre_prod,
                    "Cantidad": cantidad_input,
                    "Setup": setup_input
                })
            else:
                st.error("El código ingresado no existe en el catálogo.")

    # 3. Mostrar lista actual y procesar
    if st.session_state.lista_pedidos:
        st.subheader("📋 Lista de Carga Actual")
        df_temporal = pd.DataFrame(st.session_state.lista_pedidos)
        st.table(df_temporal)
        
        if st.button("🗑️ Limpiar Lista"):
            st.session_state.lista_pedidos = []
            st.rerun()

        st.divider()
        
        # 4. Cálculo de Planificación
        fecha_inicio = st.date_input("Fecha Inicio Plan", datetime.now())
        if st.button("🚀 Generar Plan de Producción"):
            tiempo_actual = datetime.combine(fecha_inicio, datetime.min.time()).replace(hour=h_inicio)
            plan_prod, diario = [], {}
            
            for pedido in st.session_state.lista_pedidos:
                info = catalogo[pedido['Código']]
                tasa_kgh = float(info['Tasa']) * 1000
                peso_pedido = pedido['Cantidad']
                peso_u = float(info.get('Peso unitario', 0))
                setup = pedido['Setup']
                
                # Proceso de Setup
                if setup > 0:
                    rem_s = setup
                    while rem_s > 0:
                        tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                        espacio = (obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600
                        cons = min(rem_s, espacio)
                        tiempo_actual += timedelta(hours=cons); rem_s -= cons
                
                inicio_p = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                
                # Proceso de Producción
                rem_c = peso_pedido
                while rem_c > 0.001:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    f_hoy = tiempo_actual.strftime('%Y-%m-%d')
                    cap_kg = ((obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                    prod_kg = min(rem_c, cap_kg)
                    diario[f_hoy] = diario.get(f_hoy, 0) + prod_kg
                    tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
                
                plan_prod.append({
                    "CÓDIGO": pedido['Código'], "PRODUCTO": pedido['Producto'], "KG": peso_pedido,
                    "UNIDADES": round(peso_pedido / peso_u, 0) if peso_u > 0 else 0,
                    "INICIO": inicio_p.strftime('%d/%m/%y %H:%M'), "FIN": tiempo_actual.strftime('%d/%m/%y %H:%M')
                })

            # Mostrar Resultados
            df_final = pd.DataFrame(plan_prod)
            st.success("✅ Planificación completada.")
            
            fig = px.bar(pd.DataFrame(list(diario.items()), columns=['F', 'KG']), x='F', y='KG', title="Carga Diaria")
            st.plotly_chart(fig, use_container_width=True)
            
            # Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, sheet_name='Plan', index=False)
            
            st.download_button("📥 Descargar Reporte Final", data=output.getvalue(), file_name="Plan_Manual.xlsx")
            st.dataframe(df_final, use_container_width=True)

else:
    st.info("👋 Por favor, sube el archivo de catálogo para habilitar el ingreso manual.")
