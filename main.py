"""
ChatFight Auto-Responder Bot
===========================
Bot de Telegram que detecta automáticamente juegos del bot ChatFight
(palabras y operaciones matemáticas en imágenes) y responde automáticamenteizando IA de
util Groq para analizar las imágenes.

Autor: ElJoker63
Repo: https://github.com/ElJoker63/chatfight-bot
"""

import asyncio
import os
import re
import sys
import time
import uuid
import base64
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from groq import Groq

# =============================================================================
# CONFIGURATION
# =============================================================================

load_dotenv()

# Telegram API credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Session string (optional - if absent uses local session file)
SESSION_STRING = os.getenv("SESSION_STRING", "")

# ChatFight configuration
CHATFIGHT_BOT_ID = int(os.getenv("CHATFIGHT_BOT_ID"))
CHATFIGHT_GROUP_ID = int(os.getenv("CHATFIGHT_GROUP_ID"))

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI")

# Groq API Key for AI image analysis
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Captions que identifican los juegos
CAPTION_PALABRA = "Sé el primero en escribir la palabra que aparece en la foto para escalar en la clasificación de minijuegos."
CAPTION_OPERACION = "Sé el primero en escribir el resultado del cálculo en fotos para poder ascender en la tabla de clasificación del minijuego."

# Colección de ChatFight en MongoDB
CHATFIGHT_COLLECTION_NAME = "ChatFight"

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("chatfight-bot")

# =============================================================================
# MONGODB CONNECTION
# =============================================================================

_chatfight_client = None
_chatfight_collection = None

def get_chatfight_collection():
    """Inicializa y retorna la conexión a MongoDB para ChatFight"""
    global _chatfight_client, _chatfight_collection
    
    if _chatfight_client is None:
        _chatfight_client = MongoClient(MONGO_URI)
        _db = _chatfight_client["userdm"]
        _chatfight_collection = _db[CHATFIGHT_COLLECTION_NAME]
        
        # Crear un índice para el documento único de estadísticas
        _chatfight_collection.create_index("type", unique=True)
    
    return _chatfight_collection

def init_chatfight_db():
    """Inicializa la base de datos ChatFight"""
    try:
        collection = get_chatfight_collection()
        _chatfight_client.admin.command('ping')
        log.info("[ChatFight] MongoDB conectado correctamente")
        return True
    except Exception as e:
        log.error(f"[ChatFight] Error de conexión a MongoDB: {e}")
        return False

# =============================================================================
# CHATFIGHT IN-MEMORY STATE
# =============================================================================

chatfight_enabled = False

# =============================================================================
# CHATFIGHT DATABASE FUNCTIONS
# =============================================================================

def load_chatfight_db():
    """Carga el estado desde MongoDB"""
    try:
        collection = get_chatfight_collection()
        doc = collection.find_one({"type": "chatfight_stats"})
        if doc:
            return {
                "enabled": doc.get("enabled", False),
                "stats": doc.get("stats", {})
            }
    except Exception as e:
        log.error(f"[ChatFight] Error de carga desde MongoDB: {e}")
    return {"enabled": False, "stats": {}}

def save_chatfight_db(enabled: bool, stats: dict):
    """Guarda el estado en MongoDB"""
    try:
        collection = get_chatfight_collection()
        collection.update_one(
            {"type": "chatfight_stats"},
            {
                "$set": {
                    "type": "chatfight_stats",
                    "enabled": enabled,
                    "stats": stats,
                    "updated_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
    except Exception as e:
        log.error(f"[ChatFight] Error de guardado en MongoDB: {e}")

# Inicializar el estado desde MongoDB
db_data = load_chatfight_db()
chatfight_enabled = db_data.get("enabled", False)

# Estadísticas por defecto
default_stats = {
    "total_responses": 0,
    "palabra_responses": 0,
    "operacion_responses": 0,
    "errors": 0,
    "last_response": None,
    "history": []
}

chatfight_stats = default_stats.copy()
saved_stats = db_data.get("stats", {})
chatfight_stats.update(saved_stats)

# =============================================================================
# CHATFIGHT GROQ CLIENT
# =============================================================================

class ChatFightProcessor:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
    
    def image_to_base64(self, image_path: str) -> str:
        """Convierte una imagen en base64"""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/jpeg;base64,{encoded_string}"
    
    def get_prompt_for_type(self, tipo: str) -> str:
        """Obtiene el prompt según el tipo de juego"""
        if tipo == "palabra":
            return "Responde SOLO con la palabra que aparece en la imagen, sin puntos, sin comas, sin nada más. Solo la palabra."
        elif tipo == "operacion":
            return "Responde SOLO con el resultado del cálculo matemático de la imagen. Solo el número, sin puntos, sin comas. fijate siempre si el resultado es negativo o positivo, el orden de los factores en restas si altera el producto"
        return "Responde solo con lo que se pide en la imagen."
    
    async def analyze_image(self, image_path: str, tipo: str) -> str:
        """Analiza una imagen y retorna la respuesta con timeout"""
        image_data_url = self.image_to_base64(image_path)
        prompt = self.get_prompt_for_type(tipo)
        
        try:
            # La API de Groq es síncrona, no necesita asyncio.wait_for
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url
                                }
                            }
                        ]
                    }
                ],
                temperature=0.3,
                max_completion_tokens=100,
                top_p=1,
                stream=False,
            )
            
            response = completion.choices[0].message.content or ""
            
            # Limpiar la respuesta
            response = response.strip()
            response = response.replace(".", "").replace(",", "").replace(" ", "")
            
            return response
            
        except Exception as e:
            log.error(f"[ChatFight] Error analyzing image: {e}")
            raise

