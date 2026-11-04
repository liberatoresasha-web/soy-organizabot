import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import datetime
import json
import openai
from zoneinfo import ZoneInfo

# Librerías oficiales de Google Auth & OAuthlib
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "9006959123:AAGwA8wE4vhFi8-tv0bUvFAnnLnfyi2ZCXQ"
DATA_FILE = "data.json"

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "635273911604-g1s9ce1rgq8stugbjorlhv2nj08dtnpm.apps.googleusercontent.com")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "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")
REDIRECT_URI = "https://soy-organizabot.onrender.com/oauth2callback"

# Scopes ampliados para incluir Calendar, Tasks y Drive/Keep (archivos)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

openai.api_key = os.environ.get("OPENAI_API_KEY")

oauth_pending_states = {}
oauth_flows = {}
ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

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
recordatorio_temp_state = {}
nota_temp_state = {}
user_input_states = {}

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

# --- SERVIDOR WEB OAUTH ---
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
                    user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": {}, "recordatorios": [], "frecuentes": [], "notas": {}, "config": {"semana": "09:00", "fin_semana": "10:00"}}
                
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
                
                html_respuesta = f"""
                <html>
                    <body style='font-family:sans-serif; text-align:center; padding-top:50px; background-color:#f4f7f6;'>
                        <div style='background:white; max-width:500px; margin:0 auto; padding:30px; border-radius:10px; box-shadow:0px 4px 10px rgba(0,0,0,0.1);'>
                            <h2 style='color:#2b6cb0;'>¡Cuenta de Google vinculada con éxito! 🎉</h2>
                            <p style='color:#4a5568;'>Ya podés volver a Telegram para seguir utilizando el asistente.</p>
                            <a href='https://t.me/SoyOrganizabot?start=vinculado' style='display:inline-block; margin-top:20px; padding:12px 24px; background:#3182ce; color:white; text-decoration:none; border-radius:5px; font-weight:bold;'>Volver al Bot de Telegram</a>
                        </div>
                    </body>
                </html>
                """
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
        server.serve_forever()
    except Exception as e:
        print(f"Error crítico en servidor web: {e}")

# --- GOOGLE API HELPERS ---
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
        res = cal_service.events().insert(calendarId='primary', body=event).execute()
        return res.get('id')
    except Exception as e:
        print(f"Error creando evento en Google Calendar: {e}")
        return False

def obtener_listas_google_tasks(user_id):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return []
        tasks_service = build('tasks', 'v1', credentials=creds)
        results = tasks_service.tasklists().list(maxResults=10).execute()
        return results.get('items', [])
    except Exception as e:
        print(f"Error obteniendo listas de Tasks: {e}")
        return []

def agregar_google_task(user_id, titulo_tarea, tasklist_id='@default'):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return False
        tasks_service = build('tasks', 'v1', credentials=creds)
        task = {'title': titulo_tarea}
        tasks_service.tasks().insert(tasklist=tasklist_id, body=task).execute()
        return True
    except Exception as e:
        print(f"Error agregando tarea a Google Tasks: {e}")
        return False

def obtener_tareas_google(user_id, tasklist_id='@default'):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return []
        tasks_service = build('tasks', 'v1', credentials=creds)
        results = tasks_service.tasks().list(tasklist=tasklist_id, showCompleted=False).execute()
        return results.get('items', [])
    except Exception as e:
        print(f"Error listando tareas: {e}")
        return []

def completada_tarea_google(user_id, task_id, tasklist_id='@default'):
    try:
        creds = obtener_credenciales_usuario(user_id)
        if not creds:
            return False
        tasks_service = build('tasks', 'v1', credentials=creds)
        task = tasks_service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        task['status'] = 'completed'
        tasks_service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
        return True
    except Exception as e:
        print(f"Error completando tarea: {e}")
        return False

