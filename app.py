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

# --- MANEJO DE ESTADO ---
if 'lista_pedidos' not in st.session_state:
    st.session_state.lista_pedidos = pd.DataFrame(columns=["Orden", "Código", "Cantidad", "Setup"])

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
    # Selector de fecha después de subir el catálogo
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
        # Botones de cantidad aumentan/disminuyen 500 kg
        cant_input = col2.number_input("Cantidad (Kg)", min_value=0.0, step=500.0)
        set_input = col3.number_input("Setup (Horas)", min_value=0.0, step=0.5)
        
        submit = st.form_submit_button("Agregar a la lista")
        
        if submit:
            cod_limpio = cod_input.strip()
            if cod_limpio in catalogo:
                nueva_fila = pd.DataFrame([{
                    "Orden": len(st.session_state.lista_pedidos) + 1,
                    "Código": cod_limpio,
                    "Cantidad": cant_input,
                    "Setup": set_input
                }])
                st.session_state.lista_pedidos = pd.concat([st.session_state.lista_pedidos, nueva_fila], ignore_index=True)
                st.success(f"Producto {cod_limpio} agregado.")
            else:
                st.error("❌ El código no existe en el catálogo.")

    # --- TABLA DE PEDIDOS EDITABLE EN COLA ---
    if not st.session_state.lista_pedidos.empty:
        st.divider()
        st.subheader("📋 Pedidos en Cola (Editables)")
        st.info("💡 Haz clic en cualquier celda para corregir datos. El cronograma se actualizará solo.")
        
        # Editor para modificar lo que ya está en cola
        df_editado = st.data_editor(
            st.session_state.lista_pedidos,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Orden": st.column_config.NumberColumn("Orden", format="%d"),
                "Código": st.column_config.TextColumn("Código"),
                "Cantidad": st.column_config.NumberColumn("Kg", step=500.0),
                "Setup": st.column_config.NumberColumn("Setup (h)", step=0.5)
            },
            key="editor_cola"
        )
        st.session_state.lista_pedidos = df_editado

        if st.button("🗑️ Borrar toda la lista", type="primary"):
            st.session_state.lista_pedidos = pd.DataFrame(columns=["Orden", "Código", "Cantidad", "Setup"])
            st.rerun()

        # --- CÁLCULO DEL CRONOGRAMA ---
        st.divider()
        st.subheader("📅 Cronograma Resultante")
        
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_ini)
        plan_final = []
        dias_es = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mie", "Thu": "Jue", "Fri": "Vie", "Sat": "Sab", "Sun": "Dom"}

        # Respetar el orden definido por el usuario
        df_para_calc = st.session_state.lista_pedidos.sort_values("Orden")

        for _, p in df_para_calc.iterrows():
            cod_str = str(p['Código']).strip()
            if cod_str in catalogo:
                info = catalogo[cod_str]
                tasa_kgh = float(info['Tasa']) * 1000
                
                # Manejo de valores vacíos tras edición
                try:
                    rem_s = float(p['Setup']) if pd.notna(p['Setup']) else 0.0
                    rem_c = float(p['Cantidad']) if pd.notna(p['Cantidad']) else 0.0
                except:
                    rem_s, rem_c = 0.0, 0.0

                # Cálculo de tiempos de Setup
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
                
                inicio_prod = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                
                # Cálculo de tiempos de Producción
                while rem_c > 0.001:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    cap_kg = ((obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                    prod_kg = min(rem_c, cap_kg)
                    tiempo_actual += timedelta(hours=prod_kg / tasa_kgh if tasa_kgh > 0 else 0); rem_c -= prod_kg
                
                def f_fecha(dt):
                    dia = dias_es.get(dt.strftime('%a'), dt.strftime('%a'))
                    return dt.strftime(f'{dia} %d/%m/%y %I:%M %p')

                plan_final.append({
                    "ORDEN": int(p['Orden']) if pd.notna(p['Orden']) else 0,
                    "CÓDIGO": cod_str,
                    "PRODUCTO": info['Producto'],
                    "INICIO": f_fecha(inicio_prod),
                    "FIN": f_fecha(tiempo_actual)
                })

        if plan_final:
            df_cronograma = pd.DataFrame(plan_final)
            st.dataframe(df_cronograma, use_container_width=True, hide_index=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_cronograma.to_excel(writer, sheet_name='Plan', index=False)
            st.download_button("📥 Descargar Plan Excel", data=output.getvalue(), file_name="Plan_Produccion.xlsx")

else:
    st.info("👋 Por favor, sube el catálogo para comenzar a planificar.")
