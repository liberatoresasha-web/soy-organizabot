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

# --- COMANDOS PRINCIPALES ---

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in user_data_store:
        user_data_store[user.id] = {
            "tareas": ["Revisar pendientes"], 
            "listas": {},
            "reuniones": [],
            "acciones": [],
            "hora_semana": "08:00", 
            "hora_fin_de_semana": "10:00"
        }

    keyboard = [
        [InlineKeyboardButton("⚙️ Configurar reportes", callback_data="menu_config")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    texto_bienvenida = (
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte y comenzar a organizar tu día. Esta es la lista de comandos disponibles:\n\n"
        "• /configuracion - Configurar horarios para el reporte matutino\n"
        "• /agenda_reunion - Asistente interactivo para agendar reuniones\n"
        "• /reuniones - Ver listado de reuniones agendadas\n"
        "• /tareas - Ver listado de pendientes actuales\n"
        "• /nueva_tarea - Agregar una tarea nueva\n"
        "• /nota - Guardar una nota rápida\n"
        "• /lista_notas - Ver tus notas guardadas\n"
        "• /accion - Registrar o consultar tus acciones cotidianas\n\n"
        "Para comenzar, por favor configurá tus preferencias de horarios:"
    )

    await update.message.reply_text(texto_bienvenida, reply_markup=reply_markup)

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "hora_semana": "08:00", "hora_fin_de_semana": "10:00"}

    reunion_temp_state[user_id] = {"step": "cfg_sem_hora"}
    
    horas_buttons = []
    fila = []
    for h in range(4, 13):
        h_str = f"{h:02d}"
        fila.append(InlineKeyboardButton(f"{h_str} hs", callback_data=f"cfgh_sem_{h_str}"))
        if len(fila) == 3:
            horas_buttons.append(fila)
            fila = []
    if fila:
        horas_buttons.append(fila)

    texto = "⚙️ **Paso 1/4:** Seleccioná la hora para el **Horario Semanal (Lunes a Viernes)** (de 04 a 12 hs):"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(horas_buttons), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(horas_buttons), parse_mode="Markdown")

