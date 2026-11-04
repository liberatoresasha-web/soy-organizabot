# --- SERVIDOR WEB SECUNDARIO (RENDER) CON SOPORTE OAUTH CALLBACK ---
class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        if path == "/oauth2callback":
            code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0] # user_id de Telegram

            if not code or not state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Error: Falta codigo o estado de autenticacion.")
                return

            try:
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

                user_id = str(state)
                if user_id not in user_data_store:
                    user_data_store[user_id] = {"tareas": [], "listas": {}, "reuniones": [], "notas": []}
                
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
                html_respuesta = "<html><body style='font-family:sans-serif; text-align:center; padding-top:50px;'><h2>¡Cuenta de Google vinculada con éxito!</h2><p>Ya podés cerrar esta pestaña y volver a Telegram con @SoyOrganizabot.</p></body></html>"
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
