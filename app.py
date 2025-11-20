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

with tab2:
    st.header("Ranking Global")
    
    if st.button("🔄 Calcular Puntajes Actuales"):
        with st.spinner("Consultando resultados finales a la NBA..."):
            
            # --- CAMBIO CLAVE: Usamos get_all_values en lugar de get_all_records ---
            # Esto trae TODO como una matriz simple, mucho más seguro.
            todos_los_datos = hoja_votos.get_all_values()
            
            # Verificamos si hay suficientes datos (Mínimo debe haber encabezados + 1 voto)
            if len(todos_los_datos) < 2:
                st.warning("⚠️ Tu hoja de cálculo parece vacía (solo tiene encabezados o nada). ¡Vota primero!")
                # DEBUG: Mostramos qué ve Python
                st.write("Lo que veo en tu hoja es:", todos_los_datos)
            
            else:
                # Construimos el DataFrame manualmente para asegurar que las columnas se llamen bien
                encabezados = todos_los_datos[0]  # La primera fila son los títulos
                filas = todos_los_datos[1:]       # El resto son datos
                
                df = pd.DataFrame(filas, columns=encabezados)
                
                # --- LIMPIEZA DE COLUMNAS (Por si pusiste "Fecha " con espacio o "FECHA") ---
                df.columns = df.columns.str.strip().str.lower()
                
                # DEBUG: Si falla, esto nos dirá qué columnas detectó realmente
                if 'fecha' not in df.columns:
                    st.error("🚨 Error Crítico: No encuentro la columna 'fecha'.")
                    st.write("Las columnas que detecté son:", df.columns.tolist())
                    st.stop()

                fechas = df['fecha'].unique()
                ganadores_reales = {}
                
                # Barra de progreso
                bar = st.progress(0)
                for i, f in enumerate(fechas):
                    # Saltamos filas vacías si las hubiera
                    if not f: continue 
                    
                    try:
                        sb = scoreboard.ScoreBoard(game_date=f)
                        for g in sb.games.get_dict():
                            if "Final" in g['gameStatusText']:
                                h_s = g['homeTeam']['score']
                                a_s = g['awayTeam']['score']
                                win = g['homeTeam']['teamName'] if h_s > a_s else g['awayTeam']['teamName']
                                # Convertimos gameId a string para asegurar compatibilidad
                                ganadores_reales[str(g['gameId'])] = win
                    except Exception as e:
                        st.warning(f"Error consultando fecha {f}: {e}")
                    
                    bar.progress((i+1)/len(fechas))
                
                # Calcular aciertos
                if not ganadores_reales:
                    st.info("No encontré partidos terminados ('Final') en esas fechas para comparar.")
                else:
                    # Función de comparación segura
                    def verificar_ganador(row):
                        gid = str(row.get('game_id', '')).strip()
                        voto = str(row.get('ganador_elegido', '')).strip()
                        
                        if gid in ganadores_reales and ganadores_reales[gid] == voto:
                            return 1
                        return 0

                    df['acierto'] = df.apply(verificar_ganador, axis=1)
                    
                    ranking = df.groupby('usuario')['acierto'].sum().reset_index().sort_values('acierto', ascending=False)
                    
                    st.success("¡Tabla actualizada!")
                    
                    st.dataframe(
                        ranking, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "usuario": "Jugador",
                            "acierto": st.column_config.NumberColumn("Puntos Totales", format="%d 🎯")
                        }
                    )
                    
                    if not ranking.empty:
                        lider = ranking.iloc[0]
                        st.metric("👑 Líder", lider['usuario'], f"{lider['acierto']} Puntos")
