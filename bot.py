import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import datetime
import urllib.request
import json
import openai

# Librerías oficiales de Google Auth & OAuthlib
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Configurar logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "9006959123:AAGwA8wE4vhFi8-tv0bUvFAnnLnfyi2ZCXQ"
DATA_FILE = "data.json"

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "635273911604-g1s9ce1rgq8stugbjorlhv2nj08dtnpm.apps.googleusercontent.com")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "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")
REDIRECT_URI = "https://soy-organizabot.onrender.com/oauth2callback"

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

openai.api_key = os.environ.get("OPENAI_API_KEY")

# Diccionarios de estado y flujos OAuth temporales
oauth_pending_states = {}
oauth_flows = {}

# --- PERSISTENCIA DE DATOS (JSON) ---
def cargar_datos():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error al leer {DATA_FILE}: {e}")
    return {}

def guardar_datos(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error al escribir {DATA_FILE}: {e}")

user_data_store = cargar_datos()
reunion_temp_state = {}

# --- UTILIDADES OAUTH POR USUARIO ---
def obtener_credenciales_usuario(user_id):
    str_id = str(user_id)
    if str_id in user_data_store and "google_creds" in user_data_store[str_id]:
        c_info = user_data_store[str_id]["google_creds"]
        return Credentials(
            token=c_info.get('token'),
            refresh_token=c_info.get('refresh_token'),
            token_uri=c_info.get('token_uri'),
            client_id=c_info.get('client_id'),
            client_secret=c_info.get('client_secret'),
            scopes=c_info.get('scopes')
        )
    return None

# --- SERVIDOR WEB SECUNDARIO (RENDER) CON SOPORTE OAUTH CALLBACK ---
class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        if path == "/oauth2callback":
            code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0]

            if not code or not state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Error: Falta codigo o estado de autenticacion.")
                return

            try:
                user_id = str(state)
                flow = oauth_flows.get(user_id)
                
                if not flow:
                    client_config = {
                        "web": {
                            "client_id": CLIENT_ID,
                            "client_secret": CLIENT_SECRET,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": [REDIRECT_URI]
                        }
                    }
                    flow = Flow.from_client_config(client_config, scopes=SCOPES)
                    flow.redirect_uri = REDIRECT_URI

                flow.fetch_token(code=code)
                credentials = flow.credentials

                if user_id not in user_data_store:
                    user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "notas": []}
                
                user_data_store[user_id]["google_creds"] = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                guardar_datos(user_data_store)

                self.send_response(200)
                self.end_headers()
                html_respuesta = "<html><body style='font-family:sans-serif; text-align:center; padding-top:50px;'><h2>¡Cuenta de Google vinculada con éxito!</h2><p>Ya podés cerrar esta pestaña y volver a Telegram con @SoyOrganizabot.</p></body></html>"
                self.wfile.write(html_respuesta.encode('utf-8'))
            except Exception as e:
                print(f"Error procesando token OAuth: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error interno al autenticar: {e}".encode('utf-8'))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"@SoyOrganizabot activo y con OAuth individual operativo!")

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), OAuthHandler)
        print(f"Servidor web escuchando en el puerto {port}")
        server.serve_forever()
    except Exception as e:
        print(f"Error crítico en servidor web: {e}")

