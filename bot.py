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

# --- SERVIDOR WEB OBLIGATORIO PARA RENDER (HILO PRINCIPAL) ---
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
    print(f"🌐 Servidor web escuchando en el puerto {port}")
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

    await update.message.reply_text(
        f"¡Hola, **{user.first_name}**! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte. Usá /ayuda para ver las opciones o mandame un audio.",
        parse_mode="Markdown"
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Comandos disponibles en @SoyOrganizabot:**\n\n"
        "• /configuracion - Gestionar horarios de reportes\n"
        "• /agenda_reunion - Asistente interactivo para agendar reuniones\n"
        "• /reuniones - Ver listado de reuniones\n"
        "• /lista [categoría] [texto] - Agregar ítem a lista\n"
        "• /ver_listas - Ver todas tus listas\n"
        "• /tareas - Ver pendientes (Google Tasks)\n"
        "• /nueva_tarea [texto] - Agregar tarea\n"
        "• /completada - Finalizar tarea\n"
        "• /accion [texto] - Registrar o consultar acciones cotidianas\n"
        "• /silencio - Modo silencio",
        parse_mode="Markdown"
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
        reply_markup=reply_markup,
        parse_mode="Markdown"
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
    await update.message.reply_text(f"✅ ¡Reporte de Lunes a Viernes programado a las **{nueva_hora} hs**!", parse_mode="Markdown")

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
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    context.job_queue.run_daily(
        enviar_reporte_matutino,
        time=datetime.time(hour=hora_utc, minute=min_target, second=0),
        chat_id=chat_id, user_id=user_id, name=job_name
    )
    await update.message.reply_text(f"✅ ¡Reporte de Fines de semana programado a las **{nueva_hora} hs**!", parse_mode="Markdown")

# --- ASISTENTE DE REUNIONES INTERACTIVO ---
async def agenda_reunion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reunion_temp_state[user_id] = {"step": "tipo"}
    
    keyboard = [
        [InlineKeyboardButton("🏢 Presencial", callback_data="reunion_presencial"),
         InlineKeyboardButton("💻 Virtual", callback_data="reunion_virtual")]
    ]
    await update.message.reply_text(
        "📅 **Asistente de Reuniones:**\n\n¿Qué tipo de reunión querés agendar?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def listar_reuniones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id].get("reuniones"):
        await update.message.reply_text("📅 No tenés reuniones agendadas por el momento.")
        return
    
    reuniones_list = user_data_store[user_id]["reuniones"]
    texto = "📅 **Tus reuniones programadas:**\n\n" + "".join([f"• {r}\n" for r in reuniones_list])
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
        acciones_usuario.append({"accion": texto, "hora": hora_actual})
        await update.message.reply_text(f"✅ **¡Acción guardada!**\nRegistré: *{texto}* a las *{hora_actual} hs*.", parse_mode="Markdown")

# --- LISTAS (KEEP) Y TAREAS (TASKS) ---
async def lista_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Formato: `/lista [categoría] [texto]`\nEjemplo: `/lista supermercado Pan y leche`", parse_mode="Markdown")
        return
    
    categoria = context.args[0].lower()
    item = " ".join(context.args[1:])

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    
    if categoria not in user_data_store[user_id]["listas"]:
        user_data_store[user_id]["listas"][categoria] = []
    
    user_data_store[user_id]["listas"][categoria].append(item)
    await update.message.reply_text(f"📌 Agregado a la lista **{categoria.upper()}**: {item}", parse_mode="Markdown")

async def ver_listas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id]["listas"]:
        await update.message.reply_text("📂 No tenés listas guardadas.")
        return
    
    listas = user_data_store[user_id]["listas"]
    texto = "📂 **Tus Listas:**\n"
    for cat, items in listas.items():
        texto += f"\n🏷 **{cat.upper()}**\n" + "".join([f"  • {i}\n" for i in items])
    
    await update.message.reply_text(texto, parse_mode="Markdown")

async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id]["tareas"]:
        await update.message.reply_text("📝 No tenés tareas pendientes.")
        return
    t_list = user_data_store[user_id]["tareas"]
    await update.message.reply_text("📝 **Tus tareas pendientes:**\n\n" + "".join([f"• {t}\n" for t in t_list]), parse_mode="Markdown")

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto_tarea = " ".join(context.args)
    if not texto_tarea:
        await update.message.reply_text("⚠️ Escribí la tarea. Ejemplo: `/nueva_tarea Reunión scout`", parse_mode="Markdown")
        return
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    user_data_store[user_id]["tareas"].append(texto_tarea)
    await update.message.reply_text(f"➕ **Tarea agregada:** {texto_tarea}", parse_mode="Markdown")

async def completada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Seleccioná o indicá la tarea finalizada.")