# --- MENÚS Y COMANDOS ---
async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    str_id = str(user.id)
    if str_id not in user_data_store:
        user_data_store[str_id] = {
            "tareas": [], "listas": {}, "reuniones": [], "acciones": {}, "recordatorios": [], "frecuentes": [], "notas": {},
            "config": {"semana": "09:00", "fin_semana": "10:00"}
        }
        guardar_datos(user_data_store)

    if context.args and "vinculado" in context.args:
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        await update.message.reply_text(
            "🎉 **¡Cuenta de Google vinculada con éxito!**\n\nYa tenés tu calendario y tareas sincronizados.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await configuracion_cmd(update, context)

async def menu_principal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 Tareas", callback_data="menu_tareas_listas")],
        [InlineKeyboardButton("➕ Nueva Tarea", callback_data="prompt_nueva_tarea")],
        [InlineKeyboardButton("⏰ Recordatorio", callback_data="menu_recordatorios")],
        [InlineKeyboardButton("⚡ Acción", callback_data="menu_accion")],
        [InlineKeyboardButton("📌 Notas", callback_data="menu_notas")],
        [InlineKeyboardButton("📅 Reuniones", callback_data="menu_reuniones_lista")],
        [InlineKeyboardButton("⚙️ Configuración de Horarios", callback_data="menu_config")],
        [InlineKeyboardButton("🔗 Vincular Google", callback_data="vincular_google")]
    ]
    texto = f"¡Hola, {user.first_name}! 🤖 Menú Principal de @SoyOrganizabot:\n\nSeleccioná una opción:"
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))

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
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=str(user_id),
        prompt='consent'
    )
    oauth_flows[str(user_id)] = flow

    keyboard = [
        [InlineKeyboardButton("🌐 Conectar con Google", url=authorization_url)],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    texto = "🔐 **Vincular cuenta de Google**\n\nHacé clic en el botón para autorizar al bot:"
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def configuracion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    if str_id not in user_data_store:
        user_data_store[str_id] = {"config": {"semana": "09:00", "fin_semana": "10:00"}}
        guardar_datos(user_data_store)
        
    config = user_data_store[str_id].get("config", {"semana": "09:00", "fin_semana": "10:00"})
    
    texto = (
        "⚙️ **Configuración de Reportes y Horarios**\n\n"
        f"• Horario de Lunes a Viernes: *{config.get('semana')} hs*\n"
        f"• Horario de Fin de Semana (Sábados y Domingos): *{config.get('fin_semana')} hs*\n\n"
        "Seleccioná qué horario querés modificar:"
    )
    keyboard = [
        [InlineKeyboardButton("🕒 Cambiar Lunes a Viernes", callback_data="cfg_semana"),
         InlineKeyboardButton("🕒 Cambiar Fin de Semana", callback_data="cfg_finde")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

async def accion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "⚡ **Panel de Acciones Cotidianas**\n\n"
        "Podés registrar o consultar hábitos cotidianos (ej. *cerré la puerta*, *tomé la pastilla*).\n\n"
        "Escribí directamente en el chat lo que hiciste o querés consultar:"
    )
    user_input_states[update.effective_user.id] = "esperando_accion"
    keyboard = [
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

# --- MENÚ DE NOTAS ---
async def notas_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "📌 **Gestión de Notas**\n\nSeleccioná una opción:"
    keyboard = [
        [InlineKeyboardButton("📁 Categoría de Notas (Listas)", callback_data="listar_categorias_notas")],
        [InlineKeyboardButton("➕ Nueva Lista de Notas", callback_data="crear_lista_notas")],
        [InlineKeyboardButton("📝 Agregar Nota", callback_data="prompt_agregar_nota")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

async def listar_categorias_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    listas_notas = user_data_store.get(str_id, {}).get("notas", {})

    if not listas_notas:
        texto = "📂 No tenés categorías o listas de notas guardadas."
    else:
        texto = "📁 **Tus Categorías de Notas:**\n\n"
        for categoria, items in listas_notas.items():
            texto += f"• **{categoria}** ({len(items)} notas)\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Volver", callback_data="menu_notas")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def nota_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await notas_menu(update, context)

async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await listar_categorias_notas(update, context)

# --- MENÚ DE RECORDATORIOS ---
async def recordatorio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "⏰ **Gestión de Recordatorios**\n\nSeleccioná una opción:"
    keyboard = [
        [InlineKeyboardButton("➕ Nuevo Recordatorio", callback_data="nuevo_recordatorio_flow")],
        [InlineKeyboardButton("📁 Recordatorios Guardados", callback_data="listar_recordatorios_guardados")],
        [InlineKeyboardButton("🔄 Recordatorios Frecuentes", callback_data="listar_recordatorios_frecuentes")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

async def listar_guardados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    recs = user_data_store.get(str_id, {}).get("recordatorios", [])

    if not recs:
        texto = "📂 No tenés recordatorios guardados."
    else:
        texto = "📁 **Tus Recordatorios Guardados:**\n\n"
        for r in recs:
            texto += f"• {r.get('texto')} — 📅 {r.get('fecha')} a las {r.get('hora')} hs\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def listar_frecuentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    freqs = user_data_store.get(str_id, {}).get("frecuentes", [])

    if not freqs:
        texto = "🔄 No tenés recordatorios frecuentes configurados."
    else:
        freqs_ordenados = sorted(freqs, key=lambda x: x.get('hora', '00:00'))
        texto = "🔄 **Tus Recordatorios Frecuentes:**\n\n"
        for f in freqs_ordenados:
            texto += f"• **{f.get('texto')}** — 🕒 {f.get('frecuencia')} a las {f.get('hora')} Hs\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def iniciar_flujo_recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    recordatorio_temp_state[user_id] = {"step": "texto"}
    texto = "⏰ **Asistente de Recordatorios**\n\nEscribí el texto de lo que querés que te recuerde:"
    keyboard = [
        [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def agenda_reunion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not obtener_credenciales_usuario(user_id):
        keyboard = [
            [InlineKeyboardButton("🔗 Vincular Google ahora", callback_data="vincular_google_menu")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        texto = "⚠️ Para agendar reuniones en tu Google Calendar personal, primero necesitás vincular tu cuenta usando /conectar."
        if update.callback_query:
            await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    reunion_temp_state[user_id] = {"step": "tipo"}
    keyboard = [
        [InlineKeyboardButton("🏢 Presencial", callback_data="reunion_presencial"),
         InlineKeyboardButton("💻 Virtual", callback_data="reunion_virtual")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
    ]
    text_msg = "📅 Asistente de Reuniones:\n\n¿Qué tipo de reunión querés agendar?"
    if update.callback_query:
        await update.callback_query.edit_message_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def listar_reuniones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    reuniones = user_data_store.get(str_id, {}).get("reuniones", [])

    if not reuniones:
        texto = "📂 No tenés reuniones agendadas."
        keyboard = [
            [InlineKeyboardButton("📅 Agendar nueva reunión", callback_data="menu_agenda")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
    else:
        texto = "📅 **Tus Reuniones Agendadas:**\n\n"
        keyboard = []
        for idx, r in enumerate(reuniones):
            texto += f"• {r.get('titulo')} ({r.get('fecha')} {r.get('hora')} hs)\n"
            keyboard.append([
                InlineKeyboardButton(f"✏️ Editar: {r.get('titulo')[:12]}", callback_data=f"edit_reu_{idx}"),
                InlineKeyboardButton(f"🗑️ Eliminar", callback_data=f"del_reu_{idx}")
            ])
        keyboard.append([InlineKeyboardButton("📅 Agendar nueva reunión", callback_data="menu_agenda")])
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
        markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_id = str(user_id)
    texto_tarea = " ".join(context.args)
    if not texto_tarea:
        await update.message.reply_text("⚠️ Escribí la tarea. Ejemplo: /nueva_tarea Comprar pan")
        return
    if not obtener_credenciales_usuario(user_id):
        await update.message.reply_text("⚠️ Primero vinculá tu cuenta usando /conectar.")
        return

    if str_id not in user_data_store:
        user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": {}, "recordatorios": [], "frecuentes": [], "notas": {}}
    user_data_store[str_id]["tareas"].append(texto_tarea)
    guardar_datos(user_data_store)
    agregar_google_task(user_id, texto_tarea)
    await update.message.reply_text(f"➕ Tarea agregada y sincronizada en tu Google Tasks: *{texto_tarea}*", parse_mode="Markdown")

async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not obtener_credenciales_usuario(user_id):
        texto = "⚠️ Necesitás vincular tu cuenta de Google con /conectar para ver tus listas de Google Tasks."
        keyboard = [
            [InlineKeyboardButton("🔗 Vincular Google", callback_data="vincular_google")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(texto, reply_markup=markup)
        else:
            await update.message.reply_text(texto, reply_markup=markup)
        return

    listas = obtener_listas_google_tasks(user_id)
    if not listas:
        texto = "📝 No se encontraron listas en tu Google Tasks."
        keyboard = [
            [InlineKeyboardButton("➕ Nueva Tarea", callback_data="prompt_nueva_tarea")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
    else:
        texto = "📝 **Tus Listas de Google Tasks:**\n\nSeleccioná una lista para ver sus tareas:"
        keyboard = []
        for lst in listas:
            keyboard.append([InlineKeyboardButton(f"📁 {lst.get('title')}", callback_data=f"ver_lista_{lst.get('id')}")])
        keyboard.append([InlineKeyboardButton("➕ Nueva Tarea", callback_data="prompt_nueva_tarea")])
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
        markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

async def completada_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not obtener_credenciales_usuario(user_id):
        await update.message.reply_text("⚠️ Tenés que vincular tu cuenta primero con /conectar.")
        return

    tareas_pendientes = obtener_tareas_google(user_id)
    if not tareas_pendientes:
        await update.message.reply_text("🎉 ¡No tenés tareas pendientes para completar!")
        return

    texto = "✅ **Seleccioná la tarea que completaste:**\n\n"
    keyboard = []
    for t in tareas_pendientes[:10]:
        keyboard.append([InlineKeyboardButton(f"✔️ {t.get('title')}", callback_data=f"comp_task_{t.get('id')}")])
    keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
    
    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- MANEJADOR DE BOTONES INTERACTIVOS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    str_id = str(user_id)

    if data == "menu_principal":
        await menu_principal_cmd(update, context)
        return
    elif data == "menu_accion":
        await accion_cmd(update, context)
        return
    elif data == "menu_recordatorios":
        await recordatorio_menu(update, context)
        return
    elif data == "menu_notas":
        await notas_menu(update, context)
        return
    elif data == "listar_categorias_notas":
        await listar_categorias_notas(update, context)
        return
    elif data == "crear_lista_notas":
        user_input_states[user_id] = "esperando_nombre_categoria_nota"
        keyboard = [
            [InlineKeyboardButton("⬅️ Volver", callback_data="menu_notas")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        await query.edit_message_text("📁 Escribí el nombre de la nueva categoría/lista de notas:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "prompt_agregar_nota":
        listas_n = user_data_store.get(str_id, {}).get("notas", {})
        if not listas_n:
            user_input_states[user_id] = "esperando_nombre_categoria_nota"
            keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
            await query.edit_message_text("⚠️ No tenés listas de notas. Escribí el nombre de la primera categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        keyboard = []
        for cat in listas_n.keys():
            keyboard.append([InlineKeyboardButton(f"📁 {cat}", callback_data=f"nota_cat_{cat}")])
        keyboard.append([InlineKeyboardButton("➕ Crear Nueva Lista", callback_data="crear_lista_notas")])
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_notas")])
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
        await query.edit_message_text("📌 Seleccioná a qué lista querés agregar la nota:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("nota_cat_"):
        cat_elegida = data.replace("nota_cat_", "")
        nota_temp_state[user_id] = {"categoria": cat_elegida}
        user_input_states[user_id] = "esperando_texto_nota"
        keyboard = [
            [InlineKeyboardButton("⬅️ Volver", callback_data="prompt_agregar_nota")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        await query.edit_message_text(f"✍️ Escribí el contenido de la nota para la lista **{cat_elegida}**:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    elif data == "nuevo_recordatorio_flow":
        await iniciar_flujo_recordatorio(update, context)
        return
    elif data == "listar_recordatorios_guardados":
        await listar_guardados(update, context)
        return
    elif data == "listar_recordatorios_frecuentes":
        await listar_frecuentes(update, context)
        return
    elif data in ["vincular_google", "vincular_google_menu"]:
        await conectar_google(update, context)
        return
    elif data == "menu_agenda":
        await agenda_reunion(update, context)
        return
    elif data == "menu_reuniones_lista":
        await listar_reuniones(update, context)
        return
    elif data == "menu_tareas_listas":
        await tareas(update, context)
        return
    elif data == "menu_config":
        await configuracion_cmd(update, context)
        return
    elif data == "cfg_semana":
        user_input_states[user_id] = "esperando_hora_semana"
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        await query.edit_message_text("🕒 Escribí el nuevo horario para Lunes a Viernes (ej: 08:30):", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "cfg_finde":
        user_input_states[user_id] = "esperando_hora_finde"
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        await query.edit_message_text("🕒 Escribí el nuevo horario para Fin de Semana (ej: 10:00):", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "prompt_nueva_tarea":
        user_input_states[user_id] = "esperando_texto_tarea"
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        await query.edit_message_text("✍️ Escribí el texto de tu nueva tarea directamente en el chat:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "crear_nueva_lista":
        user_input_states[user_id] = "esperando_nombre_lista"
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        await query.edit_message_text("📁 Escribí el nombre para la nueva lista de Google Tasks:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("ver_lista_"):
        list_id = data.replace("ver_lista_", "")
        t_list = obtener_tareas_google(user_id, tasklist_id=list_id)
        if not t_list:
            texto = "📁 Esta lista está vacía."
        else:
            texto = "📁 **Tareas en la lista:**\n\n" + "".join([f"• {t.get('title')}\n" for t in t_list])
        keyboard = [
            [InlineKeyboardButton("➕ Nueva Tarea", callback_data="prompt_nueva_tarea")],
            [InlineKeyboardButton("⬅️ Volver a listas", callback_data="menu_tareas_listas")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    elif data.startswith("comp_task_"):
        t_id = data.replace("comp_task_", "")
        success = completada_tarea_google(user_id, t_id)
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
        if success:
            await query.edit_message_text("✅ ¡Tarea marcada como completada con éxito!", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ Hubo un error al completar la tarea.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("del_reu_"):
        idx = int(data.replace("del_reu_", ""))
        if str_id in user_data_store and len(user_data_store[str_id]["reuniones"]) > idx:
            eliminada = user_data_store[str_id]["reuniones"].pop(idx)
            guardar_datos(user_data_store)
            keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
            await query.edit_message_text(f"🗑️ Reunión eliminada: {eliminada.get('titulo')}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("freq_done_"):
        await query.edit_message_text("✅ ¡Excelente! Recordatorio completado por hoy. 👍", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]))
        return

    if data.startswith("freq_type_"):
        frecuencia = data.replace("freq_type_", "")
        if user_id in recordatorio_temp_state:
            recordatorio_temp_state[user_id]["frecuencia"] = frecuencia
            recordatorio_temp_state[user_id]["step"] = "hora"
            keyboard = [
                [InlineKeyboardButton("⬅️ Volver", callback_data="nuevo_recordatorio_flow")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await query.edit_message_text("🕒 Escribí la hora a la que querés que te avise (ej: 20:00 o 17:00):", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data in ["reunion_presencial", "reunion_virtual"]:
        tipo = "Presencial" if data == "reunion_presencial" else "Virtual"
        reunion_temp_state[user_id] = {"tipo": tipo, "step": "titulo"}
        keyboard = [
            [InlineKeyboardButton("⬅️ Volver", callback_data="menu_agenda")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
        ]
        await query.edit_message_text(f"📝 Reunión {tipo}\n\nEscribí el título de la reunión:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("anio_"):
        reunion_temp_state[user_id]["anio"] = data.replace("anio_", "")
        reunion_temp_state[user_id]["step"] = "mes"
        keyboard = [
            [InlineKeyboardButton("Enero", callback_data="mes_01"), InlineKeyboardButton("Febrero", callback_data="mes_02"), InlineKeyboardButton("Marzo", callback_data="mes_03")],
            [InlineKeyboardButton("Abril", callback_data="mes_04"), InlineKeyboardButton("Mayo", callback_data="mes_05"), InlineKeyboardButton("Junio", callback_data="mes_06")],
            [InlineKeyboardButton("Julio", callback_data="mes_07"), InlineKeyboardButton("Agosto", callback_data="mes_08"), InlineKeyboardButton("Septiembre", callback_data="mes_09")],
            [InlineKeyboardButton("Octubre", callback_data="mes_10"), InlineKeyboardButton("Noviembre", callback_data="mes_11"), InlineKeyboardButton("Diciembre", callback_data="mes_12")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="menu_agenda")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
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
        dias_buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="anio_" + reunion_temp_state[user_id].get("anio", "2026"))])
        dias_buttons.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
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
        horas_reunion.append([InlineKeyboardButton("⬅️ Volver", callback_data="mes_" + reunion_temp_state[user_id].get("mes", "01"))])
        horas_reunion.append([InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")])
        await query.edit_message_text("⏰ Seleccioná la hora:", reply_markup=InlineKeyboardMarkup(horas_reunion))
    
    elif data.startswith("reu_h_"):
        reunion_temp_state[user_id]["reu_h"] = data.replace("reu_h_", "")
        reunion_temp_state[user_id]["step"] = "minuto_reunion"
        min_reunion = [
            [InlineKeyboardButton("00 min", callback_data="reu_m_00"), InlineKeyboardButton("15 min", callback_data="reu_m_15")],
            [InlineKeyboardButton("30 min", callback_data="reu_m_30"), InlineKeyboardButton("45 min", callback_data="reu_m_45")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="dia_" + reunion_temp_state[user_id].get("dia", "01"))],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
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
    ahora_arg = datetime.datetime.now(ARG_TZ)

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

            keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
            if "tarea" in texto_transcrito.lower():
                nueva_t = texto_transcrito.lower().replace("tarea", "").strip()
                if str_id not in user_data_store:
                    user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": {}, "recordatorios": [], "frecuentes": [], "notas": {}}
                user_data_store[str_id]["tareas"].append(nueva_t)
                guardar_datos(user_data_store)
                agregar_google_task(user_id, nueva_t)
                await update.message.reply_text(f"➕ Tarea agregada por voz: *{nueva_t}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(f"🎤 *Transcripción:* \"{texto_transcrito}\"", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
            await update.message.reply_text("❌ Error al procesar audio.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text = update.message.text
    hoy_str = ahora_arg.strftime("%Y-%m-%d")

    if user_id in user_input_states:
        estado_input = user_input_states[user_id]
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]

        if estado_input == "esperando_nombre_categoria_nota":
            del user_input_states[user_id]
            if str_id not in user_data_store:
                user_data_store[str_id] = {"notas": {}}
            if "notas" not in user_data_store[str_id]:
                user_data_store[str_id]["notas"] = {}
            
            if text not in user_data_store[str_id]["notas"]:
                user_data_store[str_id]["notas"][text] = []
                guardar_datos(user_data_store)
            
            nota_temp_state[user_id] = {"categoria": text}
            user_input_states[user_id] = "esperando_texto_nota"
            keyboard_nota = [
                [InlineKeyboardButton("⬅️ Volver", callback_data="prompt_agregar_nota")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text(f"📁 Categoría '{text}' creada. Ahora escribí el contenido de la nota:", reply_markup=InlineKeyboardMarkup(keyboard_nota))
            return

        elif estado_input == "esperando_texto_nota":
            del user_input_states[user_id]
            cat = nota_temp_state.get(user_id, {}).get("categoria", "General")
            if str_id not in user_data_store:
                user_data_store[str_id] = {"notas": {}}
            if "notas" not in user_data_store[str_id]:
                user_data_store[str_id]["notas"] = {}
            if cat not in user_data_store[str_id]["notas"]:
                user_data_store[str_id]["notas"][cat] = []
            
            user_data_store[str_id]["notas"][cat].append(text)
            guardar_datos(user_data_store)
            
            keyboard_nota_ok = [
                [InlineKeyboardButton("📌 Ver Notas", callback_data="listar_categorias_notas")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text(f"📌 Nota guardada en **{cat}**: *{text}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_nota_ok))
            return

        elif estado_input == "esperando_accion":
            del user_input_states[user_id]
            texto_completo = text.strip()
            texto_lower = texto_completo.lower()
            if str_id not in user_data_store:
                user_data_store[str_id] = {"acciones": {}}
            if "acciones" not in user_data_store[str_id]:
                user_data_store[str_id]["acciones"] = {}

            if "?" in texto_completo or "¿" in texto_completo or "cerre" in texto_lower or "revise" in texto_lower or "tomé" in texto_lower or "puse" in texto_lower:
                clave_accion = texto_lower.replace("?", "").replace("¿", "").replace("el", "").replace("la", "").strip()
                encontrada = False
                hora_reg = ""
                for acc, fecha_hora in user_data_store[str_id]["acciones"].items():
                    if any(palabra in acc for palabra in clave_accion.split() if len(palabra) > 3):
                        if fecha_hora.startswith(hoy_str):
                            encontrada = True
                            hora_reg = fecha_hora.split(" ")[1]
                            break
                
                if encontrada:
                    resp = f"Siii, registré '{clave_accion}' hoy a las {hora_reg} hs."
                else:
                    resp = f"Nooo, no he registrado esa acción hoy; la última vez no figura en el día de hoy."
            else:
                ahora_reg_str = ahora_arg.strftime("%Y-%m-%d %H:%M")
                user_data_store[str_id]["acciones"][texto_lower] = ahora_reg_str
                guardar_datos(user_data_store)
                hora_actual = ahora_arg.strftime("%H:%M")
                resp = f"Siii, registré '{texto_completo}' hoy a las {hora_actual} hs. ✅"

            await update.message.reply_text(resp, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif estado_input == "esperando_recordatorio":
            del user_input_states[user_id]
            recordatorio_temp_state[user_id] = {"texto": text, "step": "frecuencia"}
            keyboard_freq = [
                [InlineKeyboardButton("🔄 Todos los días", callback_data="freq_type_Todos los días")],
                [InlineKeyboardButton("📅 Lunes a Viernes", callback_data="freq_type_Lunes a Viernes")],
                [InlineKeyboardButton("📌 Una sola vez", callback_data="freq_type_Única vez")],
                [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text("🔄 Seleccioná la frecuencia del recordatorio:", reply_markup=InlineKeyboardMarkup(keyboard_freq))
            return

        elif estado_input == "esperando_hora_semana":
            del user_input_states[user_id]
            if str_id not in user_data_store:
                user_data_store[str_id] = {"config": {}}
            user_data_store[str_id]["config"]["semana"] = text
            guardar_datos(user_data_store)
            
            user_input_states[user_id] = "esperando_hora_finde"
            await update.message.reply_text(
                f"✅ Horario de Lunes a Viernes actualizado a: *{text} hs*\n\n"
                "🕒 Ahora, escribí el nuevo horario para **Fin de Semana** (Sábados y Domingos, ej: 10:00):",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]))
            return

        elif estado_input == "esperando_hora_finde":
            del user_input_states[user_id]
            if str_id not in user_data_store:
                user_data_store[str_id] = {"config": {}}
            user_data_store[str_id]["config"]["fin_semana"] = text
            guardar_datos(user_data_store)

            config = user_data_store[str_id]["config"]
            resumen_msg = (
                "⚙️ **¡Configuración Actualizada con Éxito!**\n\n"
                f"• Horario Lunes a Viernes: *{config.get('semana')} hs*\n"
                f"• Horario Fin de Semana: *{config.get('fin_semana')} hs*\n\n"
                "Ya podés avanzar y vincular tu cuenta de Google para aprovechar todas las funciones:"
            )
            keyboard_post_config = [
                [InlineKeyboardButton("🔗 Vincular Google", callback_data="vincular_google")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text(resumen_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_post_config))
            return

        elif estado_input == "esperando_texto_tarea":
            del user_input_states[user_id]
            agregar_google_task(user_id, text)
            await update.message.reply_text(f"➕ Tarea creada y sincronizada en Google Tasks: *{text}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        elif estado_input == "esperando_nombre_lista":
            del user_input_states[user_id]
            try:
                creds = obtener_credenciales_usuario(user_id)
                tasks_service = build('tasks', 'v1', credentials=creds)
                body = {'title': text}
                tasks_service.tasklists().insert(body=body).execute()
                await update.message.reply_text(f"📁 ¡Lista de tareas '{text}' creada con éxito en Google Tasks!", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                await update.message.reply_text(f"❌ Error al crear la lista: {e}", reply_markup=InlineKeyboardMarkup(keyboard))
            return

    if user_id in recordatorio_temp_state:
        state = recordatorio_temp_state[user_id]
        step = state.get("step")

        if step == "texto":
            state["texto"] = text
            state["step"] = "frecuencia"
            keyboard_freq = [
                [InlineKeyboardButton("🔄 Todos los días", callback_data="freq_type_Todos los días")],
                [InlineKeyboardButton("📅 Lunes a Viernes", callback_data="freq_type_Lunes a Viernes")],
                [InlineKeyboardButton("📌 Una sola vez", callback_data="freq_type_Única vez")],
                [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text("🔄 Seleccioná la frecuencia del recordatorio:", reply_markup=InlineKeyboardMarkup(keyboard_freq))
            return

        elif step == "hora":
            state["hora"] = text
            if str_id not in user_data_store:
                user_data_store[str_id] = {"recordatorios": [], "frecuentes": []}

            frecuencia = state.get("frecuencia")
            if frecuencia == "Única vez":
                if "recordatorios" not in user_data_store[str_id]:
                    user_data_store[str_id]["recordatorios"] = []
                user_data_store[str_id]["recordatorios"].append({
                    "texto": state.get("texto"),
                    "fecha": hoy_str,
                    "hora": text
                })
            else:
                if "frecuentes" not in user_data_store[str_id]:
                    user_data_store[str_id]["frecuentes"] = []
                user_data_store[str_id]["frecuentes"].append({
                    "texto": state.get("texto"),
                    "frecuencia": frecuencia,
                    "hora": text
                })

            guardar_datos(user_data_store)
            del recordatorio_temp_state[user_id]

            keyboard_menu = [
                [InlineKeyboardButton("⬅️ Volver", callback_data="menu_recordatorios")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
            ]
            await update.message.reply_text(
                f"✅ **¡Recordatorio Creado con Éxito!**\n\n"
                f"• {state.get('texto')}\n"
                f"• Frecuencia: {frecuencia}\n"
                f"• Hora: {text} hs",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_menu)
            )
            return

    if user_id in reunion_temp_state:
        state = reunion_temp_state[user_id]
        step = state.get("step")

        if step == "titulo":
            state["titulo"] = text
            state["step"] = "anio"
            keyboard = [
                [InlineKeyboardButton("2026", callback_data="anio_2026"), InlineKeyboardButton("2027", callback_data="anio_2027")],
                [InlineKeyboardButton("⬅️ Volver", callback_data="menu_agenda")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]
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
                user_data_store[str_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": {}, "recordatorios": [], "frecuentes": [], "notas": {}}
            
            reunion_obj = {
                "titulo": titulo,
                "tipo": tipo,
                "fecha": fecha_formateada,
                "hora": hora,
                "ubicacion": ubicacion_o_link
            }
            user_data_store[str_id]["reuniones"].append(reunion_obj)
            guardar_datos(user_data_store)

            sincronizar_google_calendar_crear(user_id, titulo, fecha_formateada, hora, ubicacion_o_link)
            del reunion_temp_state[user_id]

            mensaje_final = (
                "✅ ¡Reunión agendada en tu Google Calendar personal!\n\n"
                f"📌 {titulo}\n"
                f"📅 {fecha_formateada} a las {hora} hs\n"
                f"📍 {ubicacion_o_link}"
            )
            keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
            await update.message.reply_text(mensaje_final, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    # Corrección Punto 1: Ya no se agregan tareas automáticas desde texto libre; solo responde indicando usar el menú.
    keyboard_main = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="menu_principal")]]
    await update.message.reply_text(
        "🤖 Para registrar hábitos usá la opción **Acción**, o elegí una opción del menú:",
        reply_markup=InlineKeyboardMarkup(keyboard_main), parse_mode="Markdown"
    )

def main():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler(["start", "iniciar"], iniciar))
    app.add_handler(CommandHandler("conectar", conectar_google))
    app.add_handler(CommandHandler("agenda_reunion", agenda_reunion))
    app.add_handler(CommandHandler("reuniones", listar_reuniones))
    app.add_handler(CommandHandler("configuracion", configuracion_cmd))
    app.add_handler(CommandHandler("accion", accion_cmd))
    app.add_handler(CommandHandler("recordatorio", recordatorio_menu))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))
    app.add_handler(CommandHandler("completada", completada_cmd))
    app.add_handler(CommandHandler("nota", nota_cmd))
    app.add_handler(CommandHandler("lista_notas", lista_notas))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.TEXT & ~filters.COMMAND, handle_voice_or_text))

    print("🚀 @SoyOrganizabot con separación total de módulos en marcha!")
    app.run_polling()

if __name__ == '__main__':
    main()
