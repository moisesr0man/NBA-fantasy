import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from nba_api.live.nba.endpoints import scoreboard
from datetime import datetime
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams

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
# --- BORRA EL BLOQUE "with tab1:" VIEJO Y PON ESTE ---

with tab1:
    if usuario == "Selecciona tu nombre...":
        st.warning("⚠️ Selecciona tu nombre en la izquierda para poder votar.")
    else:
        st.write(f"Hola **{usuario}**, vamos a ver tus pendientes:")
        
        # 1. Descargamos los votos que ya existen en la nube para no repetir
        registros_existentes = hoja_votos.get_all_records()
        votos_previos_usuario = {} # Diccionario para guardar {game_id: equipo_votado}
        
        if registros_existentes:
            df_existente = pd.DataFrame(registros_existentes)
            # Filtramos solo lo que ha votado ESTE usuario
            if 'usuario' in df_existente.columns and 'game_id' in df_existente.columns:
                df_user = df_existente[df_existente['usuario'] == usuario]
                # Llenamos el diccionario: Clave=ID del juego, Valor=Equipo
                for index, row in df_user.iterrows():
                    votos_previos_usuario[str(row['game_id'])] = row['ganador_elegido']

        # 2. Traemos los juegos de hoy
        games = obtener_partidos_hoy()
        
        if not games:
            st.info("No hay partidos programados para hoy en la NBA.")
        else:
            with st.form("form_votos"):
                mis_votos = {}
                hay_algo_que_votar = False
                
                for game in games:
                    home = game['homeTeam']['teamName']
                    away = game['awayTeam']['teamName']
                    gid = game['gameId']
                    
                    st.write("---")
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.caption(f"{away} (Visita) vs {home} (Casa)")
                        
                        # --- LÓGICA ANTI-DUPLICADOS ---
                        # Si el ID del juego ya está en su historial:
                        if str(gid) in votos_previos_usuario:
                            eleccion_pasada = votos_previos_usuario[str(gid)]
                            st.success(f"✅ Ya votaste por: **{eleccion_pasada}**")
                        else:
                            # Si no ha votado, mostramos los botones
                            sel = st.radio("¿Quién gana?", [away, home], key=gid, index=None, horizontal=True)
                            if sel:
                                mis_votos[gid] = {"matchup": f"{away} vs {home}", "seleccion": sel}
                                hay_algo_que_votar = True

                st.write("---")
                
                # Solo mostramos el botón de enviar si hay votos nuevos
                if hay_algo_que_votar:
                    if st.form_submit_button("🚀 Enviar Mis Predicciones"):
                        fecha = datetime.now().strftime("%Y-%m-%d")
                        rows = [[fecha, usuario, v['matchup'], v['seleccion'], k] for k, v in mis_votos.items()]
                        hoja_votos.append_rows(rows)
                        st.success("¡Votos guardados! (Si recargas la página verás que ya se bloquearon)")
                        # Forzamos recarga para que se bloqueen los botones visualmente
                        st.cache_data.clear()
                else:
                    st.info("Ya votaste en todos los partidos disponibles o no has seleccionado nada nuevo.")
                    st.form_submit_button("Actualizar", disabled=True)
# --- LÓGICA PESTAÑA 2: RESULTADOS ---

# --- REEMPLAZA TU SECCIÓN "with tab2:" COMPLETA CON ESTO ---

with tab2:
    st.header("Ranking Global")
    
    if st.button("🔄 Calcular Puntajes Actuales"):
        with st.spinner("Consultando la base de datos histórica de la NBA..."):
            
            # 1. Preparamos el "Traductor" de equipos (ID -> Nombre corto)
            # Esto es necesario porque la API de stats usa IDs (1610612747) y tú guardaste nombres ("Lakers")
            nba_teams = teams.get_teams()
            team_map = {str(t['id']): t['nickname'] for t in nba_teams} # Ejemplo: {'1610612...': 'Lakers'}
            
            # 2. Bajamos los votos de tu Google Sheet
            todos_los_datos = hoja_votos.get_all_values()
            
            if len(todos_los_datos) < 2:
                st.warning("⚠️ No hay suficientes datos para calcular. ¡Vota primero!")
            else:
                # Creamos el DataFrame
                encabezados = todos_los_datos[0]
                filas = todos_los_datos[1:]
                df = pd.DataFrame(filas, columns=encabezados)
                
                # Limpiamos nombres de columnas
                df.columns = df.columns.str.strip().str.lower()
                
                # Verificamos fechas únicas
                if 'fecha' not in df.columns:
                    st.error("Error: No encuentro la columna 'fecha' en tu Excel.")
                    st.stop()

                fechas_unicas = df['fecha'].unique()
                ganadores_reales = {} # {game_id: 'Lakers'}
                
                # Barra de progreso
                bar = st.progress(0)
                
                # 3. Loop para consultar cada fecha en la API de ESTADÍSTICAS
                for i, fecha_str in enumerate(fechas_unicas):
                    if not fecha_str: continue
                    
                    try:
                        # Usamos ScoreboardV2 que SÍ acepta fechas pasadas
                        # header=... es para evitar bloqueos de la API
                        sb = scoreboardv2.ScoreboardV2(game_date=fecha_str, timeout=30)
                        
                        # Obtenemos los puntajes línea por línea
                        line_score = sb.line_score.get_data_frame()
                        
                        if not line_score.empty:
                            # La API devuelve una fila por equipo. Agrupamos por GAME_ID para ver quién ganó.
                            # Columnas clave: GAME_ID, TEAM_ID, PTS
                            
                            # Lista de Game IDs en ese día
                            games_ids = line_score['GAME_ID'].unique()
                            
                            for gid in games_ids:
                                # Filtramos los 2 equipos de ese juego
                                juego = line_score[line_score['GAME_ID'] == gid]
                                # Buscamos el que tenga más puntos (max PTS)
                                ganador = juego.loc[juego['PTS'].idxmax()]
                                
                                # Traducimos ID del ganador a Nombre (ej: 1610612747 -> Lakers)
                                team_id_str = str(ganador['TEAM_ID'])
                                if team_id_str in team_map:
                                    nombre_ganador = team_map[team_id_str]
                                    ganadores_reales[str(gid)] = nombre_ganador
                                    
                    except Exception as e:
                        print(f"Error procesando fecha {fecha_str}: {e}")
                    
                    bar.progress((i + 1) / len(fechas_unicas))
                
                # 4. Comparación Final
                if not ganadores_reales:
                    st.info("No encontré resultados oficiales para las fechas de tus votos. ¿Quizás los partidos no han terminado?")
                else:
                    def verificar_ganador(row):
                        gid = str(row.get('game_id', '')).strip()
                        voto = str(row.get('ganador_elegido', '')).strip()
                        
                        # Comparamos si el ID del juego existe y si el nombre coincide
                        if gid in ganadores_reales:
                            real = ganadores_reales[gid]
                            if real == voto:
                                return 1
                        return 0

                    df['acierto'] = df.apply(verificar_ganador, axis=1)
                    
                    # Tabla de posiciones
                    ranking = df.groupby('usuario')['acierto'].sum().reset_index().sort_values('acierto', ascending=False)
                    
                    st.success("¡Cálculo completado exitosamente!")
                    st.dataframe(
                        ranking, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "usuario": "Jugador",
                            "acierto": st.column_config.NumberColumn("Aciertos", format="%d 🎯")
                        }
                    )
                    
                    if not ranking.empty:
                        lider = ranking.iloc[0]
                        st.metric("👑 Ganador Actual", lider['usuario'], f"{lider['acierto']} Puntos")
