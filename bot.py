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

# Token configurado directamente
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
    print(f"🌐 Servidor web interno corriendo en el puerto {port}")
    server.serve_forever()

# --- DATOS Y CONFIGURACIONES POR USUARIO ---
user_data_store = {}

# --- FUNCIÓN PARA OBTENER EL CLIMA DE VILLA REGINA ---
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

# --- TAREA PROGRAMADA DEL REPORTE MATUTINO ---
async def enviar_reporte_matutino(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    user_id = job.user_id

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}
    
    # Validamos si hoy es fin de semana (Sábado = 5, Domingo = 6)
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
        "Estoy listo para ayudarte a organizar tus tareas y notas. Usá /ayuda para ver las opciones."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Comandos disponibles en @SoyOrganizabot:**\n\n"
        "• /iniciar - Iniciar la conversación\n"
        "• /ayuda - Muestra esta lista\n"
        "• /configuracion - Ajustar reportes diferenciados\n"
        "• /tareas - Ver pendientes\n"
        "• /nueva_tarea [texto] - Agregar tarea\n"
        "• /completada - Finalizar tarea\n"
        "• /nota - Guardar nota\n"
        "• /lista_notas - Ver notas\n"
        "• /recordatorio - Programar aviso\n"
        "• /silencio - Modo silencio"
    )

# ⚙️ Comando /configuracion con menú avanzado
async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

    h_sem = user_data_store[user_id]["hora_semana"]
    h_fin = user_data_store[user_id]["hora_fin_de_semana"]

    keyboard = [
        [InlineKeyboardButton(f"🏢 Lunes a Viernes ({h_sem})", callback_data="menu_sem")],
        [InlineKeyboardButton(f"🏡 Finde / Sáb-Dom ({h_fin})", callback_data="menu_fin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ **Configuración de Reportes Matutinos:**\n\n"
        f"• Lunes a Viernes: **{h_sem} hs**\n"
        f"• Fines de semana: **{h_fin} hs**\n\n"
        "Seleccioná qué bloque querés modificar:",
        reply_markup=reply_markup
    )

# Manejador de botones interactivos
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_sem":
        # Mostrar opciones de horario para Lunes a Viernes
        keyboard = [
            [InlineKeyboardButton("07:00 hs", callback_data="set_sem_07:00"),
             InlineKeyboardButton("08:00 hs", callback_data="set_sem_08:00")],
            [InlineKeyboardButton("09:00 hs", callback_data="set_sem_09:00"),
             InlineKeyboardButton("⬅️ Volver", callback_data="menu_volver")]
        ]
        await query.edit_message_text("🏢 Seleccioná la hora para **Lunes a Viernes**:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_fin":
        # Mostrar opciones de horario para Finde
        keyboard = [
            [InlineKeyboardButton("09:00 hs", callback_data="set_fin_09:00"),
             InlineKeyboardButton("10:00 hs", callback_data="set_fin_10:00")],
            [InlineKeyboardButton("11:00 hs", callback_data="set_fin_11:00"),
             InlineKeyboardButton("⬅️ Volver", callback_data="menu_volver")]
        ]
        await query.edit_message_text("🏡 Seleccioná la hora para el **Fin de semana**:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_volver":
        await configuracion_menu_principal(query)

    elif data.startswith("set_sem_") or data.startswith("set_fin_"):
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        
        tipo, hora_val = data.split("_")[1], data.split("_")[2]
        
        if user_id not in user_data_store:
            user_data_store[user_id] = {"tareas": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

        if tipo == "sem":
            user_data_store[user_id]["hora_semana"] = hora_val
            label = "Lunes a Viernes"
        else:
            user_data_store[user_id]["hora_fin_de_semana"] = hora_val
            label = "Fin de semana"

        # Programamos el trabajo diario en job_queue
        partes = hora_val.split(":")
        hora_utc = (int(partes[0]) + 3) % 24
        min_target = int(partes[1])

        job_name = f"{user_id}_{tipo}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        context.job_queue.run_daily(
            enviar_reporte_matutino,
            time=datetime.time(hour=hora_utc, minute=min_target, second=0),
            chat_id=chat_id,
            user_id=user_id,
            name=job_name
        )

        await query.edit_message_text(
            text=f"✅ **¡Guardado con éxito!**\n\nEl reporte de **{label}** quedó programado a las **{hora_val} hs**."
        )

async def configuracion_menu_principal(query):
    user_id = query.from_user.id
    h_sem = user_data_store.get(user_id, {}).get("hora_semana", "08:00")
    h_fin = user_data_store.get(user_id, {}).get("hora_fin_de_semana", "10:00")

    keyboard = [
        [InlineKeyboardButton(f"🏢 Lunes a Viernes ({h_sem})", callback_data="menu_sem")],
        [InlineKeyboardButton(f"🏡 Finde / Sáb-Dom ({h_fin})", callback_data="menu_fin")]
    ]
    await query.edit_message_text(
        "⚙️ **Configuración de Reportes Matutinos:**\n\n"
        f"• Lunes a Viernes: **{h_sem} hs**\n"
        f"• Fines de semana: **{h_fin} hs**\n\n"
        "Seleccioná qué bloque querés modificar:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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

async def completada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Próximamente selector de tareas completadas.")

async def nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Mandame el texto de tu nota.")

async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📂 Tus notas guardadas.")

async def recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏰ Configuración de recordatorios.")

async def silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔕 Modo silencio.")

def main():
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("iniciar", iniciar))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("configuracion", configuracion))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))
    app.add_handler(CommandHandler("completada", completada))
    app.add_handler(CommandHandler("nota", nota))
    app.add_handler(CommandHandler("lista_notas", lista_notas))
    app.add_handler(CommandHandler("recordatorio", recordatorio))
    app.add_handler(CommandHandler("silencio", silencio))

    print("🚀 ¡@SoyOrganizabot con horarios diferenciados listo!")
    app.run_polling()

if __name__ == '__main__':
    main()
