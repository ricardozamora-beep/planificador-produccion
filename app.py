import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

st.set_page_config(page_title="Planificador Heredia", page_icon="🏭", layout="wide")

# --- LÓGICA DE TIEMPO ---
def obtener_fin_turno(dt, h_lun_jue, h_vie):
    fin = h_lun_jue if dt.weekday() <= 3 else h_vie
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

# --- ESTADO ---
if 'pedidos' not in st.session_state:
    st.session_state.pedidos = pd.DataFrame(columns=["Orden", "Código", "Cantidad", "Setup"])

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuración")
h_ini = st.sidebar.number_input("Inicio Turno", 0, 23, 7)
h_lj = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_v = st.sidebar.number_input("Salida Vie", 0, 23, 15)
feriados = [d.strftime("%Y-%m-%d") for d in st.sidebar.date_input("Feriados", [])]

# --- CUERPO ---
st.title("🏭 Planificador de Producción")
file_cat = st.file_uploader("Subir Catálogo", type=["xlsx"])

if file_cat:
    cat = pd.read_excel(file_cat).drop_duplicates(subset=['Código']).set_index('Código').to_dict('index')

    st.subheader("➕ Agregar Pedido")
    with st.form("add", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        cod = c1.text_input("Código")
        cant = c2.number_input("Kg", min_value=0.0)
        setu = c3.number_input("Setup (h)", min_value=0.0)
        if st.form_submit_button("Agregar"):
            if cod in cat:
                nueva_fila = pd.DataFrame([{"Orden": len(st.session_state.pedidos)+1, "Código": cod, "Cantidad": cant, "Setup": setu}])
                st.session_state.pedidos = pd.concat([st.session_state.pedidos, nueva_fila], ignore_index=True)
            else: st.error("Código no existe")

    if not st.session_state.pedidos.empty:
        st.subheader("📝 Editar Pedidos (Reordena cambiando el número en 'Orden')")
        st.session_state.pedidos = st.data_editor(st.session_state.pedidos.sort_values("Orden"), num_rows="dynamic", use_container_width=True)
        
        if st.button("🗑️ Borrar toda la tabla", type="primary"):
            st.session_state.pedidos = pd.DataFrame(columns=["Orden", "Código", "Cantidad", "Setup"])
            st.rerun()

        st.divider()
        fecha_start = st.date_input("Fecha Inicio", datetime.now())
        
        # --- CÁLCULO ---
        tiempo = datetime.combine(fecha_start, datetime.min.time()).replace(hour=h_ini)
        res = []
        for _, p in st.session_state.pedidos.sort_values("Orden").iterrows():
            info = cat[str(p['Código'])]
            tasa = float(info['Tasa']) * 1000
            
            # Setup
            rem_s = float(p['Setup'])
            while rem_s > 0:
                tiempo = saltar_no_laborales(tiempo, feriados, h_ini, h_lj, h_v)
                esp = (obtener_fin_turno(tiempo, h_lj, h_v) - tiempo).total_seconds()/3600
                cons = min(rem_s, esp)
                tiempo += timedelta(hours=cons); rem_s -= cons
            
            ini = saltar_no_laborales(tiempo, feriados, h_ini, h_lj, h_v)
            
            # Prod
            rem_c = float(p['Cantidad'])
            while rem_c > 0.001:
                tiempo = saltar_no_laborales(tiempo, feriados, h_ini, h_lj, h_v)
                cap = ((obtener_fin_turno(tiempo, h_lj, h_v) - tiempo).total_seconds()/3600) * tasa
                prod = min(rem_c, cap)
                tiempo += timedelta(hours=prod/tasa); rem_c -= prod
            
            res.append({"CÓDIGO": p['Código'], "PRODUCTO": info['Producto'], "INICIO": ini.strftime('%d/%m %H:%M'), "FIN": tiempo.strftime('%d/%m %H:%M')})

        st.table(pd.DataFrame(res))