# =============================================================================
# CHATFIGHT GAME DETECTION
# =============================================================================

def detect_game_type(message) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Detecta el tipo de mensaje del bot ChatFight
    Returns: (is_game, tipo, image_path_or_none)
    """
    try:
        # Verificar que sea del bot ChatFight
        if not message.from_user or message.from_user.id != CHATFIGHT_BOT_ID:
            return False, None, None
        
        # Verificar que sea en el grupo correcto
        if message.chat.id != CHATFIGHT_GROUP_ID:
            return False, None, None
        
        # Verificar caption
        caption = message.caption or ""
        
        # Buscar el tipo de operación matemática
        if "resultado del cálculo" in caption.lower() or "tabla de clasificación" in caption.lower():
            return True, "operacion", None
        
        # Buscar el tipo de palabra
        if "escribir la palabra" in caption.lower() or "escalar en la clasificación" in caption.lower():
            return True, "palabra", None
        
        return False, None, None
        
    except Exception as e:
        log.error(f"[ChatFight] Error de detección del tipo: {e}")
        return False, None, None

# =============================================================================
# CHATFIGHT MESSAGE PROCESSING
# =============================================================================

async def process_chatfight_message(client: Client, message, processor: ChatFightProcessor):
    """
    Procesa un mensaje del bot ChatFight
    """
    global chatfight_stats, chatfight_enabled
    
    log.info(f"[ChatFight] process_chatfight_message iniciado (enabled={chatfight_enabled})")
    
    if not chatfight_enabled:
        log.warning("[ChatFight] ChatFight está desactivado")
        return
    
    try:
        # Detectar el tipo de juego
        is_game, tipo, _ = detect_game_type(message)
        
        log.info(f"[ChatFight] detect_game_type resultado: is_game={is_game}, tipo={tipo}")
        
        if not is_game:
            log.warning("[ChatFight] No se detectó un juego válido")
            return
        
        log.info(f"[ChatFight] Detectado juego tipo: {tipo}")
        
        # Descargar la imagen
        temp_file = f"temp_chatfight_{uuid.uuid4().hex[:8]}.jpg"
        
        try:
            # Descargar según el tipo de media
            downloaded_path = None
            if message.photo:
                log.info(f"[ChatFight] Descargando photo...")
                downloaded_path = await client.download_media(message.photo, file_name=temp_file)
            elif message.document and message.document.mime_type.startswith('image/'):
                log.info(f"[ChatFight] Descargando document...")
                downloaded_path = await client.download_media(message.document, file_name=temp_file)
            else:
                log.warning("[ChatFight] No se encontró media para descargar")
                return
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                log.error(f"[ChatFight] Error: No se pudo descargar la imagen (path={downloaded_path})")
                return
            
            log.info(f"[ChatFight] Imagen descargada: {downloaded_path}")
            
            # Analizar la imagen
            log.info(f"[ChatFight] Analizando imagen con Groq (timeout 30s)...")
            response = await processor.analyze_image(downloaded_path, tipo)
            
            log.info(f"[ChatFight] Respuesta: {response}")
            
            # Responder al mensaje
            log.info(f"[ChatFight] Enviando respuesta...")
            await message.reply(response)
            log.info(f"[ChatFight] Respuesta enviada exitosamente")
            
            # Actualizar las estadísticas
            chatfight_stats["total_responses"] += 1
            if tipo == "palabra":
                chatfight_stats["palabra_responses"] += 1
            else:
                chatfight_stats["operacion_responses"] += 1
            
            chatfight_stats["last_response"] = datetime.now(timezone.utc).isoformat()
            
            # Guardar en el historial
            chatfight_stats["history"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tipo": tipo,
                "response": response
            })
            
            # Mantener el historial limitado a los últimos 100
            if len(chatfight_stats["history"]) > 100:
                chatfight_stats["history"] = chatfight_stats["history"][-100:]
            
            # Guardar en MongoDB
            save_chatfight_db(chatfight_enabled, chatfight_stats)
            
            # Limpiar el archivo temporal
            try:
                os.remove(downloaded_path)
                log.info(f"[ChatFight] Archivo temporal eliminado: {downloaded_path}")
            except Exception as e:
                log.warning(f"[ChatFight] Error eliminando archivo temporal: {e}")
            
        except Exception as e:
            log.error(f"[ChatFight] Error de procesamiento: {e}")
            log.exception("[ChatFight] Traceback:")
            chatfight_stats["errors"] += 1
            save_chatfight_db(chatfight_enabled, chatfight_stats)
            
    except Exception as e:
        log.error(f"[ChatFight] Error general: {e}")
        traceback.print_exc()
        chatfight_stats["errors"] += 1
        save_chatfight_db(chatfight_enabled, chatfight_stats)

# =============================================================================
# CHATFIGHT CONTROL COMMANDS
# =============================================================================

def chatfight_toggle():
    """Activa/desactiva el módulo ChatFight"""
    global chatfight_enabled
    chatfight_enabled = not chatfight_enabled
    save_chatfight_db(chatfight_enabled, chatfight_stats)
    return chatfight_enabled

def get_chatfight_status() -> dict:
    """Obtiene el estado actual del módulo"""
    return {
        "enabled": chatfight_enabled,
        "stats": chatfight_stats.copy()
    }

def get_chatfight_stats_text() -> str:
    """Genera un texto con las estadísticas"""
    stats = chatfight_stats
    
    status_emoji = "✅" if chatfight_enabled else "❌"
    status_text = "ACTIVADO" if chatfight_enabled else "DESACTIVADO"
    
    last_resp = stats.get('last_response') or 'Nunca'
    
    text = f"""🤖 **ChatFight Auto-Responder**

