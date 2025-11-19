import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from nba_api.live.nba.endpoints import scoreboard
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="NBA ", page_icon="🏀")

# --- 1. CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource
def conectar_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Intenta buscar en los Secretos de Streamlit (Nube)
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Si no encuentra secretos, busca el archivo local (Tu PC)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
    client = gspread.authorize(creds)
    # Asegúrate que este nombre sea EXACTO al de tu hoja
    sheet = client.open("FANTASEX NBA").worksheet("votos")
    return sheet    
    # --- ¡OJO! CAMBIA ESTO POR EL NOMBRE DE TU ARCHIVO ---
    sheet = client.open("FANTASEX NBA").worksheet("votos")
    return sheet

try:
    hoja_votos = conectar_sheets()
except Exception as e:
    st.error(f"Error conectando a Google Sheets: {e}")
    st.stop()

# --- 2. CONEXIÓN A LA NBA (Live Data) ---
def obtener_partidos_hoy():
    try:
        board = scoreboard.ScoreBoard()
        games = board.games.get_dict()
        return games
    except Exception as e:
        return []

# --- 3. INTERFAZ DE USUARIO (FRONTEND) ---
st.title("🏀 FANTASEX")

usuario = st.sidebar.selectbox(
    "¿Quién está votando?", 
    ["Selecciona tu nombre...", "Moises", "Frank", "Gordic", "Kike"]
)

# --- AQUÍ ES DONDE SE DEFINEN LAS PESTAÑAS (TAB1 y TAB2) ---
tab1, tab2 = st.tabs(["🗳️ Vota", "🏆 Tabla de Posiciones"])

# --- LÓGICA PESTAÑA 1: VOTACIÓN ---
with tab1:
    if usuario == "Selecciona tu nombre...":
        st.warning("⚠️ Selecciona tu nombre en la izquierda.")
    else:
        st.write(f"Partidos de hoy para: **{usuario}**")
        games = obtener_partidos_hoy()
        
        if not games:
            st.info("No hay partidos programados para hoy.")
        else:
            with st.form("form_votos"):
                mis_votos = {}
                for game in games:
                    home = game['homeTeam']['teamName']
                    away = game['awayTeam']['teamName']
                    gid = game['gameId']
                    
                    st.write("---")
                    col1, col2, col3 = st.columns([1,2,1])
                    with col2:
                        st.caption(f"{away} vs {home}")
                        sel = st.radio("Ganador:", [away, home], key=gid, index=None, horizontal=True)
                    
                    if sel:
                        mis_votos[gid] = {"matchup": f"{away} vs {home}", "seleccion": sel}

                st.write("---")
                if st.form_submit_button("🚀 Enviar Predicciones"):
                    if len(mis_votos) < len(games):
                        st.error("¡Te faltan partidos!")
                    else:
                        fecha = datetime.now().strftime("%Y-%m-%d")
                        rows = [[fecha, usuario, v['matchup'], v['seleccion'], k] for k, v in mis_votos.items()]
                        hoja_votos.append_rows(rows)
                        st.success("¡Votos guardados!")
                        st.balloons()

# --- LÓGICA PESTAÑA 2: RESULTADOS ---
with tab2:
    st.header("Ranking Global")
    
    if st.button("🔄 Calcular Puntajes Actuales"):
        with st.spinner("Consultando resultados finales a la NBA..."):
            datos_sheet = hoja_votos.get_all_records()
            
            if not datos_sheet:
                st.warning("Aún no hay votos en la hoja.")
            else:
                df = pd.DataFrame(datos_sheet)
                fechas = df['fecha'].unique()
                ganadores_reales = {}
                
                # Barra de progreso
                bar = st.progress(0)
                for i, f in enumerate(fechas):
                    try:
                        sb = scoreboard.ScoreBoard(game_date=f)
                        for g in sb.games.get_dict():
                            if "Final" in g['gameStatusText']:
                                h_s = g['homeTeam']['score']
                                a_s = g['awayTeam']['score']
                                win = g['homeTeam']['teamName'] if h_s > a_s else g['awayTeam']['teamName']
                                ganadores_reales[g['gameId']] = win
                    except: pass
                    bar.progress((i+1)/len(fechas))
                
                # Calcular aciertos
                # Compara game_id y ganador elegido
                df['acierto'] = df.apply(
                    lambda x: 1 if str(x['game_id']) in ganadores_reales and ganadores_reales[str(x['game_id'])] == x['ganador_elegido'] else 0, 
                    axis=1
                )
                
                ranking = df.groupby('usuario')['acierto'].sum().reset_index().sort_values('acierto', ascending=False)
                
                st.success("¡Tabla actualizada!")
                st.dataframe(ranking, use_container_width=True, hide_index=True)
                
                if not ranking.empty:
                    lider = ranking.iloc[0]

                    st.metric("👑 Líder", lider['usuario'], f"{lider['acierto']} Puntos")
