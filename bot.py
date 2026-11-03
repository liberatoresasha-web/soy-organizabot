import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import datetime
import urllib.request
import json

# Configurar logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "9006959123:AAGwA8wE4vhFi8-tv0bUvFAnnLnfyi2ZCXQ"

# --- SERVIDOR WEB PARA CUMPLIR CON RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"@SoyOrganizabot activo y funcionando!")
    
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

# --- ALMACENAMIENTO EN MEMORIA POR USUARIO ---
user_data_store = {}

def obtener_clima_villa_regina():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=-39.07&longitude=-67.08&current=temperature_2m,weather_code"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            temp = data["current"]["temperature_2m"]
            return f"{temp}°C, cielo despejado/parcial"
    except Exception as e:
        print(f"Error al obtener clima: {e}")
        return "Clima no disponible por el momento"

async def enviar_reporte_matutino(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    user_id = job.user_id

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
    hoy_es_finde = datetime.datetime.now().weekday() >= 5
    tareas_pendientes = user_data_store[user_id].get("tareas", [])
    clima = obtener_clima_villa_regina()

    if tareas_pendientes:
        lista_str = "\n".join([f"• {t}" for t in tareas_pendientes])
    else:
        lista_str = "• No tenés tareas pendientes para hoy. ¡Día libre! 🎉"

    saludo_extra = "¡Disfrutá del fin de semana, Sasha! 🌴" if hoy_es_finde else "¡Que tengas una excelente jornada laboral!"

    mensaje = (
        f"☀️ ¡Buen día, Sasha! 🤖☕\n\n"
        f"🌤 **Clima en Villa Regina:** {clima}\n\n"
        "📝 **Tus tareas pendientes:**\n"
        f"{lista_str}\n\n"
        f"{saludo_extra}"
    )

    await context.bot.send_message(chat_id=chat_id, text=mensaje)

# --- COMANDOS PRINCIPALES ---

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in user_data_store:
        user_data_store[user.id] = {
            "tareas": ["Revisar pendientes de recursos humanos"], 
            "listas": {"supermercado": ["Leche", "Café"]},
            "reuniones": [],
            "acciones": [],
            "hora_semana": "08:00", 
            "hora_fin_de_semana": "10:00"
        }

    await update.message.reply_text(
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte. Usá /ayuda para ver las opciones o mandame un audio."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Comandos disponibles en @SoyOrganizabot:**\n\n"
        "• /configuracion - Gestionar horarios de reportes\n"
        "• /Agenda_reunion - Asistente para agendar reuniones\n"
        "• /reuniones - Ver listado de reuniones\n"
        "• /lista [categoría] [texto] - Agregar ítem a lista (ej: /lista supermercado pan)\n"
        "• /ver_listas - Ver todas tus listas\n"
        "• /tareas - Ver pendientes (Google Tasks)\n"
        "• /nueva_tarea [texto] - Agregar tarea\n"
        "• /completada - Finalizar tarea\n"
        "• /accion [texto] - Registrar o consultar acciones cotidianas\n"
        "• /silencio - Modo silencio"
    )

# --- CONFIGURACIÓN ---
async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

    h_sem = user_data_store[user_id]["hora_semana"]
    h_fin = user_data_store[user_id]["hora_fin_de_semana"]

    keyboard = [
        [InlineKeyboardButton(f"🏢 Lunes a Viernes ({h_sem})", callback_data="info_sem")],
        [InlineKeyboardButton(f"🏡 Finde / Sáb-Dom ({h_fin})", callback_data="info_fin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ **Configuración de Reportes Matutinos:**\n\n"
        f"• Lunes a Viernes: **{h_sem} hs**\n"
        f"• Fines de semana: **{h_fin} hs**\n\n"
        "Para cambiar la hora escribí:\n"
        "👉 `/hora_semana 07:30`\n"
        "👉 `/hora_finde 09:15`",
        reply_markup=reply_markup
    )

async def set_hora_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Usá el formato: `/hora_semana 07:30`", parse_mode="Markdown")
        return
    nueva_hora = context.args[0]
    try:
        partes = nueva_hora.split(":")
        hora_target, min_target = int(partes[0]), int(partes[1])
    except:
        await update.message.reply_text("❌ Formato incorrecto. Usá `HH:MM`.", parse_mode="Markdown")
        return

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    user_data_store[user_id]["hora_semana"] = nueva_hora

    hora_utc = (hora_target + 3) % 24
    job_name = f"{user_id}_sem"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    context.job_queue.run_daily(
        enviar_reporte_matutino,
        time=datetime.time(hour=hora_utc, minute=min_target, second=0),
        chat_id=chat_id, user_id=user_id, name=job_name
    )
    await update.message.reply_text(f"✅ ¡Reporte de Lunes a Viernes programado a las **{nueva_hora} hs**!")

async def set_hora_finde(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Usá el formato: `/hora_finde 10:30`", parse_mode="Markdown")
        return
    nueva_hora = context.args[0]
    try:
        partes = nueva_hora.split(":")
        hora_target, min_target = int(partes[0]), int(partes[1])
    except:
        await update.message.reply_text("❌ Formato incorrecto. Usá `HH:MM`.", parse_mode="Markdown")
        return

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    user_data_store[user_id]["hora_fin_de_semana"] = nueva_hora

    hora_utc = (hora_target + 3) % 24
    job_name = f"{user_id}_fin"
    for job in context.job_queue.get_jobs_by_
