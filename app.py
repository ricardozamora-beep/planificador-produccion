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
        cant_input = col2.number_input("Cantidad (Kg)", min_value=0.0, step=500.0)
        set_input = col3.number_input("Setup (Horas)", min_value=0.0, step=0.5)
        submit = st.form_submit_button("Agregar a la lista")
        
        if submit:
            cod_limpio = cod_input.strip()
            if cod_limpio in catalogo:
                nueva_fila = pd.DataFrame([{"Orden": len(st.session_state.lista_pedidos) + 1, "Código": cod_limpio, "Cantidad": cant_input, "Setup": set_input}])
                st.session_state.lista_pedidos = pd.concat([st.session_state.lista_pedidos, nueva_fila], ignore_index=True)
                st.success(f"Producto {cod_limpio} agregado.")
            else:
                st.error("❌ El código no existe en el catálogo.")

    if not st.session_state.lista_pedidos.empty:
        st.divider()
        st.subheader("📋 Pedidos en Cola (Editables)")
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

        st.divider()
        st.subheader("📅 Cronograma Resultante")
        
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_ini)
        plan_final = []
        produccion_diaria_raw = []
        dias_es = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mie", "Thu": "Jue", "Fri": "Vie", "Sat": "Sab", "Sun": "Dom"}

        df_para_calc = st.session_state.lista_pedidos.sort_values("Orden")

        for _, p in df_para_calc.iterrows():
            cod_str = str(p['Código']).strip()
            if cod_str in catalogo:
                info = catalogo[cod_str]
                tasa_kgh = float(info['Tasa']) * 1000
                
                try:
                    rem_s = float(p['Setup']) if pd.notna(p['Setup']) else 0.0
                    rem_c = float(p['Cantidad']) if pd.notna(p['Cantidad']) else 0.0
                except:
                    rem_s, rem_c = 0.0, 0.0

                # Lógica de Setup
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
                
                inicio_prod = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                
                # Lógica de Producción
                while rem_c > 0.001:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    fin_turno = obtener_fin_turno(tiempo_actual, h_lj, h_v)
                    cap_horas = (fin_turno - tiempo_actual).total_seconds()/3600
                    cap_kg = cap_horas * tasa_kgh
                    prod_kg = min(rem_c, cap_kg)
                    
                    # Registro para el resumen diario por fecha
                    produccion_diaria_raw.append({
                        "Fecha_Sort": tiempo_actual.date(), # Para ordenar cronológicamente
                        "Día": dias_es.get(tiempo_actual.strftime('%a'), tiempo_actual.strftime('%a')),
                        "Fecha": tiempo_actual.strftime('%d/%m/%y'),
                        "Kg": prod_kg
                    })
                    
                    tiempo_actual += timedelta(hours=prod_kg / tasa_kgh if tasa_kgh > 0 else 0); rem_c -= prod_kg
                
                def f_fecha(dt):
                    dia = dias_es.get(dt.strftime('%a'), dt.strftime('%a'))
                    return dt.strftime(f'{dia} %d/%m/%y %I:%M %p')

                plan_final.append({
                    "ORDEN": int(p['Orden']),
                    "CÓDIGO": cod_str,
                    "PRODUCTO": info['Producto'],
                    "CANTIDAD (Kg)": p['Cantidad'],
                    "INICIO": f_fecha(inicio_prod),
                    "FIN": f_fecha(tiempo_actual)
                })

        if plan_final:
            df_cronograma = pd.DataFrame(plan_final)
            st.dataframe(df_cronograma, use_container_width=True, hide_index=True)
            
            # --- GENERACIÓN DE EXCEL ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                
                # Formatos
                fmt_header = workbook.add_format({'bold': True, 'bg_color': '#1F4E78', 'font_color': 'white', 'border': 1, 'align': 'center'})
                fmt_cell = workbook.add_format({'border': 1, 'align': 'left'})
                fmt_num = workbook.add_format({'border': 1, 'num_format': '#,##0', 'align': 'right'})

                # HOJA 1: Detalle por Pedido
                df_cronograma.to_excel(writer, sheet_name='Plan de Producción', index=False)
                ws1 = writer.sheets['Plan de Producción']
                for col_num, value in enumerate(df_cronograma.columns.values):
                    ws1.write(0, col_num, value, fmt_header)
                    ws1.set_column(col_num, col_num, 22, fmt_cell)

                # HOJA 2: Totales Diarios (Resumen Simplificado)
                if produccion_diaria_raw:
                    df_raw = pd.DataFrame(produccion_diaria_raw)
                    # Sumar todos los kg por día
                    df_diario_total = df_raw.groupby(["Fecha_Sort", "Día", "Fecha"])["Kg"].sum().reset_index()
                    df_diario_total = df_diario_total.sort_values("Fecha_Sort").drop(columns=["Fecha_Sort"])
                    df_diario_total.columns = ["Día", "Fecha", "Total Producido (Kg)"]
                    
                    df_diario_total.to_excel(writer, sheet_name='Totales Diarios', index=False)
                    ws2 = writer.sheets['Totales Diarios']
                    for col_num, value in enumerate(df_diario_total.columns.values):
                        ws2.write(0, col_num, value, fmt_header)
                        ws2.set_column(col_num, col_num, 20, fmt_cell)
                    ws2.set_column(2, 2, 25, fmt_num) # Columna Total Kg

            st.download_button(
                label="📥 Descargar Reporte Profesional",
                data=output.getvalue(),
                file_name="Reporte_Produccion_Heredia.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("👋 Sube el catálogo para comenzar.")
