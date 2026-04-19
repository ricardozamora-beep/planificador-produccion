import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador Heredia", page_icon="🏭", layout="wide")

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, h_lj, h_v):
    fin = h_lj if dt.weekday() <= 3 else h_v
    return dt.replace(hour=fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, feriados, h_ini, h_lj, h_v):
    while True:
        if dt.weekday() >= 5 or dt.strftime("%Y-%m-%d") in feriados:
            dt = (dt + timedelta(days=1)).replace(hour=h_ini, minute=0, second=0)
            continue
        fin = h_lj if dt.weekday() <= 3 else h_v
        if dt.hour >= fin:
            dt = (dt + timedelta(days=1)).replace(hour=h_ini, minute=0, second=0)
            continue
        if dt.hour < h_ini:
            dt = dt.replace(hour=h_ini, minute=0, second=0)
        return dt

# --- MANEJO DE ESTADO (PERSISTENCIA) ---
if 'lista_pedidos' not in st.session_state:
    st.session_state.lista_pedidos = []

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_ini = st.sidebar.number_input("Hora Inicio Turno", 0, 23, 7)
h_lj = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_v = st.sidebar.number_input("Salida Viernes", 0, 23, 15)
feriados_input = st.sidebar.date_input("Días Feriados", [])
feriados = [d.strftime("%Y-%m-%d") for d in feriados_input]

# --- CUERPO PRINCIPAL ---
st.title("🏭 Planificador de Producción Estable")

file_cat = st.file_uploader("1. Sube el Catálogo de Productos", type=["xlsx"])

if file_cat:
    # --- CAMBIO 1: Fecha de inicio se introduce después de subir el catálogo ---
    st.divider()
    fecha_inicio_plan = st.date_input("📅 Fecha de inicio de producción", datetime.now())
    
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    catalogo = df_cat.drop_duplicates(subset=['Código']).set_index('Código').to_dict('index')

    st.divider()
    
    # --- FORMULARIO DE INGRESO ---
    st.subheader("➕ Agregar Nuevo Pedido")
    with st.form("nuevo_pedido", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        cod_input = col1.text_input("Código de Material")
        
        # --- CAMBIO 2: Botones de cantidad aumentan/disminuyen 500 kg ---
        cant_input = col2.number_input("Cantidad (Kg)", min_value=0.0, step=500.0)
        
        set_input = col3.number_input("Setup (Horas)", min_value=0.0, step=0.5)
        
        submit = st.form_submit_button("Agregar a la lista")
        
        if submit:
            if cod_input.strip() in catalogo:
                nuevo_item = {
                    "Orden": len(st.session_state.lista_pedidos) + 1,
                    "Código": cod_input.strip(),
                    "Cantidad": cant_input,
                    "Setup": set_input
                }
                st.session_state.lista_pedidos.append(nuevo_item)
                st.success(f"Producto {cod_input} agregado.")
            else:
                st.error("❌ El código no existe en el catálogo.")

    # --- LISTA DE PEDIDOS ACTUALES ---
    if st.session_state.lista_pedidos:
        st.divider()
        st.subheader("📋 Pedidos en Cola")
        df_pedidos = pd.DataFrame(st.session_state.lista_pedidos)
        st.table(df_pedidos)

        if st.button("🗑️ Borrar toda la lista", type="primary"):
            st.session_state.lista_pedidos = []
            st.rerun()

        # --- CÁLCULO DEL CRONOGRAMA ---
        st.divider()
        st.subheader("📅 Cronograma Resultante")
        
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_ini)
        plan_final = []
        dias_es = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mie", "Thu": "Jue", "Fri": "Vie", "Sat": "Sab", "Sun": "Dom"}

        for p in st.session_state.lista_pedidos:
            info = catalogo[p['Código']]
            tasa_kgh = float(info['Tasa']) * 1000
            
            # Cálculo Setup
            rem_s = float(p['Setup'])
            while rem_s > 0:
                tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                espacio = (obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600
                cons = min(rem_s, espacio)
                tiempo_actual += timedelta(hours=cons); rem_s -= cons
            
            inicio_prod = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
            
            # Cálculo Producción
            rem_c = float(p['Cantidad'])
            while rem_c > 0.001:
                tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                cap_kg = ((obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                prod_kg = min(rem_c, cap_kg)
                tiempo_actual += timedelta(hours=prod_kg / tasa_kgh if tasa_kgh > 0 else 0); rem_c -= prod_kg
            
            def f_fecha(dt):
                dia = dias_es.get(dt.strftime('%a'), dt.strftime('%a'))
                return dt.strftime(f'{dia} %d/%m/%y %I:%M %p')

            plan_final.append({
                "ORDEN": p['Orden'],
                "CÓDIGO": p['Código'],
                "PRODUCTO": info['Producto'],
                "INICIO": f_fecha(inicio_prod),
                "FIN": f_fecha(tiempo_actual)
            })

        df_final = pd.DataFrame(plan_final)
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # Descarga
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, sheet_name='Plan', index=False)
        st.download_button("📥 Descargar Plan Excel", data=output.getvalue(), file_name="Plan_Produccion.xlsx")

else:
    st.info("👋 Sube el catálogo para comenzar a agregar pedidos.")