# --- FUNCIONES DE CALENDAR Y TASKS POR USUARIO ---
def sincronizar_google_calendar_crear(user_id, titulo, fecha, hora, detalle):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return False

        cal_service = build('calendar', 'v3', credentials=creds)
        start_datetime = f"{fecha}T{hora}:00-03:00"
        h_fin = int(hora.split(":")[0]) + 1
        end_datetime = f"{fecha}T{h_fin:02d}:{hora.split(':')[1]}:00-03:00"

        event = {
            'summary': titulo,
            'description': detalle,
            'start': {'dateTime': start_datetime, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end': {'dateTime': end_datetime, 'timeZone': 'America/Argentina/Buenos_Aires'},
        }
        cal_service.events().insert(calendarId='primary', body=event).execute()
        return True
    except Exception as e:
        print(f"Error creando evento en Google Calendar: {e}")
        return False

def agregar_google_task(user_id, titulo_tarea):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return False

        tasks_service = build('tasks', 'v1', credentials=creds)
        task = {'title': titulo_tarea}
        tasks_service.tasks().insert(tasklist='@default', body=task).execute()
        return True
    except Exception as e:
        print(f"Error agregando tarea a Google Tasks: {e}")
        return False

# --- COMANDOS PRINCIPALES ---
async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    str_id = str(user.id)
    if str_id not in user_data_store:
        user_data_store[str_id] = {
            "tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []
        }
        guardar_datos(user_data_store)

    keyboard = [
        [InlineKeyboardButton("🔗 Vincular mi Google (Calendar y Tasks)", callback_data="vincular_google")],
        [InlineKeyboardButton("⚙️ Configurar reportes", callback_data="menu_config")]
    ]
    
    texto_bienvenida = (
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Ahora cada usuario puede vincular su propia cuenta de Google de forma independiente.\n\n"
        "• /conectar - Vincular tu Google Calendar y Google Tasks\n"
        "• /agenda_reunion - Agendar evento en tu calendario\n"
        "• /nueva_tarea - Agregar tarea a tu Google Tasks\n"
        "• /tareas - Ver tareas pendientes\n"
        "• /nota [texto] - Guardar una nota rápida\n"
        "• /lista_notas - Ver tus notas guardadas\n\n"
        "Hacé clic en el botón para conectar tu cuenta:"
    )
    await update.message.reply_text(texto_bienvenida, reply_markup=InlineKeyboardMarkup(keyboard))

async def conectar_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    authorization_url, state_val = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=str(user_id),
        prompt='consent'
    )
    
    oauth_flows[str(user_id)] = flow

    keyboard = [[InlineKeyboardButton("🌐 Conectar con Google", url=authorization_url)]]
    texto = "🔐 **Vincular cuenta de Google**\n\nHacé clic en el siguiente botón para autorizar al bot a gestionar *tu* calendario y tus tareas de forma segura:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def agenda_reunion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not obtener_credenciales_usuario(user_id):
        keyboard = [[InlineKeyboardButton("🔗 Vincular Google ahora", callback_data="vincular_google_menu")]]
        texto = "⚠️ Para agendar reuniones en tu Google Calendar personal, primero necesitás vincular tu cuenta usando /conectar."
        if update.callback_query:
            await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    reunion_temp_state[user_id] = {"step": "tipo"}
    keyboard = [
        [InlineKeyboardButton("🏢 Presencial", callback_data="reunion_presencial"),
         InlineKeyboardButton("💻 Virtual", callback_data="reunion_virtual")]
    ]
    text_msg = "📅 Asistente de Reuniones (Google Calendar):\n\n¿Qué tipo de reunión querés agendar?"
    if update.callback_query:
        await update.callback_query.edit_message_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    texto_tarea = " ".join(context.args)
    if not texto_tarea:
        await update.message.reply_text("⚠️ Escribí la tarea. Ejemplo: /nueva_tarea Comprar pan")
        return

    if not obtener_credenciales_usuario(user_id):
        await update.message.reply_text("⚠️ Primero tenés que vincular tu cuenta de Google usando /conectar para sincronizar con Google Tasks.")
        return

    if str_id not in user_data_store:
        user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []}
    
    user_data_store[str_id]["tareas"].append(texto_tarea)
    guardar_datos(user_data_store)
    
    agregar_google_task(user_id, texto_tarea)
    await update.message.reply_text(f"➕ Tarea agregada y sincronizada en tu Google Tasks: *{texto_tarea}*", parse_mode="Markdown")

async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    if str_id not in user_data_store or not user_data_store[str_id]["tareas"]:
        texto = "📝 No tenés tareas pendientes."
    else:
        t_list = user_data_store[str_id]["tareas"]
        texto = "📝 Tus tareas pendientes:\n\n" + "".join([f"• {t}\n" for t in t_list])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto)
    else:
        await update.message.reply_text(texto)