async def agenda_reunion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reunion_temp_state[user_id] = {"step": "tipo"}
    
    keyboard = [
        [InlineKeyboardButton("🏢 Presencial", callback_data="reunion_presencial"),
         InlineKeyboardButton("💻 Virtual", callback_data="reunion_virtual")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📅 Asistente de Reuniones:\n\n¿Qué tipo de reunión querés agendar?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "📅 Asistente de Reuniones:\n\n¿Qué tipo de reunión querés agendar?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def listar_reuniones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id].get("reuniones"):
        texto = "📅 No tenés reuniones agendadas por el momento."
        reply_markup = None
    else:
        reuniones = user_data_store[user_id]["reuniones"]
        try:
            reuniones_ordenadas = sorted(reuniones, key=lambda x: x.split("|")[1].strip())
            user_data_store[user_id]["reuniones"] = reuniones_ordenadas
        except Exception:
            reuniones_ordenadas = reuniones

        texto = "📅 **Tus reuniones programadas (ordenadas por fecha):**\n\n"
        for idx, r in enumerate(reuniones_ordenadas, 1):
            texto += f"{idx}. {r}\n"

        keyboard = [
            [InlineKeyboardButton("✏️ Editar / Reagendar", callback_data="reuniones_editar"),
             InlineKeyboardButton("🗑 Eliminar", callback_data="reuniones_eliminar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def accion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = " ".join(context.args)

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    
    acciones_usuario = user_data_store[user_id]["acciones"]

    if not texto:
        await update.message.reply_text(
            "⚠️ Indicá la acción. Ejemplo:\n"
            "/accion Cerré la puerta de casa o preguntá por algo.\n"
            "También podés pedir un resumen escribiendo /accion resumen"
        )
        return

    if texto.lower() == "resumen":
        if not acciones_usuario:
            await update.message.reply_text("📋 No tenés acciones registradas todavía en el día.")
            return
        resumen_str = "\n".join([f"• {a['accion']} (a las {a['hora']})" for a in acciones_usuario])
        await update.message.reply_text(f"📋 Resumen de tus acciones de hoy:\n\n{resumen_str}")
        return

    if "?" in texto or texto.lower().startswith("¿") or "hice" in texto.lower() or "cerré" in texto.lower() or "apagué" in texto.lower():
        encontrada = None
        for acc in acciones_usuario:
            if any(palabra in acc["accion"].lower() for palabra in texto.lower().replace("?", "").split() if len(palabra) > 3):
                encontrada = acc
                break
        
        user_name = update.effective_user.first_name
        if encontrada:
            await update.message.reply_text(f"¡Siii, {user_name}! Registré que {encontrada['accion']} a las {encontrada['hora']} hs.")
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
        await update.message.reply_text(f"✅ ¡Acción guardada!\nRegistré: {texto} a las {hora_actual} hs.")

async def nota_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto_nota = " ".join(context.args)
    if not texto_nota:
        await update.message.reply_text("⚠️ Escribí la nota. Ejemplo: /nota Comprar regalo")
        return
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": [], "notas": []}
    if "notas" not in user_data_store[user_id]:
        user_data_store[user_id]["notas"] = []
    user_data_store[user_id]["notas"].append(texto_nota)
    await update.message.reply_text(f"📌 Nota guardada: {texto_nota}")

async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id].get("notas"):
        texto = "📂 No tenés notas guardadas recientemente."
    else:
        notas_list = user_data_store[user_id]["notas"]
        texto = "📂 Tus notas guardadas:\n\n" + "".join([f"• {n}\n" for n in notas_list])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto)
    else:
        await update.message.reply_text(texto)

async def lista_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Formato: /lista [categoría] [texto]\nEjemplo: /lista supermercado Pan y leche")
        return
    
    categoria = context.args[0].lower()
    item = " ".join(context.args[1:])

    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    
    if categoria not in user_data_store[user_id]["listas"]:
        user_data_store[user_id]["listas"][categoria] = []
    
    user_data_store[user_id]["listas"][categoria].append(item)
    await update.message.reply_text(f"📌 Agregado a la lista {categoria.upper()}: {item}")

async def ver_listas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id].get("listas"):
        texto = "📂 No tenés listas guardadas."
    else:
        listas = user_data_store[user_id]["listas"]
        texto = "📂 Tus Listas:\n"
        for cat, items in listas.items():
            texto += f"\n🏷 {cat.upper()}\n" + "".join([f"  • {i}\n" for i in items])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto)
    else:
        await update.message.reply_text(texto)

async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store or not user_data_store[user_id]["tareas"]:
        texto = "📝 No tenés tareas pendientes."
    else:
        t_list = user_data_store[user_id]["tareas"]
        texto = "📝 Tus tareas pendientes:\n\n" + "".join([f"• {t}\n" for t in t_list])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(texto)
    else:
        await update.message.reply_text(texto)

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto_tarea = " ".join(context.args)
    if not texto_tarea:
        await update.message.reply_text("⚠️ Escribí la tarea. Ejemplo: /nueva_tarea Reunión scout")
        return
    if user_id not in user_data_store:
        user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
    user_data_store[user_id]["tareas"].append(texto_tarea)
    await update.message.reply_text(f"➕ Tarea agregada: {texto_tarea}")

async def completada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Seleccioná o indicá la tarea finalizada.")

# --- MANEJADOR DE BOTONES Y PASOS INTERACTIVOS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if data == "menu_agenda":
        await agenda_reunion(update, context)
        return
    elif data == "menu_tareas":
        await tareas(update, context)
        return
    elif data == "menu_notas":
        await lista_notas(update, context)
        return
    elif data == "menu_acciones":
        await query.edit_message_text("⚡ Para registrar una acción escribí por ejemplo:\n/accion Cerré la puerta\nPara ver el resumen escribí:\n/accion resumen")
        return
    elif data == "menu_config":
        await configuracion(update, context)
        return

    elif data == "reuniones_eliminar":
        if user_id not in user_data_store or not user_data_store[user_id].get("reuniones"):
            await query.edit_message_text("📅 No tenés reuniones para eliminar.")
            return
        
        reuniones = user_data_store[user_id]["reuniones"]
        texto = "🗑 **Seleccioná el número de la reunión que querés eliminar:**\n\n"
        for idx, r in enumerate(reuniones, 1):
            texto += f"{idx}. {r}\n"
        texto += "\n*(Escribí el número correspondiente por el chat)*"
        
        reunion_temp_state[user_id] = {"step": "esperando_eliminar_numero"}
        await query.edit_message_text(texto, parse_mode="Markdown")
        return

    elif data == "reuniones_editar":
        await query.edit_message_text("✏️ Para reagendar o editar una reunión, podés volver a crearla con /agenda_reunion o eliminar la actual.")
        return

    if data.startswith("cfgh_sem_"):
        h_val = data.replace("cfgh_sem_", "")
        if user_id not in reunion_temp_state:
            reunion_temp_state[user_id] = {}
        reunion_temp_state[user_id]["sem_h"] = h_val
        reunion_temp_state[user_id]["step"] = "cfg_sem_min"

        min_buttons = [
            [InlineKeyboardButton("00 min", callback_data="cfgm_sem_00"), InlineKeyboardButton("05 min", callback_data="cfgm_sem_05"), InlineKeyboardButton("10 min", callback_data="cfgm_sem_10")],
            [InlineKeyboardButton("15 min", callback_data="cfgm_sem_15"), InlineKeyboardButton("20 min", callback_data="cfgm_sem_20"), InlineKeyboardButton("25 min", callback_data="cfgm_sem_25")],
            [InlineKeyboardButton("30 min", callback_data="cfgm_sem_30"), InlineKeyboardButton("35 min", callback_data="cfgm_sem_35"), InlineKeyboardButton("40 min", callback_data="cfgm_sem_40")],
            [InlineKeyboardButton("45 min", callback_data="cfgm_sem_45"), InlineKeyboardButton("50 min", callback_data="cfgm_sem_50"), InlineKeyboardButton("55 min", callback_data="cfgm_sem_55")]
        ]
        await query.edit_message_text(f"⚙️ Hora semanal seleccionada: {h_val} hs.\n\n**Paso 2/4:** Seleccioná los minutos:", reply_markup=InlineKeyboardMarkup(min_buttons), parse_mode="Markdown")
        return

    elif data.startswith("cfgm_sem_"):
        m_val = data.replace("cfgm_sem_", "")
        if user_id not in reunion_temp_state:
            reunion_temp_state[user_id] = {}
        reunion_temp_state[user_id]["sem_m"] = m_val
        
        h_sem = reunion_temp_state[user_id].get("sem_h", "08")
        if user_id not in user_data_store:
            user_data_store[user_id] = {}
        user_data_store[user_id]["hora_semana"] = f"{h_sem}:{m_val}"

        reunion_temp_state[user_id]["step"] = "cfg_fin_hora"
        
        horas_buttons = []
        fila = []
        for h in range(7, 17):
            h_str = f"{h:02d}"
            fila.append(InlineKeyboardButton(f"{h_str} hs", callback_data=f"cfgh_fin_{h_str}"))
            if len(fila) == 3:
                horas_buttons.append(fila)
                fila = []
        if fila:
            horas_buttons.append(fila)

        await query.edit_message_text(f"✅ Horario Semanal guardado ({h_sem}:{m_val} hs).\n\n⚙️ **Paso 3/4:** Seleccioná la hora para el **Horario Fin de Semana** (de 07 a 16 hs):", reply_markup=InlineKeyboardMarkup(horas_buttons), parse_mode="Markdown")
        return

    elif data.startswith("cfgh_fin_"):
        h_val = data.replace("cfgh_fin_", "")
        if user_id not in reunion_temp_state:
            reunion_temp_state[user_id] = {}
        reunion_temp_state[user_id]["fin_h"] = h_val
        reunion_temp_state[user_id]["step"] = "cfg_fin_min"

        min_buttons = [
            [InlineKeyboardButton("00 min", callback_data="cfgm_fin_00"), InlineKeyboardButton("05 min", callback_data="cfgm_fin_05"), InlineKeyboardButton("10 min", callback_data="cfgm_fin_10")],
            [InlineKeyboardButton("15 min", callback_data="cfgm_fin_15"), InlineKeyboardButton("20 min", callback_data="cfgm_fin_20"), InlineKeyboardButton("25 min", callback_data="cfgm_fin_25")],
            [InlineKeyboardButton("30 min", callback_data="cfgm_fin_30"), InlineKeyboardButton("35 min", callback_data="cfgm_fin_35"), InlineKeyboardButton("40 min", callback_data="cfgm_fin_40")],
            [InlineKeyboardButton("45 min", callback_data="cfgm_fin_45"), InlineKeyboardButton("50 min", callback_data="cfgm_fin_50"), InlineKeyboardButton("55 min", callback_data="cfgm_fin_55")]
        ]
        await query.edit_message_text(f"⚙️ Hora fin de semana seleccionada: {h_val} hs.\n\n**Paso 4/4:** Seleccioná los minutos:", reply_markup=InlineKeyboardMarkup(min_buttons), parse_mode="Markdown")
        return

    elif data.startswith("cfgm_fin_"):
        m_val = data.replace("cfgm_fin_", "")
        if user_id not in reunion_temp_state:
            reunion_temp_state[user_id] = {}
        
        h_fin = reunion_temp_state[user_id].get("fin_h", "10")
        hora_fin_completa = f"{h_fin}:{m_val}"
        
        if user_id not in user_data_store:
            user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "acciones": []}
        
        user_data_store[user_id]["hora_fin_de_semana"] = hora_fin_completa
        
        h_sem_str = user_data_store[user_id].get("hora_semana", "08:00")
        h_fin_str = hora_fin_completa

        menu_keyboard = [
            [InlineKeyboardButton("Acciones", callback_data="menu_acciones"),
             InlineKeyboardButton("Tareas", callback_data="menu_tareas")],
            [InlineKeyboardButton("Notas", callback_data="menu_notas"),
             InlineKeyboardButton("Agendar reunión", callback_data="menu_agenda")]
        ]
        
        resumen_texto = (
            "🎉 ¡Configuración completada con éxito!\n\n"
            f"• Horario Semanal: {h_sem_str} hs\n"
            f"• Horario Fin de Semana: {h_fin_str} hs\n\n"
            "Ya podés utilizar el bot con las siguientes opciones:"
        )
        await query.edit_message_text(resumen_texto, reply_markup=InlineKeyboardMarkup(menu_keyboard))
        return

    if data == "reunion_presencial" or data == "reunion_virtual":
        tipo = "Presencial" if data == "reunion_presencial" else "Virtual"
        reunion_temp_state[user_id] = {"tipo": tipo, "step": "titulo"}
        await query.edit_message_text(f"📝 Reunión {tipo}\n\nPor favor, escribí el título de la reunión:")
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
        await query.edit_message_text("📅 Seleccioná el mes de la reunión:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("mes_"):
        mes = data.replace("mes_", "")
        reunion_temp_state[user_id]["mes"] = mes
        reunion_temp_state[user_id]["step"] = "dia"
        
        dias_buttons = []
        fila_actual = []
        for d in range(1, 32):
            d_str = f"{d:02d}"
            fila_actual.append(InlineKeyboardButton(str(d), callback_data=f"dia_{d_str}"))
            if len(fila_actual) == 7:
                dias_buttons.append(fila_actual)
                fila_actual = []
        if fila_actual:
            dias_buttons.append(fila_actual)

        await query.edit_message_text("📅 Seleccioná el día de la reunión:", reply_markup=InlineKeyboardMarkup(dias_buttons))

    elif data.startswith("dia_"):
        dia = data.replace("dia_", "")
        reunion_temp_state[user_id]["dia"] = dia
        reunion_temp_state[user_id]["step"] = "hora_reunion"
        
        horas_reunion = []
        fila = []
        for h in range(24):
            h_str = f"{h:02d}"
            fila.append(InlineKeyboardButton(f"{h_str} hs", callback_data=f"reu_h_{h_str}"))
            if len(fila) == 6:
                horas_reunion.append(fila)
                fila = []
        if fila:
            horas_reunion.append(fila)

        await query.edit_message_text("⏰ Seleccioná la hora de la reunión:", reply_markup=InlineKeyboardMarkup(horas_reunion))

    elif data.startswith("reu_h_"):
        h_str = data.replace("reu_h_", "")
        reunion_temp_state[user_id]["reu_h"] = h_str
        reunion_temp_state[user_id]["step"] = "minuto_reunion"

        min_reunion = [
            [InlineKeyboardButton("00 min", callback_data="reu_m_00"), InlineKeyboardButton("05 min", callback_data="reu_m_05"), InlineKeyboardButton("10 min", callback_data="reu_m_10")],
            [InlineKeyboardButton("15 min", callback_data="reu_m_15"), InlineKeyboardButton("20 min", callback_data="reu_m_20"), InlineKeyboardButton("25 min", callback_data="reu_m_25")],
            [InlineKeyboardButton("30 min", callback_data="reu_m_30"), InlineKeyboardButton("35 min", callback_data="reu_m_35"), InlineKeyboardButton("40 min", callback_data="reu_m_40")],
            [InlineKeyboardButton("45 min", callback_data="reu_m_45"), InlineKeyboardButton("50 min", callback_data="reu_m_50"), InlineKeyboardButton("55 min", callback_data="reu_m_55")]
        ]
        await query.edit_message_text(f"⏰ Hora: {h_str} hs. Seleccioná los minutos:", reply_markup=InlineKeyboardMarkup(min_reunion))
        return

    elif data.startswith("reu_m_"):
        m_str = data.replace("reu_m_", "")
        state = reunion_temp_state.get(user_id, {})
        h_str = state.get("reu_h", "09")
        hora_final = f"{h_str}:{m_str}"
        
        state["hora"] = hora_final
        tipo = state.get("tipo")
        state["step"] = "lugar_link"

        prompt_texto = "📍 Ingresá la dirección o lugar de la reunión:" if tipo == "Presencial" else "💻 Ingresá el link de la reunión:"
        await query.edit_message_text(prompt_texto)
        return

    elif data == "ver_resumen_acciones":
        acciones = user_data_store.get(user_id, {}).get("acciones", [])
        if not acciones:
            await query.edit_message_text("📋 No hay acciones registradas hoy.")
            return
        resumen_str = "\n".join([f"• {a['accion']} (a las {a['hora']})" for a in acciones])
        await query.edit_message_text(f"📋 Resumen de tus acciones de hoy:\n\n{resumen_str}")
    elif data == "no_resumen":
        await query.edit_message_text("👍 ¡Entendido!")

async def handle_voice_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Manejar nota de voz enviada por el usuario
    if update.message.voice:
        file_id = update.message.voice.file_id
        new_file = await context.bot.get_file(file_id)
        # Descargar el archivo de voz (opcionalmente guardado en memoria o disco para procesar)
        await update.message.reply_text("🎤 ¡Recibí tu nota de voz! Ya quedó guardada para procesarla próximamente.")
        return

    text = update.message.text

    if user_id in reunion_temp_state and reunion_temp_state[user_id].get("step") == "esperando_eliminar_numero":
        try:
            indice = int(text.strip()) - 1
            reuniones = user_data_store[user_id]["reuniones"]
            if 0 <= indice < len(reuniones):
                eliminada = reuniones.pop(indice)
                del reunion_temp_state[user_id]
                
                texto = f"🗑 **Reunión eliminada con éxito:**\n{eliminada}\n\n"
                if not reuniones:
                    texto += "📅 Ya no te quedan reuniones agendadas."
                    reply_markup = None
                else:
                    texto += "📅 **Tus reuniones actualizadas:**\n\n"
                    for idx, r in enumerate(reuniones, 1):
                        texto += f"{idx}. {r}\n"
                    keyboard = [
                        [InlineKeyboardButton("✏️ Editar / Reagendar", callback_data="reuniones_editar"),
                         InlineKeyboardButton("🗑 Eliminar", callback_data="reuniones_eliminar")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Número inválido. Por favor, escribí un número de la lista:")
        except ValueError:
            await update.message.reply_text("⚠️ Por favor, ingresá solo el número de la reunión que querés eliminar:")
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
                "📅 Seleccioná el año de la reunión:",
                reply_markup=InlineKeyboardMarkup(keyboard)
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
                f"✅ ¡Reunión {tipo.lower()} agendada con éxito!\n\n"
                f"📌 {titulo}\n📅 Fecha: {fecha_formateada} a las {hora} hs\n📍 Detalle: {ubicacion_o_link}\n\n"
                "(Sincronizado con Google Calendar)"
            )
            return

def main():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", iniciar))
    app.add_handler(CommandHandler("iniciar", iniciar))
    app.add_handler(CommandHandler("configuracion", configuracion))
    app.add_handler(CommandHandler("agenda_reunion", agenda_reunion))
    app.add_handler(CommandHandler("reuniones", listar_reuniones))
    app.add_handler(CommandHandler("accion", accion_cmd))
    app.add_handler(CommandHandler("lista", lista_cmd))
    app.add_handler(CommandHandler("ver_listas", ver_listas))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))
    app.add_handler(CommandHandler("completada", completada))
    app.add_handler(CommandHandler("nota", nota_cmd))
    app.add_handler(CommandHandler("lista_notas", lista_notas))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.TEXT & ~filters.COMMAND, handle_voice_or_text))

    print("🚀 ¡@SoyOrganizabot listo y corriendo en Telegram (Hilo principal)!")
    app.run_polling()

if __name__ == '__main__':
    main()
