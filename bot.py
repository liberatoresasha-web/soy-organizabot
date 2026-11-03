import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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
        return # Evita saturar los logs con peticiones web

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌐 Servidor web interno corriendo en el puerto {port}")
    server.serve_forever()

# --- COMANDOS DEL BOT ---

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte a organizar tus tareas y notas. Usá /ayuda para ver las opciones."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Comandos disponibles en @SoyOrganizabot:**\n\n"
        "• /iniciar - Iniciar la conversación y registro\n"
        "• /ayuda - Muestra esta lista de comandos\n"
        "• /configuracion - Permite configurar preferencias\n"
        "• /tareas - Muestra la lista de pendientes\n"
        "• /nueva_tarea - Agrega una tarea nueva\n"
        "• /completada - Finaliza una tarea\n"
        "• /nota - Guarda una nota rápida\n"
        "• /lista_notas - Ver notas guardadas\n"
        "• /recordatorio - Programa un recordatorio\n"
        "• /silencio - Modo silencio / posponer"
    )

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ **Configuración:** Próximamente podrás ajustar tus preferencias desde acá.")

async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Tus pendientes:** No tenés tareas registradas por el momento.")

async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("➕ **Nueva tarea:** Escribí la tarea que querés agregar (próximamente automático).")

async def completada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ **Completar tarea:** Seleccioná la tarea que finalizaste.")

async def nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 **Guardar nota:** Mandame el texto de la nota que querés recordar.")

async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📂 **Tus notas:** Acá verás el listado de tus anotaciones recientes.")

async def recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏰ **Recordatorio:** Configurá cuándo querés recibir un aviso.")

async def silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔕 **Modo silencio:** Avisos matutinos pospuestos.")

def main():
    # Arrancar el servidor web falso antes que nada en un hilo separado
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    # Construir la aplicación del bot
    app = ApplicationBuilder().token(TOKEN).build()

    # Registro de comandos
    app.add_handler(CommandHandler("iniciar", iniciar))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("configuracion", configuracion))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(CommandHandler("nueva_tarea", nueva_tarea))
    app.add_handler(CommandHandler("completada", completada))
    app.add_handler(CommandHandler("nota", nota))
    app.add_handler(CommandHandler("lista_notas", lista_notas))
    app.add_handler(CommandHandler("recordatorio", recordatorio))
    app.add_handler(CommandHandler("silencio", silencio))

    print("🚀 ¡@SoyOrganizabot está listo y funcionando en la nube!")
    app.run_polling()

if __name__ == '__main__':
    main()