async def nota_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    texto_nota = " ".join(context.args)
    if not texto_nota:
        await update.message.reply_text("⚠️ Escribí la nota. Ejemplo: /nota Comprar regalo")
        return
    if str_id not in user_data_store:
        user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []}
    if "notas" not in user_data_store[str_id]:
        user_data_store[str_id]["notas"] = []
    user_data_store[str_id]["notas"].append(texto_nota)
    guardar_datos(user_data_store)
    await update.message.reply_text(f"📌 Nota guardada: {texto_nota}")

async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    if str_id not in user_data_store or not user_data_store[str_id].get("notas"):
        texto = "📂 No tenés notas guardadas."
    else:
        notas_list = user_data_store[str_id]["notas"]
        texto = "📂 Tus notas guardadas:\n\n" + "".join([f"• {n}\n" for n in notas_list])
    if update.callback_query:
        await update.callback_query.edit_message_text(texto)
    else:
        await update.message.reply_text(texto)

# --- MANEJADOR DE BOTONES ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data in ["vincular_google", "vincular_google_menu"]:
        await conectar_google(update, context)
        return
    elif data == "menu_agenda":
        await agenda_reunion(update, context)
        return
    elif data == "menu_tareas":
        await tareas(update, context)
        return

    if data in ["reunion_presencial", "reunion_virtual"]:
        tipo = "Presencial" if data == "reunion_presencial" else "Virtual"
        reunion_temp_state[user_id] = {"tipo": tipo, "step": "titulo"}
        await query.edit_message_text(f"📝 Reunión {tipo}\n\nEscribí el título de la reunión:")
    elif data.startswith("anio_"):
        reunion_temp_state[user_id]["anio"] = data.replace("anio_", "")
        reunion_temp_state[user_id]["step"] = "mes"
        keyboard = [
            [InlineKeyboardButton("Enero", callback_data="mes_01"), InlineKeyboardButton("Febrero", callback_data="mes_02"), InlineKeyboardButton("Marzo", callback_data="mes_03")],
            [InlineKeyboardButton("Abril", callback_data="mes_04"), InlineKeyboardButton("Mayo", callback_data="mes_05"), InlineKeyboardButton("Junio", callback_data="mes_06")],
            [InlineKeyboardButton("Julio", callback_data="mes_07"), InlineKeyboardButton("Agosto", callback_data="mes_08"), InlineKeyboardButton("Septiembre", callback_data="mes_09")],
            [InlineKeyboardButton("Octubre", callback_data="mes_10"), InlineKeyboardButton("Noviembre", callback_data="mes_11"), InlineKeyboardButton("Diciembre", callback_data="mes_12")],
        ]
        await query.edit_message_text("📅 Seleccioná el mes:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("mes_"):
        reunion_temp_state[user_id]["mes"] = data.replace("mes_", "")
        reunion_temp_state[user_id]["step"] = "dia"
        dias_buttons = []
        fila = []
        for d in range(1, 32):
            fila.append(InlineKeyboardButton(str(d), callback_data=f"dia_{d:02d}"))
            if len(fila) == 7:
                dias_buttons.append(fila)
                fila = []
        if fila:
            dias_buttons.append(fila)
        await query.edit_message_text("📅 Seleccioná el día:", reply_markup=InlineKeyboardMarkup(dias_buttons))
    elif data.startswith("dia_"):
        reunion_temp_state[user_id]["dia"] = data.replace("dia_", "")
        reunion_temp_state[user_id]["step"] = "hora_reunion"
        horas_reunion = []
        fila = []
        for h in range(24):
            fila.append(InlineKeyboardButton(f"{h:02d} hs", callback_data=f"reu_h_{h:02d}"))
            if len(fila) == 6:
                horas_reunion.append(fila)
                fila = []
        if fila:
            horas_reunion.append(fila)
        await query.edit_message_text("⏰ Seleccioná la hora:", reply_markup=InlineKeyboardMarkup(horas_reunion))
    elif data.startswith("reu_h_"):
        reunion_temp_state[user_id]["reu_h"] = data.replace("reu_h_", "")
        reunion_temp_state[user_id]["step"] = "minuto_reunion"
        min_reunion = [
            [InlineKeyboardButton("00 min", callback_data="reu_m_00"), InlineKeyboardButton("15 min", callback_data="reu_m_15")],
            [InlineKeyboardButton("30 min", callback_data="reu_m_30"), InlineKeyboardButton("45 min", callback_data="reu_m_45")]
        ]
        await query.edit_message_text("⏰ Seleccioná los minutos:", reply_markup=InlineKeyboardMarkup(min_reunion))
    elif data.startswith("reu_m_"):
        m_str = data.replace("reu_m_", "")
        state = reunion_temp_state.get(user_id, {})
        h_str = state.get("reu_h", "09")
        state["hora"] = f"{h_str}:{m_str}"
        state["step"] = "lugar_link"
        tipo = state.get("tipo")
        prompt_texto = "📍 Ingresá la dirección:" if tipo == "Presencial" else "💻 Ingresá el link de la reunión:"
        await query.edit_message_text(prompt_texto)

# --- MANEJADOR DE TEXTO Y AUDIOS ---
async def handle_voice_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)

    if update.message.voice:
        audio_path = f"voice_{user_id}.ogg"
        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            await voice_file.download_to_drive(audio_path)

            with open(audio_path, "rb") as audio:
                transcript = openai.Audio.transcribe("whisper-1", audio)
            
            texto_transcrito = transcript["text"] if isinstance(transcript, dict) else transcript.text
            if os.path.exists(audio_path):
                os.remove(audio_path)

            await update.message.reply_text(f"🎤 *Transcripción:* \"{texto_transcrito}\"", parse_mode="Markdown")
            
            if "tarea" in texto_transcrito.lower():
                nueva_t = texto_transcrito.lower().replace("tarea", "").strip()
                if str_id not in user_data_store:
                    user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []}
                user_data_store[str_id]["tareas"].append(nueva_t)
                guardar_datos(user_data_store)
                agregar_google_task(user_id, nueva_t)
                await update.message.reply_text(f"➕ Tarea agregada a tu Google Tasks por voz: *{nueva_t}*", parse_mode="Markdown")
            else:
                await update.message.reply_text("🤖 Audio procesado.")
        except Exception as e:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            print(f"Error audio: {e}")
            await update.message.reply_text("❌ Error al procesar audio.")
        return

    text = update.message.text
    if user_id in reunion_temp_state:
        state = reunion_temp_state[user_id]
        step = state.get("step")

        if step == "titulo":
            state["titulo"] = text
            state["step"] = "anio"
            keyboard = [
                [InlineKeyboardButton("2026", callback_data="anio_2026"), InlineKeyboardButton("2027", callback_data="anio_2027")]
            ]
            await update.message.reply_text("📅 Seleccioná el año:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif step == "lugar_link":
            ubicacion_o_link = text
            tipo = state.get("tipo")
            titulo = state.get("titulo")
            anio = state.get("anio")
            mes = state.get("mes")
            dia = state.get("dia")
            hora = state.get("hora")
            fecha_formateada = f"{anio}-{mes}-{dia}"

            if str_id not in user_data_store:
                user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []}
            
            detalle = f"[{tipo}] {titulo} | {fecha_formateada} | {hora} | {ubicacion_o_link}"
            user_data_store[str_id]["reuniones"].append(detalle)
            guardar_datos(user_data_store)

            sincronizar_google_calendar_crear(user_id, titulo, fecha_formateada, hora, ubicacion_o_link)
            del reunion_temp_state[user_id]

            await update.message.reply_text(
                f"✅ ¡Reunión agendada en **tu Google Calendar** personal!\n\n"
                f"📌 {titulo}\n📅 {fecha_formateada} a las {hora} hs\n📍 {ubicacion_o_link}"
            )
            return

def main():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler(["start", "iniciar"], iniciar))
    app.add_handler(CommandHandler("conectar", conectar_google))
    app.add_handler(CommandHandler(["agenda_reunion", "reuniones"], agenda_reunion))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))
    app.add_handler(CommandHandler("nota", nota_cmd))
    app.add_handler(CommandHandler("lista_notas", lista_notas))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.TEXT & ~filters.COMMAND, handle_voice_or_text))

    print("🚀 @SoyOrganizabot con OAuth individual por usuario en marcha!")
    app.run_polling()

if __name__ == '__main__':
    main()
