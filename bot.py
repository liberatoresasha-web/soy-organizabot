import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Configurar logs para ver qué pasa en la consola
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token directamente configurado para evitar errores
TOKEN = "9006959123:AAGwA8wE4vhFi8-tv0bUvFAnnLnfyi2ZCXQ"

# 1. Comando /iniciar
async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"¡Hola, {user.first_name}! 🤖 Bienvenido a @SoyOrganizabot.\n\n"
        "Estoy listo para ayudarte a organizar tus tareas y notas. Usá /ayuda para ver las opciones."
    )

# 2. Comando /ayuda
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

# 3. Comando /configuracion
async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ **Configuración:** Próximamente podrás ajustar tus preferencias desde acá.")

# 4. Comando /tareas
async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Tus pendientes:** No tenés tareas registradas por el momento.")

# 5. Comando /nueva_tarea
async def nueva_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("➕ **Nueva tarea:** Escribí la tarea que querés agregar (próximamente automático).")

# 6. Comando /completada
async def completada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ **Completar tarea:** Seleccioná la tarea que finalizaste.")

# 7. Comando /nota
async def nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 **Guardar nota:** Mandame el texto de la nota que querés recordar.")

# 8. Comando /lista_notas
async def lista_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📂 **Tus notas:** Acá verás el listado de tus anotaciones recientes.")

# 9. Comando /recordatorio
async def recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏰ **Recordatorio:** Configurá cuándo querés recibir un aviso.")

# 10. Comando /silencio
async def silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔕 **Modo silencio:** Avisos matutinos pospuestos.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Registro de todos los comandos en el bot
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

    print("🚀 ¡@SoyOrganizabot está listo y funcionando en la nube con todos sus comandos!")
    app.run_polling()

if __name__ == '__main__':
    main()