✅ Estado: **{status_text}**

📊 **Estadísticas:**
• Total de respuestas: {stats['total_responses']}
• Palabras encontradas: {stats['palabra_responses']}
• Operaciones calculadas: {stats['operacion_responses']}
• Errores: {stats['errors']}

🕐 Última respuesta: {last_resp}"""
    return text

# =============================================================================
# CHATFIGHT MODULE INITIALIZATION
# =============================================================================

_chatfight_processor = None

def init_chatfight_module(api_key: str):
    """
    Inicializa el módulo ChatFight
    Returns: processor instance
    """
    global _chatfight_processor
    
    log.info(f"[ChatFight] Inicializando módulo ChatFight...")
    log.info(f"[ChatFight] API Key proporcionada: {'Sí' if api_key else 'No'}")
    log.info(f"[ChatFight] CHATFIGHT_BOT_ID: {CHATFIGHT_BOT_ID}")
    log.info(f"[ChatFight] CHATFIGHT_GROUP_ID: {CHATFIGHT_GROUP_ID}")
    
    # Inicializar MongoDB
    init_chatfight_db()
    
    if not api_key:
        log.warning("[ChatFight] Advertencia: No se proporcionó clave API Groq")
        return None
    
    _chatfight_processor = ChatFightProcessor(api_key)
    log.info(f"[ChatFight] Módulo inicializado (Estado: {'Activado' if chatfight_enabled else 'Desactivado'})")
    log.info(f"[ChatFight] Processor creado: {'Sí' if _chatfight_processor else 'No'}")
    return _chatfight_processor

# =============================================================================
# TELEGRAM CLIENT CREATION
# =============================================================================

# Crear el cliente Pyrogram a nivel de módulo para que esté disponible para los handlers
if SESSION_STRING:
    app = Client(
        "chatfight_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING
    )
else:
    app = Client(
        "chatfight_bot",
        api_id=API_ID,
        api_hash=API_HASH
    )

# =============================================================================
# TELEGRAM HANDLERS
# =============================================================================

@app.on_message(filters.chat(CHATFIGHT_GROUP_ID))
async def chatfight_handler(app: Client, message: Message):
    """Procesa mensajes del bot ChatFight"""
    global chatfight_enabled, _chatfight_processor
    
    log.info(f"[ChatFight] Mensaje recibido en grupo {message.chat.id} (enabled={chatfight_enabled})")
    
    # Verificar si está activado
    if not chatfight_enabled:
        log.warning("[ChatFight] Módulo desactivado, ignorando mensaje")
        return
    
    if _chatfight_processor is None:
        log.warning("[ChatFight] Processor no inicializado")
        return
    
    log.info(f"[ChatFight] Processor disponible")
    
    # Verificar que sea del bot ChatFight
    if not message.from_user:
        log.warning("[ChatFight] Mensaje sin usuario")
        return
    
    log.info(f"[ChatFight] Usuario: {message.from_user.id} (esperado: {CHATFIGHT_BOT_ID})")
    
    if message.from_user.id != CHATFIGHT_BOT_ID:
        log.warning(f"[ChatFight] Usuario no es ChatFight bot")
        return
    
    # Verificar caption para detectar juegos
    caption = message.caption or message.text or ""
    
    # Si es un documento, también verificar file_name
    if message.document:
        doc_name = message.document.file_name or ""
        caption = caption + " " + doc_name
    
    # Debug: Mostrar todos los campos relevantes del mensaje
    log.info(f"[ChatFight] --- DEBUG MESSAGE ---")
    log.info(f"[ChatFight] message_id: {message.id}")
    log.info(f"[ChatFight] caption: '{message.caption}'")
    log.info(f"[ChatFight] text: '{message.text}'")
    if message.entities:
        log.info(f"[ChatFight] entities: {[e.type for e in message.entities]}")
    if message.document:
        log.info(f"[ChatFight] doc.file_name: '{message.document.file_name}'")
        log.info(f"[ChatFight] doc.mime_type: '{message.document.mime_type}'")
    log.info(f"[ChatFight] photo: {message.photo is not None}")
    log.info(f"[ChatFight] --- END DEBUG ---")
    
    log.info(f"[ChatFight] Caption completo: {caption[:200]}...")
    
    # Buscar patrones en caption o text
    caption_lower = caption.lower()
    has_resultado = "resultado del cálculo" in caption_lower or "tabla de clasificación" in caption_lower
    has_palabra = "escribir la palabra" in caption_lower or "escalar en la clasificación" in caption_lower
    
    log.info(f"[ChatFight] has_resultado={has_resultado}, has_palabra={has_palabra}")
    
    if not (has_resultado or has_palabra):
        log.warning(f"[ChatFight] Caption no coincide con juego (caption: '{caption[:100]}')")
        return
    
    # Verificar que tenga media
    has_photo = message.photo is not None
    has_doc = message.document is not None and message.document.mime_type.startswith('image/')
    log.info(f"[ChatFight] Photo: {has_photo}, Document: {has_doc}")
    
    if not has_photo and not has_doc:
        log.warning("[ChatFight] No tiene media")
        return
    
    log.info(f"[ChatFight] Mensaje detectado: {message.id}, procesando...")
    asyncio.create_task(process_chatfight_message(app, message, _chatfight_processor))


# Commands: -cf (status), -cft (toggle), -ping

@app.on_message(filters.command("ping", prefixes=["-"]))
async def ping_me(_, message: Message):
    await message.delete()
    start = time.time()
    m = await message.reply_text("pong…")
    dt = (time.time() - start) * 1000
    msg = await m.edit_text(f"pong {dt:.0f} ms")
    await asyncio.sleep(3)
    await msg.delete()


@app.on_message(filters.command("help", prefixes=["."]))
async def help_cmd(_, message: Message):
    """Muestra la ayuda de comandos"""
    await message.delete()
    help_text = """🤖 **ChatFight Auto-Responder**

