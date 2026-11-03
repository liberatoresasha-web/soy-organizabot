import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
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
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
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

# --- COMANDOS DEL BOT ---

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in user_data_store:
        user_data_store[user.id] = {
            "tareas": ["Revisar pendientes de recursos humanos", "Coordinar reunión scout"], 
            "hora_semana": "08:00", 
            "hora_fin_de_semana": "10:00"
        }

    await update.message.reply_text(
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte. Usá /ayuda para ver las opciones."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Comandos disponibles en @SoyOrganizabot:**\n\n"
        "• /configuracion - Ver horarios actuales\n"
        "• /hora_semana [HH:MM] - Ej: `/hora_semana 07:30`\n"
        "• /hora_finde [HH:MM] - Ej: `/hora_finde 09:45`\n"
        "• /tareas - Ver pendientes\n"
        "• /nueva_tarea [texto] - Agregar tarea\n"
        "• /ayuda - Muestra esta lista"
    )

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

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
        "Para cambiar la hora libremente, usá:\n"
        "👉 `/hora_semana 07:30`\n"
        "👉 `/hora_finde 09:15`",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "info_sem":
        await query.message.reply_text("Para cambiar Lunes a Viernes a la hora que quieras, escribí por ejemplo:\n`/hora_semana 07:15`", parse_mode="Markdown")
    elif data == "info_fin":
        await query.message.reply_text("Para cambiar el fin de semana a la hora que quieras, escribí por ejemplo:\n`/hora_finde 09:30`", parse_mode="Markdown")

# Comando libre para configurar Lunes a Viernes
async def set_hora_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Escribí la hora en formato HH:MM. Ejemplo: `/hora_semana 07:30`", parse_mode="Markdown")
        return
    
    nueva_hora = context.args[0]
    try:
        partes = nueva_hora.split(":")
        hora_target = int(partes[0])
        min_target = int(partes[1])
    except:
        await update.message.reply_text("❌ Formato incorrecto. Usá el formato `HH:MM` (ejemplo: `08:30`).", parse_mode="Markdown")
        return

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
    user_data_store[user_id]["hora_semana"] = nueva_hora

    # Programar en job_queue
    hora_utc = (hora_target + 3) % 24
    job_name = f"{user_id}_sem"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    context.job_queue.run_daily(
        enviar_reporte_matutino,
        time=datetime.time(hour=hora_utc, minute=min_target, second=0),
        chat_id=chat_id,
        user_id=user_id,
        name=job_name
    )

    await update.message.reply_text(f"✅ ¡Listo! El reporte de **Lunes a Viernes** quedó programado exactamente a las **{nueva_hora} hs**.")

# Comando libre para configurar Finde
async def set_hora_finde(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Escribí la hora en formato HH:MM. Ejemplo: `/hora_finde 10:30`", parse_mode="Markdown")
        return
    
    nueva_hora = context.args[0]
    try:
        partes = nueva_hora.split(":")
        hora_target = int(partes[0])
        min_target = int(partes[1])
    except:
        await update.message.reply_text("❌ Formato incorrecto. Usá el formato `HH:MM` (ejemplo: `10:00`).", parse_mode="Markdown")
        return

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
    user_data_store[user_id]["hora_fin_de_semana"] = nueva_hora

    hora_utc = (hora_target + 3) % 24
    job_name = f"{user_id}_fin"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    context.job_queue.run_daily(
        enviar_reporte_matutino,
        time=datetime.time(hour=hora_utc, minute=min_target, second=0),
        chat_id=chat_id,
        user_id=user_id,
        name=job_name
    )

    await update.message.reply_text(f"✅ ¡Listo! El reporte de **Fines de semana** quedó programado exactamente a las **{nueva_hora} hs**.")

# Comandos de tareas
async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id]["tareas"]:
        await update.message.reply_text("📝 No tenés tareas pendientes. Agregá una con /nueva_tarea [texto]")
        return
    
    t_list = user_data_store[user_id]["tareas"]
    texto = "📝 **Tus tareas pendientes:**\n\n" + "\n".join([f"• {t}" for t in t_list])
    await update.message.reply_text(texto)

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
    texto_tarea = " ".join(context.args)
    if not texto_tarea:
        await update.message.reply_text("⚠️ Escribí la tarea. Ejemplo: `/nueva_tarea Reunión scout`", parse_mode="Markdown")
        return

    user_data_store[user_id]["tareas"].append(texto_tarea)
    await update.message.reply_text(f"➕ **Tarea agregada:** {texto_tarea}")

def main():
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("iniciar", iniciar))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("configuracion", configuracion))
    app.add_handler(CommandHandler("hora_semana", set_hora_semana))
    app.add_handler(CommandHandler("hora_finde", set_hora_finde))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))

    print("🚀 ¡@SoyOrganizabot con configuración de hora libre listo!")
    app.run_polling()

if __name__ == '__main__':
    main()
