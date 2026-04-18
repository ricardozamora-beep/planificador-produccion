import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador en Tiempo Real - Heredia", page_icon="⏱️", layout="wide")

# --- INICIALIZACIÓN DE ESTADO ---
if 'lista_pedidos' not in st.session_state:
    st.session_state.lista_pedidos = []

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, hora_lun_jue, hora_vie):
    # Lunes (0) a Jueves (3)
    hora_fin = hora_lun_jue if dt.weekday() <= 3 else hora_vie
    return dt.replace(hour=hora_fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, lista_feriados, hora_inicio_turno, hora_lun_jue, hora_vie):
    while True:
        dia_semana = dt.weekday()
        fecha_actual_str = dt.strftime("%Y-%m-%d")
        
        # Fines de semana o feriados
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
        return dt

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_inicio = st.sidebar.number_input("Hora Inicio Turno", 0, 23, 7)
h_lun_jue = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_vie = st.sidebar.number_input("Salida Viernes", 0, 23, 15)
feriados_sel = st.sidebar.date_input("Días Feriados / Cierres", value=[])
lista_feriados = [d.strftime("%Y-%m-%d") for d in feriados_sel]

# --- CUERPO PRINCIPAL ---
st.title("⏱️ Planificador de Producción en Tiempo Real")

# 1. Cargar el Catálogo
file_cat = st.file_uploader("1. Sube el Catálogo de Productos", type=["xlsx"])

if file_cat:
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    # Evitar el error de duplicados
    df_cat_limpio = df_cat.drop_duplicates(subset=['Código'])
    catalogo = df_cat_limpio.set_index('Código').to_dict('index')

    st.divider()
    
    # 2. Fecha de Inicio Global
    fecha_inicio_plan = st.date_input("📅 ¿Cuándo inicia la producción?", datetime.now())

    # 3. Formulario de Ingreso
    st.subheader("➕ Añadir Producto al Plan")
    with st.form("formulario_pedido", clear_on_submit=True):
        col_id, col_cant, col_set = st.columns([2, 1, 1])
        codigo_input = col_id.text_input("Código de Producto")
        cantidad_input = col_cant.number_input("Cantidad (kg)", min_value=0.0, step=100.0)
        setup_input = col_set.number_input("Setup (horas)", min_value=0.0, step=0.5)
        
        btn_agregar = st.form_submit_button("Añadir al Cronograma")
        
        if btn_agregar:
            if codigo_input in catalogo:
                st.session_state.lista_pedidos.append({
                    "Código": codigo_input,
                    "Producto": catalogo[codigo_input]['Producto'],
                    "Cantidad": cantidad_input,
                    "Setup": setup_input
                })
            else:
                st.error("El código no existe en el catálogo.")

    # 4. Cálculo y Muestra del Plan Automático
    if st.session_state.lista_pedidos:
        st.divider()
        st.subheader("📋 Cronograma de Producción Actualizado")
        
        # Reiniciar reloj para el cálculo completo cada vez que cambia la lista
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_inicio)
        plan_calculado = []

        for pedido in st.session_state.lista_pedidos:
            info = catalogo[pedido['Código']]
            tasa_kgh = float(info['Tasa']) * 1000
            peso_pedido = pedido['Cantidad']
            peso_u = float(info.get('Peso unitario', 0))
            setup = pedido['Setup']
            
            # Procesar Setup
            if setup > 0:
                rem_s = setup
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
            
            inicio_prod = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
            
            # Procesar Producción
            rem_c = peso_pedido
            while rem_c > 0.001:
                tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                cap_kg = ((obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                prod_kg = min(rem_c, cap_kg)
                tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
            
            plan_calculado.append({
                "CÓDIGO": pedido['Código'],
                "PRODUCTO": pedido['Producto'],
                "KG": peso_pedido,
                "UNIDADES": round(peso_pedido / peso_u, 0) if peso_u > 0 else 0,
                "INICIO": inicio_prod.strftime('%d/%m/%y %I:%M %p'),
                "FIN": tiempo_actual.strftime('%d/%m/%y %I:%M %p')
            })

        df_plan = pd.DataFrame(plan_calculado)
        st.dataframe(df_plan, use_container_width=True)

        col_acciones1, col_acciones2 = st.columns([1, 5])
        with col_acciones1:
            if st.button("🗑️ Borrar Todo"):
                st.session_state.lista_pedidos = []
                st.rerun()
        
        with col_acciones2:
            # Exportación rápida
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_plan.to_excel(writer, sheet_name='Plan', index=False)
            st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Cronograma_Produccion.xlsx")

else:
    st.info("👋 Por favor, sube el Catálogo para comenzar a ingresar pedidos.")