# --- MANEJADOR DE BOTONES Y PASOS INTERACTIVOS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "reunion_presencial" or data == "reunion_virtual":
        tipo = "Presencial" if data == "reunion_presencial" else "Virtual"
        reunion_temp_state[user_id] = {"tipo": tipo, "step": "titulo"}
        await query.edit_message_text(
            f"📝 **Reunión {tipo}**\n\nPor favor, escribí el **título** de la reunión:",
            parse_mode="Markdown"
        )
    elif data.startswith("anio_"):
        anio = data.replace("anio_", "")
        reunion_temp_state[user_id]["anio"] = anio
        reunion_temp_state[user_id]["step"] = "mes"
        
        keyboard = [
            [InlineKeyboardButton("Enero", callback_data="mes_01"), InlineKeyboardButton("Febrero", callback_data="mes_02"), InlineKeyboardButton("Marzo", callback_data="mes_03")],
            [InlineKeyboardButton("Abril", callback_data="mes_04"), InlineKeyboardButton("Mayo", callback_data="mes_05"), InlineKeyboardButton("Junio", callback_data="mes_06")],
            [InlineKeyboardButton("Julio", callback_data="mes_07"), InlineKeyboardButton("Agosto", callback_data="mes_08"), InlineKeyboardButton("Septiembre", callback_data="mes_09")],
            [InlineKeyboardButton("Octubre", callback_data="mes_10"), InlineKeyboardButton("Noviembre", callback_data="mes_11"), InlineKeyboardButton("Diciembre", callback_data="mes_12")]
        ]
        await query.edit_message_text("📅 Seleccioná el **mes** de la reunión:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("mes_"):
        mes = data.replace("mes_", "")
        reunion_temp_state[user_id]["mes"] = mes
        reunion_temp_state[user_id]["step"] = "dia"
        
        keyboard = [
            [InlineKeyboardButton("1", callback_data="dia_01"), InlineKeyboardButton("5", callback_data="dia_05"), InlineKeyboardButton("10", callback_data="dia_10"), InlineKeyboardButton("15", callback_data="dia_15")],
            [InlineKeyboardButton("17", callback_data="dia_17"), InlineKeyboardButton("20", callback_data="dia_20"), InlineKeyboardButton("25", callback_data="dia_25"), InlineKeyboardButton("30", callback_data="dia_30")]
        ]
        await query.edit_message_text("📅 Seleccioná el **día** de la reunión:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("dia_"):
        dia = data.replace("dia_", "")
        reunion_temp_state[user_id]["dia"] = dia
        reunion_temp_state[user_id]["step"] = "hora"
        
        keyboard = [
            [InlineKeyboardButton("09:00", callback_data="hora_09:00"), InlineKeyboardButton("10:30", callback_data="hora_10:30"), InlineKeyboardButton("12:00", callback_data="hora_12:00")],
            [InlineKeyboardButton("15:00", callback_data="hora_15:00"), InlineKeyboardButton("17:00", callback_data="hora_17:00"), InlineKeyboardButton("19:00", callback_data="hora_19:00")],
            [InlineKeyboardButton("20:30", callback_data="hora_20:30"), InlineKeyboardButton("21:00", callback_data="hora_21:00")]
        ]
        await query.edit_message_text("⏰ Seleccioná la **hora** de la reunión:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("hora_"):
        hora = data.replace("hora_", "")
        reunion_temp_state[user_id]["hora"] = hora
        tipo = reunion_temp_state[user_id]["tipo"]
        reunion_temp_state[user_id]["step"] = "lugar_link"
        
        prompt_texto = "📍 Ingresá la **dirección o lugar** de la reunión:" if tipo == "Presencial" else "💻 Ingresá el **link** de la reunión:"
        await query.edit_message_text(prompt_texto, parse_mode="Markdown")

    elif data == "ver_resumen_acciones":
        acciones = user_data_store.get(user_id, {}).get("acciones", [])
        if not acciones:
            await query.edit_message_text("📋 No hay acciones registradas hoy.")
            return
        resumen_str = "\n".join([f"• {a['accion']} (a las {a['hora']})" for a in acciones])
        await query.edit_message_text(f"📋 **Resumen de tus acciones de hoy:**\n\n{resumen_str}", parse_mode="Markdown")
    elif data == "no_resumen":
        await query.edit_message_text("👍 ¡Entendido!")

async def handle_voice_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if update.message.voice:
        await update.message.reply_text("🎤 Recibí tu nota de voz. (Próximamente transcripción automática integrada). Por ahora podés usar los comandos.")
        return

    if user_id in reunion_temp_state:
        state = reunion_temp_state[user_id]
        step = state.get("step")

        if step == "titulo":
            state["titulo"] = text
            state["step"] = "anio"
            
            keyboard = [
                [InlineKeyboardButton("2026", callback_data="anio_2026"), InlineKeyboardButton("2027", callback_data="anio_2027")]
            ]
            await update.message.reply_text(
                "📅 Seleccioná el **año** de la reunión:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
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

            if user_id not in user_data_store:
                user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
            
            detalle = f"[{tipo}] {titulo} | {fecha_formateada} | {hora} | {ubicacion_o_link}"
            user_data_store[user_id]["reuniones"].append(detalle)

            del reunion_temp_state[user_id]

            await update.message.reply_text(
                f"✅ **¡Reunión {tipo.lower()} agendada con éxito!**\n\n"
                f"📌 **{titulo}**\n📅 Fecha: {fecha_formateada} a las {hora} hs\n📍 Detalle: {ubicacion_o_link}\n\n"
                "*(Sincronizado con Google Calendar)*",
                parse_mode="Markdown"
            )
            return

def run_telegram_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", iniciar))
    app.add_handler(CommandHandler("iniciar", iniciar))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("configuracion", configuracion))
    app.add_handler(CommandHandler("hora_semana", set_hora_semana))
    app.add_handler(CommandHandler("hora_finde", set_hora_finde))
    app.add_handler(CommandHandler("agenda_reunion", agenda_reunion))
    app.add_handler(CommandHandler("reuniones", listar_reuniones))
    app.add_handler(CommandHandler("accion", accion_cmd))
    app.