🟢 **Comandos:**
• `-cf` - Ver estado y estadísticas
• `-cft` - Activar/Desactivar
• `-ping` - Verificar bot online"""
    msg = await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(30)
    await msg.delete()


# ChatFight control commands
@app.on_message(filters.command("cf", prefixes=["-"]))
async def chatfight_status(_, message: Message):
    """Muestra el estado del módulo ChatFight"""
    await message.delete()
    status_text = get_chatfight_stats_text()
    msg = await message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(30)
    await msg.delete()


@app.on_message(filters.command("cft", prefixes=["-"]))
async def chatfight_toggle_cmd(_, message: Message):
    """Activa o desactiva el módulo ChatFight"""
    await message.delete()
    new_state = chatfight_toggle()
    state_text = "✅ Activado" if new_state else "❌ Desactivado"
    msg = await message.reply_text(f"ChatFight {state_text}")
    await asyncio.sleep(5)
    await msg.delete()

# =============================================================================
# MAIN
# =============================================================================

async def main():
    log.info("Starting ChatFight Bot...")
    
    # Conectar a MongoDB
    if not init_chatfight_db():
        log.warning("MongoDB no disponible. Continuando sin persistencia.")
    
    # Iniciar el cliente (ya creado a nivel de módulo)
    try:
        await app.start()
    except Exception as e:
        log.error(f"Error iniciando el cliente: {e}")
        return
    
    log.info("ChatFight Bot iniciado correctamente!")
    
    # Inicializar módulo ChatFight con Groq
    if GROQ_API_KEY:
        init_chatfight_module(GROQ_API_KEY)
    else:
        log.warning("[ChatFight] GROQ_API_KEY no configurado. El módulo ChatFight no funcionará.")
    
    # Mantener el bot corriendo
    await app.idle()
    await app.stop()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
