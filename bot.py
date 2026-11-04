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
                print("Error procesando token OAuth")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Error interno al autenticar")
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
        print("Error crítico en servidor web")
