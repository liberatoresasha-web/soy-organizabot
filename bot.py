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

# --- SERVIDOR WEB EN HILO SECUNDARIO (PARA CUMPLIR CON RENDER) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"@SoyOrganizabot activo y funcionando en Render!")
    
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

# --- ALMACENAMIENTO EN MEMORIA POR USUARIO ---
user_data_store = {}
reunion_temp_state = {}

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
        f"☀️ **¡Buen día, Sasha!** 🤖☕\n\n"
        f"🌤 **Clima en Villa Regina:** {clima}\n\n"
        "📝 **Tus tareas pendientes:**\n"
        f"{lista_str}\n\n"
        f"{saludo_extra}"
    )

    await context.bot.send_message(chat_id=chat_id, text=mensaje, parse_mode="Markdown")

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

    # Única botonera inicial para configurar reportes
    keyboard = [
        [InlineKeyboardButton("⚙️ Configurar reportes", callback_data="menu_config")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    texto_bienvenida = (
        f"¡Hola, **{user.first_name}**! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte y comenzar a organizar tu día. Esta es la lista de comandos disponibles:\n\n"
        "• /configuracion - Configurar horarios para el **reporte matutino**\n"
        "• /agenda_reunion - Asistente interactivo para agendar reuniones\n"
        "• /reuniones - Ver listado de reuniones agendadas\n"
        "• /tareas - Ver listado de pendientes actuales\n"
        "• /nueva_tarea - Agregar una tarea nueva\n"
        "• /nota - Guardar una nota rápida\n"
        "• /lista_notas - Ver tus notas guardadas\n"
        "• /accion - Registrar o consultar tus acciones cotidianas\n\n"
        "Para comenzar, por favor configurá tus preferencias de horarios:"
    )

    await update.message.reply_text(texto_bienvenida, reply_markup=reply_markup, parse_mode="Markdown")

# --- CONFIGURACIÓN INTERACTIVA DE REPORTES ---
async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

    # Iniciar flujo de configuración guiada: primero horario semanal
    reunion_temp_state[user_id] = {"cfg_tipo": "sem", "step": "cfg_hora"}
    
    horas_buttons = []
    fila = []
    for h in range(24):
        h_str = f"{h:02d}"
        fila.append(InlineKeyboardButton(f"{h_str} hs", callback_data=f"cfg_h_{h_str}"))
        if len(fila) == 6:
            horas_buttons.append(fila)
            fila = []
    if fila:
        horas_buttons.append(fila)

    texto = "⚙️ **Paso 1/2:** Seleccioná la hora para el **Horario Semanal (Lunes a Viernes)**:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(horas_buttons), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(horas_buttons), parse_mode="Markdown")

# --- ASISTENTE DE REUNIONES INTERACTIVO ---
async def agenda_reunion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reunion_temp_state[user_id] = {"step": "tipo"}
    
    keyboard = [
        [InlineKeyboardButton("🏢 Presencial", callback_data="reunion_presencial"),
         InlineKeyboardButton("💻 Virtual", callback_data="reunion_virtual")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📅 **Asistente de Reuniones:**\n\n¿Qué tipo de reunión querés agendar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📅 **Asistente de Reuniones:**\n\n¿Qué tipo de reunión querés agendar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def listar_reuniones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id].get("reuniones"):
        texto = "📅 No tenés reuniones agendadas por el momento."
    else:
        reuniones_list = user_data_store[user_id]["reuniones"]
        texto = "📅 **Tus reuniones programadas:**\n\n" + "".join([f"• {r}\n" for r in reuniones_list])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, parse_mode="Markdown")

# --- ACCIONES COTIDIANAS ---
async def accion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = " ".join(context.args)

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    
    acciones_usuario = user_data_store[user_id]["acciones"]

    if not texto:
        await update.message.reply_text(
            "⚠️ Indicá la acción. Ejemplo:\n"
            "`/accion Cerré la puerta de casa` o preguntá por algo.\n"
            "También podés pedir un resumen escribiendo `/accion resumen`",
            parse_mode="Markdown"
        )
        return

    if texto.lower() == "resumen":
        if not acciones_usuario:
            await update.message.reply_text("📋 No tenés acciones registradas todavía en el día.")
            return
        resumen_str = "\n".join([f"• {a['accion']} (a las {a['hora']})" for a in acciones_usuario])
        await update.message.reply_text(f"📋 **Resumen de tus acciones de hoy:**\n\n{resumen_str}", parse_mode="Markdown")
        return

    if "?" in texto or texto.lower().startswith("¿") or "hice" in texto.lower() or "cerré" in texto.lower() or "apagué" in texto.lower():
        encontrada = None
        for acc in acciones_usuario:
            if any(palabra in acc["accion"].lower() for palabra in texto.lower().replace("?", "").split() if len(palabra) > 3):
                encontrada = acc
                break
        
        if encontrada:
            await update.message.reply_text(f"¡Siii, Sasha! Registré que **{encontrada['accion']}** a las **{encontrada['hora']} hs**.", parse_mode="Markdown")
        else:
            keyboard = [[InlineKeyboardButton("Sí, ver resumen", callback_data="ver_resumen_acciones"),
                         InlineKeyboardButton("No", callback_data="no_resumen")]]
            await update.message.reply_text(
                "❌ Noo, no tengo registrada esa acción aún.\n¿Quieres ver qué acciones realizaste hoy?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        hora_actual = datetime.datetime.now().strftime("%H:%M")
        acciones_usuario.append({"
