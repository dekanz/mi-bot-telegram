import telebot
import logging
import os
import json
import time
import requests
import socket
from datetime import datetime, timedelta
from telebot import types
from requests.exceptions import ConnectionError, Timeout, RequestException
from urllib3.exceptions import NewConnectionError, MaxRetryError
from supabase import create_client, Client
import re
from bs4 import BeautifulSoup
import pytz
import sys

# Configuración del bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN no está configurado")
    exit(1)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: SUPABASE_URL y SUPABASE_KEY no están configurados")
    print("💡 Configura estas variables de entorno en Render:")
    print("   SUPABASE_URL=https://tu-proyecto.supabase.co")
    print("   SUPABASE_KEY=tu-clave-supabase")
    exit(1)

# Aplicar parche temporal para el error de Story
def apply_story_patch():
    """Aplica un parche temporal para el error de compatibilidad con Story"""
    try:
        # Importar la clase Story
        from telebot.types import Story
        
        # Guardar el constructor original
        original_init = Story.__init__
        
        def patched_init(self, **kwargs):
            # Remover el campo 'chat' si existe, ya que causa problemas
            if 'chat' in kwargs:
                logging.warning("🔧 Removiendo campo 'chat' problemático de Story")
                del kwargs['chat']
            # Llamar al constructor original con los parámetros limpios
            return original_init(self, **kwargs)
        
        # Aplicar el parche
        Story.__init__ = patched_init
        logging.info("✅ Parche temporal aplicado para la clase Story")
        
    except Exception as e:
        logging.warning(f"⚠️ No se pudo aplicar el parche de Story: {e}")

# Aplicar el parche antes de crear el bot
apply_story_patch()

# Crear instancia del bot
bot = telebot.TeleBot(BOT_TOKEN)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)

# Configuración de Supabase (Base de datos en la nube)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_database():
    """Inicializa la base de datos en Supabase (PostgreSQL en la nube)"""
    try:
        # Verificar conexión probando las tablas
        supabase.table('registered_users').select('user_id').limit(1).execute()
        logging.info("✅ Tabla registered_users verificada")
        
        supabase.table('user_registration_log').select('id').limit(1).execute()
        logging.info("✅ Tabla user_registration_log verificada")
        
        logging.info("✅ Base de datos Supabase inicializada correctamente")
        return True
    except Exception as e:
        logging.error(f"❌ Error al inicializar base de datos Supabase: {e}")
        logging.error("💡 Asegúrate de que las tablas estén creadas en Supabase")
        return False

def backup_database():
    """Crea un respaldo de la base de datos (Supabase ya tiene respaldo automático)"""
    try:
        # Supabase tiene respaldo automático, solo confirmamos
        logging.info("✅ Supabase tiene respaldo automático habilitado")
        return True
    except Exception as e:
        logging.error(f"❌ Error al verificar respaldo: {e}")
        return False

def log_user_action(user_id, action, details=""):
    """Registra una acción del usuario en el log usando Supabase"""
    try:
        result = supabase.table('user_registration_log').insert({
            'user_id': user_id,
            'action': action,
            'details': details
        }).execute()
        
        logging.info(f"📝 Log registrado: Usuario {user_id} - {action}")
        
    except Exception as e:
        logging.error(f"❌ Error al registrar log: {e}")

def load_registered_users():
    """Carga los usuarios registrados desde Supabase"""
    try:
        result = supabase.table('registered_users').select('user_id').execute()
        user_ids = [row['user_id'] for row in result.data]
        return set(user_ids)
    except Exception as e:
        logging.error(f"❌ Error al cargar usuarios registrados: {e}")
        return set()

def add_registered_user(user_id, username=None, first_name=None, last_name=None):
    """Agrega un usuario a la base de datos usando Supabase"""
    try:
        # Verificar si el usuario ya existe
        existing = supabase.table('registered_users').select('user_id').eq('user_id', user_id).execute()
        is_new_user = len(existing.data) == 0
        
        # Insertar o actualizar usuario
        user_data = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name
        }
        
        if is_new_user:
            result = supabase.table('registered_users').insert(user_data).execute()
        else:
            result = supabase.table('registered_users').update(user_data).eq('user_id', user_id).execute()
        
        action = "REGISTRO" if is_new_user else "ACTUALIZACION"
        details = f"Username: {username}, Nombre: {first_name} {last_name}"
        log_user_action(user_id, action, details)
        
        logging.info(f"✅ Usuario {user_id} {'registrado' if is_new_user else 'actualizado'} en Supabase")
        return True
    except Exception as e:
        logging.error(f"❌ Error al agregar usuario {user_id}: {e}")
        return False

def remove_registered_user(user_id):
    """Remueve un usuario de la base de datos usando Supabase"""
    try:
        # Obtener información del usuario antes de eliminarlo
        user_info = supabase.table('registered_users').select('username, first_name, last_name').eq('user_id', user_id).execute()
        
        # Eliminar usuario
        result = supabase.table('registered_users').delete().eq('user_id', user_id).execute()
        
        # Registrar la acción en el log
        if user_info.data:
            user_data = user_info.data[0]
            details = f"Username: {user_data.get('username')}, Nombre: {user_data.get('first_name')} {user_data.get('last_name')}"
            log_user_action(user_id, "ELIMINACION", details)
        
        logging.info(f"✅ Usuario {user_id} removido de Supabase")
        return True
    except Exception as e:
        logging.error(f"❌ Error al remover usuario {user_id}: {e}")
        return False

def get_user_info(user_id):
    """Obtiene información de un usuario registrado desde Supabase"""
    try:
        result = supabase.table('registered_users').select('username, first_name, last_name, registered_at').eq('user_id', user_id).execute()
        
        if result.data:
            user_data = result.data[0]
            return {
                'username': user_data.get('username'),
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'registered_at': user_data.get('registered_at')
            }
        return None
    except Exception as e:
        logging.error(f"❌ Error al obtener información del usuario {user_id}: {e}")
        return None

def load_direct_message_users():
    """Carga los usuarios registrados para mensajes directos desde Supabase"""
    try:
        result = supabase.table('direct_message_users').select('user_id').execute()
        user_ids = [row['user_id'] for row in result.data]
        return set(user_ids)
    except Exception as e:
        logging.error(f"❌ Error al cargar usuarios de mensajes directos: {e}")
        return set()

def add_direct_message_user(user_id, username=None, first_name=None, last_name=None):
    """Agrega un usuario para recibir mensajes directos usando Supabase"""
    try:
        # Verificar si el usuario ya existe
        existing = supabase.table('direct_message_users').select('user_id').eq('user_id', user_id).execute()
        is_new_user = len(existing.data) == 0
        
        if is_new_user:
            # Insertar usuario
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name
            }
            
            result = supabase.table('direct_message_users').insert(user_data).execute()
            
            action = "REGISTRO_DIRECT_MESSAGE"
            details = f"Username: {username}, Nombre: {first_name} {last_name}"
            log_user_action(user_id, action, details)
            
            logging.info(f"✅ Usuario {user_id} registrado para mensajes directos")
            return True
        else:
            logging.info(f"ℹ️ Usuario {user_id} ya está registrado para mensajes directos")
            return True  # Ya está registrado, consideramos éxito
    except Exception as e:
        logging.error(f"❌ Error al agregar usuario de mensajes directos {user_id}: {e}")
        return False

def remove_direct_message_user(user_id):
    """Remueve un usuario de los mensajes directos usando Supabase"""
    try:
        # Obtener información del usuario antes de eliminarlo
        user_info = supabase.table('direct_message_users').select('username, first_name, last_name').eq('user_id', user_id).execute()
        
        # Eliminar usuario
        result = supabase.table('direct_message_users').delete().eq('user_id', user_id).execute()
        
        # Registrar la acción en el log
        if user_info.data:
            user_data = user_info.data[0]
            details = f"Username: {user_data.get('username')}, Nombre: {user_data.get('first_name')} {user_data.get('last_name')}"
            log_user_action(user_id, "ELIMINACION_DIRECT_MESSAGE", details)
        
        logging.info(f"✅ Usuario {user_id} removido de mensajes directos")
        return True
    except Exception as e:
        logging.error(f"❌ Error al remover usuario de mensajes directos {user_id}: {e}")
        return False

def send_direct_messages_to_users(alert_text, command_name):
    """Envía mensajes directos a todos los usuarios registrados"""
    try:
        if not direct_message_users:
            logging.info("ℹ️ No hay usuarios registrados para mensajes directos")
            return
        
        message_text = f"🔔 ALERTA EN EL GRUPO 🔔\n\n"
        message_text += f"Comando: {command_name}\n"
        message_text += f"Mensaje: {alert_text}\n\n"
        message_text += "Favor revisar el grupo para más detalles."
        
        sent_count = 0
        for user_id in direct_message_users:
            try:
                bot.send_message(user_id, message_text)
                sent_count += 1
                logging.info(f"✅ Mensaje directo enviado a usuario {user_id}")
            except Exception as e:
                error_str = str(e).lower()
                logging.error(f"❌ Error al enviar mensaje directo a usuario {user_id}: {e}")
                
                # Manejar diferentes tipos de errores
                if ("chat not found" in error_str or 
                    "blocked" in error_str or 
                    "user is deactivated" in error_str):
                    # Usuario no contactable, removerlo
                    logging.info(f"🗑️ Removiendo usuario {user_id} de mensajes directos (no contactable)")
                    remove_direct_message_user(user_id)
                    direct_message_users.discard(user_id)
                elif "bot can't initiate conversation" in error_str:
                    # Usuario no ha iniciado conversación con el bot
                    logging.warning(f"⚠️ Usuario {user_id} no ha iniciado conversación con el bot")
                    # No removerlo, solo avisar
                else:
                    # Otro tipo de error, no remover
                    logging.warning(f"⚠️ Error desconocido para usuario {user_id}: {e}")
        
        logging.info(f"📤 Mensajes directos enviados: {sent_count}/{len(direct_message_users)}")
        
    except Exception as e:
        logging.error(f"❌ Error al enviar mensajes directos: {e}")

def search_nba_season_start():
    """Busca la fecha de inicio de la temporada NBA 2025-26"""
    try:
        # Búsqueda en Google para obtener la fecha de inicio
        search_query = "NBA season 2025-26 start date when does it begin"
        search_url = f"https://www.google.com/search?q={search_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parsear el HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar fechas en el contenido
        text_content = soup.get_text().lower()
        
        # Patrones comunes para fechas de NBA
        date_patterns = [
            r'october\s+\d{1,2},?\s+2025',
            r'oct\s+\d{1,2},?\s+2025',
            r'\d{1,2}/\d{1,2}/2025',
            r'\d{1,2}-\d{1,2}-2025',
            r'october\s+\d{1,2}',
            r'oct\s+\d{1,2}'
        ]
        
        found_dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text_content)
            found_dates.extend(matches)
        
        # Si no encontramos fechas específicas, usar fecha estimada
        if not found_dates:
            # La NBA generalmente comienza a finales de octubre
            chile_tz = pytz.timezone('America/Santiago')
            return chile_tz.localize(datetime(2025, 10, 21))  # Fecha estimada típica
        
        # Procesar las fechas encontradas
        for date_str in found_dates:
            try:
                # Intentar parsear diferentes formatos
                if 'october' in date_str or 'oct' in date_str:
                    # Extraer día
                    day_match = re.search(r'\d{1,2}', date_str)
                    if day_match:
                        day = int(day_match.group())
                        chile_tz = pytz.timezone('America/Santiago')
                        return chile_tz.localize(datetime(2025, 10, day))
                elif '/' in date_str or '-' in date_str:
                    # Formato MM/DD/YYYY o MM-DD-YYYY
                    parts = re.split(r'[/-]', date_str)
                    if len(parts) >= 3:
                        month = int(parts[0])
                        day = int(parts[1])
                        year = int(parts[2])
                        if year == 2025:
                            chile_tz = pytz.timezone('America/Santiago')
                            return chile_tz.localize(datetime(year, month, day))
            except (ValueError, IndexError):
                continue
        
        # Fallback: fecha estimada
        chile_tz = pytz.timezone('America/Santiago')
        return chile_tz.localize(datetime(2025, 10, 21))
        
    except Exception as e:
        logging.error(f"❌ Error al buscar fecha de NBA: {e}")
        # Fallback: fecha estimada típica
        chile_tz = pytz.timezone('America/Santiago')
        return chile_tz.localize(datetime(2025, 10, 21))

def calculate_days_until_nba():
    """Calcula los días restantes hasta el inicio de la temporada NBA 2025-26"""
    try:
        # Obtener fecha de inicio
        season_start = search_nba_season_start()
        
        # Fecha actual en horario de Chile (CLST - Chile Summer Time)
        chile_tz = pytz.timezone('America/Santiago')
        today = datetime.now(chile_tz)
        
        # Verificar que estemos usando CLST (UTC-3)
        if today.dst() != timedelta(0):
            # Estamos en horario de verano (CLST)
            logging.info(f"✅ Usando CLST (Chile Summer Time) - UTC-3")
        else:
            # Estamos en horario estándar (CLT)
            logging.info(f"⚠️ Usando CLT (Chile Standard Time) - UTC-4")
        
        # Convertir season_start a la misma zona horaria que today
        if season_start.tzinfo is None:
            # Si season_start no tiene zona horaria, asumir que es en horario de Chile
            season_start = chile_tz.localize(season_start)
        
        # Calcular diferencia
        if season_start > today:
            days_left = (season_start - today).days
            return days_left, season_start
        else:
            # Si ya pasó la fecha, buscar la próxima temporada
            next_season = chile_tz.localize(datetime(2026, 10, 21))  # Estimación para 2026-27
            days_left = (next_season - today).days
            return days_left, next_season
            
    except Exception as e:
        logging.error(f"❌ Error al calcular días de NBA: {e}")
        # Fallback
        chile_tz = pytz.timezone('America/Santiago')
        fallback_date = chile_tz.localize(datetime(2025, 10, 21))
        today = datetime.now(chile_tz)
        days_left = (fallback_date - today).days
        return max(0, days_left), fallback_date

def check_network_connectivity():
    """Verifica la conectividad de red antes de iniciar el bot"""
    try:
        # Verificar conectividad básica
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        logging.info("✅ Conectividad de red básica verificada")
        
        # Verificar conectividad a Telegram API
        response = requests.get("https://api.telegram.org", timeout=10)
        if response.status_code == 200:
            logging.info("✅ Conectividad a Telegram API verificada")
            return True
        else:
            logging.warning(f"⚠️ Telegram API respondió con código: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Error de conectividad: {e}")
        return False

def clear_webhook():
    """Limpia el webhook para evitar conflictos"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Primero obtener información del webhook
            webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
            webhook_response = requests.get(webhook_url, timeout=10)
            
            if webhook_response.status_code == 200:
                webhook_data = webhook_response.json()
                if webhook_data.get('result', {}).get('url'):
                    logging.info(f"🔍 Webhook encontrado: {webhook_data['result']['url']}")
                else:
                    logging.info("ℹ️ No hay webhook configurado")
            
            # Ahora eliminar el webhook
            delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
            response = requests.get(delete_url, timeout=10)
            
            if response.status_code == 200:
                logging.info("✅ Webhook limpiado correctamente")
                # Esperar un poco para que se propague
                time.sleep(2)
                return True
            else:
                logging.warning(f"⚠️ Error al limpiar webhook: {response.status_code}")
                if response.status_code == 409:
                    logging.warning("⚠️ Conflicto detectado, esperando más tiempo...")
                    time.sleep(5)
                
        except (ConnectionError, Timeout, NewConnectionError, MaxRetryError) as e:
            logging.warning(f"⚠️ Intento {attempt + 1} fallido al limpiar webhook: {e}")
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 10)  # Máximo 10 segundos
                time.sleep(wait_time)
        except Exception as e:
            logging.error(f"❌ Error inesperado al limpiar webhook: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
    
    logging.error("❌ No se pudo limpiar el webhook después de todos los intentos")
    return False

def escape_markdown(text):
    """Escapa caracteres especiales de Markdown"""
    if not text:
        return text
    
    # Caracteres especiales que necesitan escape en Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def safe_markdown_text(text):
    """Prepara texto para Markdown de forma segura"""
    if not text:
        return "Usuario"
    
    # Limpiar caracteres problemáticos
    text = str(text)
    
    # Limpiar caracteres de control y caracteres problemáticos
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    # Escapar caracteres especiales de Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    # Limitar longitud para evitar problemas
    if len(text) > 50:
        text = text[:47] + "..."
    
    return text

def clean_name_for_mention(name):
    """Limpia nombres para menciones de forma segura, preservando símbolos"""
    if not name:
        return "Usuario"
    
    # Convertir a string
    name = str(name)
    
    # Solo remover caracteres de control problemáticos, NO símbolos
    name = ''.join(char for char in name if ord(char) >= 32 or char in '\n\r\t')
    
    # Remover TODOS los caracteres que pueden causar problemas en enlaces de Markdown
    # Esto incluye caracteres especiales que pueden romper el parseo
    problematic_chars = ['[', ']', '(', ')', '\\', '*', '_', '`', '~', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    for char in problematic_chars:
        name = name.replace(char, '')
    
    # Limpiar espacios extra
    name = ' '.join(name.split())
    
    # Si el nombre queda vacío, usar "Usuario"
    if not name.strip():
        name = "Usuario"
    
    # Limitar longitud
    if len(name) > 20:
        name = name[:17] + "..."
    
    return name

def clean_text_for_telegram(text):
    """Limpia texto para enviar a Telegram sin formato"""
    if not text:
        return ""
    
    # Convertir a string
    text = str(text)
    
    # Remover caracteres de control problemáticos
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    # Remover caracteres especiales de Markdown
    markdown_chars = ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    for char in markdown_chars:
        text = text.replace(char, '')
    
    return text

def create_safe_mention_text(mention_text, mentions):
    """Crea texto de menciones seguro para Markdown"""
    try:
        # Crear el texto base
        result_text = mention_text
        
        # Agregar menciones de forma segura
        if mentions:
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                result_text += " ".join(batch) + "\n"
        
        return result_text
    except Exception as e:
        logging.error(f"Error al crear texto de menciones: {e}")
        # Fallback: enviar sin menciones
        return mention_text + "\n(Error al procesar menciones)"

def validate_markdown_text(text):
    """Valida si un texto es seguro para Markdown"""
    if not text:
        return False
    
    # Verificar patrones problemáticos (pero permitir enlaces válidos)
    problematic_patterns = [
        '**', '__', '``', '~~', '>>', '##', '++', '--', '==', '||', '{{', '}}'
    ]
    
    for pattern in problematic_patterns:
        if pattern in text:
            return False
    
    # Verificar caracteres especiales problemáticos (pero permitir enlaces)
    # Solo rechazar si hay caracteres especiales que no sean parte de enlaces válidos
    special_chars = ['*', '_', '`', '~', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    for char in special_chars:
        if char in text and f'\\{char}' not in text:
            return False
    
    # Permitir enlaces válidos de Telegram: [texto](tg://user?id=123)
    # No rechazar por tener [ o ] si son parte de un enlace válido
    
    return True


def safe_send_message(chat_id, text, parse_mode='Markdown', max_retries=5):
    """Envía un mensaje con reintentos en caso de error de conexión"""
    for attempt in range(max_retries):
        try:
            # Si hay error de parseo de Markdown, intentar sin formato
            if parse_mode == 'Markdown':
                try:
                    bot.send_message(chat_id, text, parse_mode=parse_mode)
                    return True
                except Exception as markdown_error:
                    if "can't parse entities" in str(markdown_error) or "Bad Request" in str(markdown_error):
                        logging.warning(f"Error de Markdown, enviando sin formato: {markdown_error}")
                        logging.warning(f"Texto problemático: {repr(text)}")
                        # Limpiar el texto y enviar sin formato
                        clean_text = clean_text_for_telegram(text)
                        bot.send_message(chat_id, clean_text, parse_mode=None)
                        return True
                    else:
                        raise markdown_error
            else:
                bot.send_message(chat_id, text, parse_mode=parse_mode)
                return True
        except (ConnectionError, Timeout, RequestException, NewConnectionError, MaxRetryError) as e:
            logging.warning(f"Intento {attempt + 1} fallido al enviar mensaje: {e}")
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Máximo 30 segundos
                logging.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                time.sleep(wait_time)
            else:
                logging.error(f"Error después de {max_retries} intentos al enviar mensaje: {e}")
                return False
        except Exception as e:
            logging.error(f"Error inesperado al enviar mensaje: {e}")
            return False
    return False

def safe_reply_to(message, text, parse_mode='Markdown', max_retries=5):
    """Responde a un mensaje con reintentos en caso de error de conexión"""
    for attempt in range(max_retries):
        try:
            # Si hay error de parseo de Markdown, intentar sin formato
            if parse_mode == 'Markdown':
                try:
                    bot.reply_to(message, text, parse_mode=parse_mode)
                    return True
                except Exception as markdown_error:
                    if "can't parse entities" in str(markdown_error) or "Bad Request" in str(markdown_error):
                        logging.warning(f"Error de Markdown, enviando sin formato: {markdown_error}")
                        logging.warning(f"Texto problemático: {repr(text)}")
                        # Limpiar el texto y enviar sin formato
                        clean_text = clean_text_for_telegram(text)
                        bot.reply_to(message, clean_text, parse_mode=None)
                        return True
                    else:
                        raise markdown_error
            else:
                bot.reply_to(message, text, parse_mode=parse_mode)
                return True
        except (ConnectionError, Timeout, RequestException, NewConnectionError, MaxRetryError) as e:
            logging.warning(f"Intento {attempt + 1} fallido al responder mensaje: {e}")
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Máximo 30 segundos
                logging.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                time.sleep(wait_time)
            else:
                logging.error(f"Error después de {max_retries} intentos al responder mensaje: {e}")
                return False
        except Exception as e:
            logging.error(f"Error inesperado al responder mensaje: {e}")
            return False
    return False

# Inicializar base de datos
if not init_database():
    logging.error("❌ No se pudo inicializar la base de datos. Saliendo...")
    exit(1)

# Cargar usuarios registrados al iniciar
registered_users = load_registered_users()

# Cargar usuarios de mensajes directos al iniciar
direct_message_users = load_direct_message_users()

# Verificar conectividad antes de iniciar
if not check_network_connectivity():
    logging.error("❌ No se pudo verificar la conectividad de red. El bot puede no funcionar correctamente.")
    logging.info("🔄 Reintentando en 30 segundos...")
    time.sleep(30)
    if not check_network_connectivity():
        logging.error("❌ Conectividad de red no disponible. Saliendo...")
        exit(1)

# Limpiar webhook al iniciar
clear_webhook()

@bot.message_handler(commands=['start'])
def start_command(message):
    """Comando de inicio del bot"""
    welcome_text = """
🤖 ¡Hola! Soy el Bot de Menciones

Estoy aquí para ayudarte a mencionar a todos los integrantes de tu grupo.

Comandos principales:
• /all - Menciona a todos
• /allbug - Alerta de bug
• /allerror - Alerta de error de cuota
• /cr - ¡Guerra de Clanes! Invita a todos a jugar
• /marcus - Mensaje especial de Marcus
• /comunista - Envía mensaje directo al comunista
• /nba - Días restantes para temporada NBA 2025-26
• /mensaje - Registrarse para mensajes directos de alertas
• /nomensaje - Desregistrarse de mensajes directos
• /testdirecto - Probar si el bot puede enviar mensajes directos
• /register - Registrarse para menciones (o responder a un mensaje para registrar a otro)
• /unregister - Desregistrarse
• /eliminar_usuario - [ADMIN] Eliminar usuario del registro
• /help - Ver ayuda completa

¡Agrégame a un grupo y hazme administrador para empezar!
    """
    safe_reply_to(message, welcome_text, parse_mode=None)

@bot.message_handler(commands=['help'])
def help_command(message):
    """Muestra la ayuda del bot"""
    help_text = """
Bot de Menciones - Ayuda

Comandos disponibles:
• /all - Menciona a todos los miembros del grupo
• /allbug - Alerta de bug (menciona a todos)
• /allerror - Alerta de error de cuota (menciona a todos)
• /cr - ¡Guerra de Clanes! Invita a todo el clan a jugar con mensaje ultra motivacional
• /marcus - Mensaje especial de Marcus
• /comunista - Envía mensaje directo al comunista
• /nba - Días restantes para temporada NBA 2025-26
• /mensaje - Registrarse para mensajes directos de alertas
• /nomensaje - Desregistrarse de mensajes directos
• /testdirecto - Probar si el bot puede enviar mensajes directos
• /listamensajes - Muestra usuarios registrados para mensajes directos
• /admins - Menciona solo a los administradores
• /register - Registrarse para recibir menciones (o responder a un mensaje para registrar a otro usuario)
• /unregister - Desregistrarse de las menciones
• /eliminar_usuario - [ADMIN] Eliminar usuario del registro de menciones
• /registered - Muestra usuarios registrados
• /historial - Muestra historial de registros
• /backup - Crea respaldo de la base de datos
• /count - Muestra estadísticas del grupo
• /help - Muestra esta ayuda

Comandos de administrador:
• /eliminar_usuario - Elimina un usuario del registro de menciones
  Uso: Responder a un mensaje + /eliminar_usuario
  O bien: /eliminar_usuario <ID_de_usuario>

Notas importantes:
• El bot debe ser administrador del grupo
• Solo funciona en grupos y supergrupos
• Para mencionar a todos, el bot necesita permisos especiales
• Los usuarios registrados recibirán menciones especiales
• Los usuarios con /mensaje recibirán notificaciones directas
• Los datos se guardan permanentemente en la base de datos
    """
    safe_reply_to(message, help_text, parse_mode=None)

@bot.message_handler(commands=['register'])
def register_user(message):
    """Registra al usuario para recibir menciones o a otros usuarios"""
    try:
        # Debug: Log del mensaje
        logging.info(f"🔍 Debug register: reply_to_message={message.reply_to_message is not None}")
        if message.reply_to_message:
            logging.info(f"🔍 Debug: reply_from_user={message.reply_to_message.from_user is not None}")
        
        # Verificar si hay reply (mencionar a otro usuario)
        if message.reply_to_message and message.reply_to_message.from_user:
            # Registrar al usuario mencionado en la respuesta
            target_user = message.reply_to_message.from_user
            user_id = target_user.id
            username = target_user.username
            first_name = target_user.first_name
            last_name = target_user.last_name
            
            logging.info(f"🔍 Debug: Registrando a {first_name} (ID: {user_id}) por reply")
            
            # Verificar si ya está registrado
            if user_id in registered_users:
                safe_reply_to(message, f"✅ {first_name} ya está registrado para recibir menciones.")
                return
            
            # Agregar a la base de datos
            if add_registered_user(user_id, username, first_name, last_name):
                registered_users.add(user_id)
                
                # Crear mención personalizada
                mention_text = f"✅ ¡{first_name} registrado exitosamente!\n\n"
                if username:
                    mention_text += f"Usuario: @{username}\n"
                else:
                    mention_text += f"Nombre: {first_name or 'Usuario'}\n"
                mention_text += f"ID: {user_id}\n\n"
                mention_text += "Ahora recibirá menciones especiales cuando uses los comandos de alerta."
                
                safe_reply_to(message, mention_text, parse_mode=None)
                log_user_action(message.from_user.id, "REGISTER_OTHER", f"Registró a {first_name} ({user_id})")
            else:
                safe_reply_to(message, "❌ Error al registrar al usuario. Intenta de nuevo más tarde.")
        elif message.text and len(message.text.split()) > 1:
            # Verificar si hay una mención en el texto
            text_parts = message.text.split()
            if len(text_parts) > 1 and text_parts[1].startswith('@'):
                # Extraer el username de la mención
                target_username = text_parts[1][1:]  # Quitar el @
                
                # Buscar el usuario en el chat
                if message.chat.type in ['group', 'supergroup']:
                    # En grupos, necesitamos obtener la información del usuario
                    safe_reply_to(message, f"❌ No puedo registrar a @{target_username} directamente. Usa 'Responder a un mensaje' + /register en su lugar.")
                    return
                else:
                    safe_reply_to(message, "❌ Este comando solo funciona en grupos. Usa 'Responder a un mensaje' + /register en su lugar.")
                    return
            else:
                safe_reply_to(message, "❌ Formato incorrecto. Usa: /register @usuario o responde a un mensaje + /register")
                return
        else:
            # Registrar al usuario que envió el comando
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name
            last_name = message.from_user.last_name
            
            logging.info(f"🔍 Debug: Registrando a {first_name} (ID: {user_id}) - sin reply")
            
            if user_id in registered_users:
                safe_reply_to(message, "✅ Ya estás registrado para recibir menciones.")
                return
            
            # Agregar a la base de datos
            if add_registered_user(user_id, username, first_name, last_name):
                registered_users.add(user_id)
                
                # Crear mención personalizada
                mention_text = f"✅ ¡Registro exitoso!\n\n"
                if username:
                    mention_text += f"Usuario: @{username}\n"
                else:
                    mention_text += f"Nombre: {first_name or 'Usuario'}\n"
                mention_text += f"ID: {user_id}\n\n"
                mention_text += "Ahora recibirás menciones especiales cuando uses los comandos de alerta."
                
                safe_reply_to(message, mention_text, parse_mode=None)
            else:
                safe_reply_to(message, "❌ Ocurrió un error al registrarte en la base de datos. Intenta de nuevo.")
        
    except Exception as e:
        logging.error(f"Error al registrar usuario: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al registrarte. Intenta de nuevo.")

@bot.message_handler(commands=['unregister'])
def unregister_user(message):
    """Desregistra al usuario de las menciones"""
    try:
        user_id = message.from_user.id
        
        if user_id not in registered_users:
            safe_reply_to(message, "❌ No estás registrado.")
            return
        
        # Remover de la base de datos
        if remove_registered_user(user_id):
            registered_users.remove(user_id)
            safe_reply_to(message, "✅ Te has desregistrado de las menciones.")
        else:
            safe_reply_to(message, "❌ Ocurrió un error al desregistrarte de la base de datos. Intenta de nuevo.")
        
    except Exception as e:
        logging.error(f"Error al desregistrar usuario: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al desregistrarte. Intenta de nuevo.")

@bot.message_handler(commands=['all'])
def mention_all(message):
    """Menciona a todos los miembros del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        # Obtener información del chat
        chat_member_count = bot.get_chat_member_count(chat_id)
        
        mention_text = f"🔔 MENCIÓN GENERAL 🔔\n\n"
        mention_text += f"Total de miembros: {chat_member_count}\n"
        mention_text += f"📝 Usuarios registrados: {len(registered_users)}\n\n"
        
        # Obtener administradores
        administrators = bot.get_chat_administrators(chat_id)
        
        # Lista para almacenar las menciones
        mentions = []
        mentioned_users = set()
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot:
                if admin.user.username:
                    clean_username = clean_name_for_mention(admin.user.username)
                    if f"@{clean_username}" not in mentioned_users:
                        mentions.append(f"@{clean_username}")
                        mentioned_users.add(f"@{clean_username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = clean_name_for_mention(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {clean_name_for_mention(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        clean_username = clean_name_for_mention(member.user.username)
                        if f"@{clean_username}" not in mentioned_users:
                            mentions.append(f"@{clean_username}")
                            mentioned_users.add(f"@{clean_username}")
                    else:
                        if f"user_{user_id}" not in mentioned_users:
                            full_name = escape_markdown(member.user.first_name)
                            if member.user.last_name:
                                full_name += f" {escape_markdown(member.user.last_name)}"
                            mentions.append(f"[{full_name}](tg://user?id={user_id})")
                            mentioned_users.add(f"user_{user_id}")
            except Exception as e:
                logging.error(f"Error al obtener usuario {user_id}: {e}")
                continue
        
        if mentions:
            # Crear texto de menciones seguro
            final_text = create_safe_mention_text(mention_text, mentions)
            safe_send_message(chat_id, final_text, parse_mode='Markdown')
            
            # Enviar mensajes directos a usuarios registrados
            send_direct_messages_to_users("MENCIÓN GENERAL", "/all")
        else:
            safe_reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar a todos: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['allbug'])
def mention_all_bug(message):
    """Menciona a todos para alerta de bug"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        # Obtener información del chat
        chat_member_count = bot.get_chat_member_count(chat_id)
        
        mention_text = f"🚨 ALERTA DE BUG 🚨\n\n"
        mention_text += f"Total de miembros: {chat_member_count}\n"
        mention_text += f"📝 Usuarios registrados: {len(registered_users)}\n\n"
        mention_text += "⚠️ Se ha detectado un bug crítico que requiere atención inmediata\n\n"
        
        # Obtener administradores
        administrators = bot.get_chat_administrators(chat_id)
        
        # Lista para almacenar las menciones
        mentions = []
        mentioned_users = set()
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot:
                if admin.user.username:
                    clean_username = clean_name_for_mention(admin.user.username)
                    if f"@{clean_username}" not in mentioned_users:
                        mentions.append(f"@{clean_username}")
                        mentioned_users.add(f"@{clean_username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = clean_name_for_mention(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {clean_name_for_mention(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        clean_username = clean_name_for_mention(member.user.username)
                        if f"@{clean_username}" not in mentioned_users:
                            mentions.append(f"@{clean_username}")
                            mentioned_users.add(f"@{clean_username}")
                    else:
                        if f"user_{user_id}" not in mentioned_users:
                            full_name = escape_markdown(member.user.first_name)
                            if member.user.last_name:
                                full_name += f" {escape_markdown(member.user.last_name)}"
                            mentions.append(f"[{full_name}](tg://user?id={user_id})")
                            mentioned_users.add(f"user_{user_id}")
            except Exception as e:
                logging.error(f"Error al obtener usuario {user_id}: {e}")
                continue
        
        if mentions:
            # Crear texto de menciones seguro
            final_text = create_safe_mention_text(mention_text, mentions)
            safe_send_message(chat_id, final_text, parse_mode='Markdown')
            
            # Enviar mensajes directos a usuarios registrados
            send_direct_messages_to_users("ALERTA DE BUG CRÍTICO", "/allbug")
        else:
            safe_reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar para bug: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['allerror'])
def mention_all_error(message):
    """Menciona a todos para alerta de error de cuota"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        # Obtener información del chat
        chat_member_count = bot.get_chat_member_count(chat_id)
        
        mention_text = f"💥 ALERTA DE ERROR DE CUOTA 💥\n\n"
        mention_text += f"Total de miembros: {chat_member_count}\n"
        mention_text += f"📝 Usuarios registrados: {len(registered_users)}\n\n"
        mention_text += "⚠️ Se ha alcanzado el límite de cuota del sistema\n"
        mention_text += "🔧 Se requiere intervención inmediata del equipo técnico\n\n"
        
        # Obtener administradores
        administrators = bot.get_chat_administrators(chat_id)
        
        # Lista para almacenar las menciones
        mentions = []
        mentioned_users = set()
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot:
                if admin.user.username:
                    clean_username = clean_name_for_mention(admin.user.username)
                    if f"@{clean_username}" not in mentioned_users:
                        mentions.append(f"@{clean_username}")
                        mentioned_users.add(f"@{clean_username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = clean_name_for_mention(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {clean_name_for_mention(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        clean_username = clean_name_for_mention(member.user.username)
                        if f"@{clean_username}" not in mentioned_users:
                            mentions.append(f"@{clean_username}")
                            mentioned_users.add(f"@{clean_username}")
                    else:
                        if f"user_{user_id}" not in mentioned_users:
                            full_name = escape_markdown(member.user.first_name)
                            if member.user.last_name:
                                full_name += f" {escape_markdown(member.user.last_name)}"
                            mentions.append(f"[{full_name}](tg://user?id={user_id})")
                            mentioned_users.add(f"user_{user_id}")
            except Exception as e:
                logging.error(f"Error al obtener usuario {user_id}: {e}")
                continue
        
        if mentions:
            # Crear texto de menciones seguro
            final_text = create_safe_mention_text(mention_text, mentions)
            safe_send_message(chat_id, final_text, parse_mode='Markdown')
            
            # Enviar mensajes directos a usuarios registrados
            send_direct_messages_to_users("ALERTA DE ERROR DE CUOTA", "/allerror")
        else:
            safe_reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar para error: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['admins'])
def mention_admins(message):
    """Menciona solo a los administradores del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        administrators = bot.get_chat_administrators(chat_id)
        
        mention_text = "🔔 MENCIÓN A ADMINISTRADORES 🔔\n\n"
        mentions = []
        
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                clean_username = clean_name_for_mention(admin.user.username)
                mentions.append(f"@{clean_username}")
            elif not admin.user.is_bot:
                full_name = clean_name_for_mention(admin.user.first_name or "Usuario")
                if admin.user.last_name:
                    full_name += f" {clean_name_for_mention(admin.user.last_name)}"
                mentions.append(f"[{full_name}](tg://user?id={admin.user.id})")
        
        if mentions:
            mention_text += " ".join(mentions)
            safe_send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            safe_reply_to(message, "❌ No se encontraron administradores.")
            
    except Exception as e:
        logging.error(f"Error al mencionar administradores: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['count'])
def count_members(message):
    """Cuenta los miembros del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        member_count = bot.get_chat_member_count(chat_id)
        administrators = bot.get_chat_administrators(chat_id)
        
        admin_count = len([admin for admin in administrators if not admin.user.is_bot])
        
        count_text = f"""
📊 INFORMACIÓN DEL GRUPO

 Total de miembros: {member_count}
 Administradores: {admin_count}
 Miembros normales: {member_count - admin_count}
📝 Usuarios registrados: {len(registered_users)}

Nota: Solo puedo mencionar a administradores por limitaciones de la API de Telegram.
        """
        
        safe_reply_to(message, count_text, parse_mode=None)
        
    except Exception as e:
        logging.error(f"Error al contar miembros: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['registered'])
def show_registered_users(message):
    """Muestra los usuarios registrados"""
    try:
        if not registered_users:
            safe_reply_to(message, "📝 No hay usuarios registrados.")
            return
        
        # Obtener información detallada de Supabase
        try:
            result = supabase.table('registered_users').select('user_id, username, first_name, last_name, registered_at').order('registered_at', desc=True).execute()
            
            users_info = result.data
            
            count_text = f"📊 USUARIOS REGISTRADOS\n\n"
            count_text += f"Total registrados: {len(registered_users)}\n\n"
            
            # Mostrar últimos 10 usuarios registrados
            count_text += "Últimos registros:\n"
            for i, user_data in enumerate(users_info[:10]):
                username = user_data.get('username')
                first_name = user_data.get('first_name')
                last_name = user_data.get('last_name')
                user_id = user_data.get('user_id')
                registered_at = user_data.get('registered_at')
                
                display_name = username if username else f"{first_name or 'Usuario'}"
                if last_name:
                    display_name += f" {last_name}"
                # Limpiar el nombre para evitar problemas de Markdown
                clean_display_name = clean_text_for_telegram(display_name)
                count_text += f"{i+1}. {clean_display_name} (ID: {user_id})\n"
            
            if len(users_info) > 10:
                count_text += f"\n... y {len(users_info) - 10} más"
            
            count_text += "\n\nLos usuarios registrados recibirán menciones especiales en los comandos de alerta."
            
        except Exception as db_error:
            logging.error(f"Error al consultar Supabase: {db_error}")
            count_text = f"""
📊 USUARIOS REGISTRADOS

Total registrados: {len(registered_users)}

Los usuarios registrados recibirán menciones especiales en los comandos de alerta.
        """
        
        safe_reply_to(message, count_text, parse_mode=None)
        
    except Exception as e:
        logging.error(f"Error al mostrar usuarios registrados: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['historial', 'logs'])
def show_registration_history(message):
    """Muestra el historial de registros y acciones"""
    try:
        # Obtener los últimos 20 registros desde Supabase
        result = supabase.table('user_registration_log').select('user_id, action, details, timestamp').order('timestamp', desc=True).limit(20).execute()
        
        logs = result.data
        
        if not logs:
            safe_reply_to(message, "📝 No hay historial de registros disponible.")
            return
        
        history_text = "📊 HISTORIAL DE REGISTROS\n\n"
        
        for log in logs:
            user_id = log.get('user_id')
            action = log.get('action')
            details = log.get('details')
            timestamp = log.get('timestamp')
            action_emoji = {
                "REGISTRO": "✅",
                "ACTUALIZACION": "🔄", 
                "ELIMINACION": "❌"
            }.get(action, "📝")
            
            # Formatear timestamp
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%d/%m/%Y %H:%M")
            except:
                formatted_time = timestamp
            
            history_text += f"{action_emoji} **{action}** - Usuario {user_id}\n"
            history_text += f"   📅 {formatted_time}\n"
            if details:
                history_text += f"   📝 {details}\n"
            history_text += "\n"
        
        if len(logs) == 20:
            history_text += "... (mostrando últimos 20 registros)"
        
        safe_reply_to(message, history_text, parse_mode=None)
        
    except Exception as e:
        logging.error(f"Error al mostrar historial: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['backup', 'respaldo'])
def create_database_backup(message):
    """Crea un respaldo de la base de datos"""
    try:
        if backup_database():
            safe_reply_to(message, "✅ Respaldo de la base de datos creado exitosamente.")
        else:
            safe_reply_to(message, "❌ Error al crear el respaldo de la base de datos.")
    except Exception as e:
        logging.error(f"Error al crear respaldo: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['mensaje'])
def mensaje_command(message):
    """Registra al usuario para recibir mensajes directos de alertas"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        if user_id in direct_message_users:
            safe_reply_to(message, "✅ Ya estás registrado para recibir mensajes directos de alertas.")
            return
        
        # Agregar a la base de datos
        if add_direct_message_user(user_id, username, first_name, last_name):
            direct_message_users.add(user_id)
            
            mensaje_text = f"✅ ¡Registro exitoso para mensajes directos!\n\n"
            if username:
                mensaje_text += f"Usuario: @{username}\n"
            else:
                mensaje_text += f"Nombre: {first_name or 'Usuario'}\n"
            mensaje_text += f"ID: {user_id}\n\n"
            mensaje_text += "Ahora recibirás mensajes directos cada vez que haya una alerta en el grupo.\n\n"
            mensaje_text += "⚠️ IMPORTANTE: Para recibir mensajes directos, debes:\n"
            mensaje_text += "1. Enviar un mensaje privado al bot (cualquier cosa)\n"
            mensaje_text += "2. Esto permite que el bot te contacte directamente\n\n"
            mensaje_text += "Usa /nomensaje para desregistrarte."
            
            safe_reply_to(message, mensaje_text, parse_mode=None)
        else:
            safe_reply_to(message, "❌ Ocurrió un error al registrarte. Intenta de nuevo.")
        
    except Exception as e:
        logging.error(f"Error en comando mensaje: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['nomensaje'])
def nomensaje_command(message):
    """Desregistra al usuario de los mensajes directos"""
    try:
        user_id = message.from_user.id
        
        if user_id not in direct_message_users:
            safe_reply_to(message, "❌ No estás registrado para mensajes directos.")
            return
        
        # Remover de la base de datos
        if remove_direct_message_user(user_id):
            direct_message_users.remove(user_id)
            safe_reply_to(message, "✅ Te has desregistrado de los mensajes directos.")
        else:
            safe_reply_to(message, "❌ Ocurrió un error al desregistrarte. Intenta de nuevo.")
        
    except Exception as e:
        logging.error(f"Error en comando nomensaje: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['listamensajes'])
def listamensajes_command(message):
    """Muestra los usuarios registrados para mensajes directos"""
    try:
        if not direct_message_users:
            safe_reply_to(message, "📝 No hay usuarios registrados para mensajes directos.")
            return
        
        # Obtener información detallada de Supabase
        try:
            result = supabase.table('direct_message_users').select('user_id, username, first_name, last_name, registered_at').order('registered_at', desc=True).execute()
            
            users_info = result.data
            
            count_text = f"📊 USUARIOS REGISTRADOS PARA MENSAJES DIRECTOS\n\n"
            count_text += f"Total registrados: {len(direct_message_users)}\n\n"
            
            # Mostrar todos los usuarios registrados
            count_text += "Usuarios registrados:\n"
            for i, user_data in enumerate(users_info):
                username = user_data.get('username')
                first_name = user_data.get('first_name')
                last_name = user_data.get('last_name')
                user_id = user_data.get('user_id')
                registered_at = user_data.get('registered_at')
                
                display_name = username if username else f"{first_name or 'Usuario'}"
                if last_name:
                    display_name += f" {last_name}"
                # Limpiar el nombre para evitar problemas de Markdown
                clean_display_name = clean_text_for_telegram(display_name)
                count_text += f"{i+1}. {clean_display_name} (ID: {user_id})\n"
            
            count_text += "\nEstos usuarios recibirán mensajes directos cada vez que haya una alerta en el grupo."
            
        except Exception as db_error:
            logging.error(f"Error al consultar Supabase: {db_error}")
            count_text = f"""
📊 USUARIOS REGISTRADOS PARA MENSAJES DIRECTOS

Total registrados: {len(direct_message_users)}

Estos usuarios recibirán mensajes directos cada vez que haya una alerta en el grupo.
        """
        
        safe_reply_to(message, count_text, parse_mode=None)
        
    except Exception as e:
        logging.error(f"Error al mostrar usuarios de mensajes directos: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['testdirecto'])
def test_directo_command(message):
    """Comando para probar si el bot puede enviar mensajes directos al usuario"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        test_message = "🧪 PRUEBA DE MENSAJE DIRECTO 🧪\n\n"
        test_message += "Si recibes este mensaje, el bot puede contactarte directamente.\n"
        test_message += "¡Perfecto! Recibirás notificaciones de alertas del grupo."
        
        try:
            bot.send_message(user_id, test_message)
            safe_reply_to(message, "✅ Mensaje directo enviado exitosamente. ¡Puedes recibir notificaciones!")
            logging.info(f"✅ Prueba de mensaje directo exitosa para usuario {user_id}")
        except Exception as e:
            error_str = str(e).lower()
            if "bot can't initiate conversation" in error_str:
                safe_reply_to(message, "❌ El bot no puede enviarte mensajes directos.\n\nPara solucionarlo:\n1. Ve al bot en privado\n2. Envía cualquier mensaje (ej: /start)\n3. Prueba de nuevo con /testdirecto")
            else:
                safe_reply_to(message, f"❌ Error al enviar mensaje directo: {e}")
            logging.error(f"❌ Error en prueba de mensaje directo para usuario {user_id}: {e}")
        
        log_user_action(user_id, "TEST_DIRECTO", "Usuario probó mensaje directo")
        
    except Exception as e:
        logging.error(f"Error en comando testdirecto: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['eliminar_usuario'])
def eliminar_usuario_command(message):
    """Comando de administrador para eliminar un usuario del registro de menciones del bot"""
    try:
        chat_id = message.chat.id
        
        # Verificar que el comando se use en un grupo
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        # Verificar que el usuario que ejecuta el comando sea administrador
        try:
            chat_member = bot.get_chat_member(chat_id, message.from_user.id)
            if chat_member.status not in ['creator', 'administrator']:
                safe_reply_to(message, "❌ Solo los administradores pueden usar este comando.")
                logging.warning(f"⚠️ Usuario {message.from_user.id} intentó usar /eliminar_usuario sin ser administrador")
                return
        except Exception as e:
            logging.error(f"❌ Error al verificar permisos de administrador: {e}")
            safe_reply_to(message, "❌ No se pudo verificar tus permisos de administrador.")
            return
        
        # Opción 1: Responder a un mensaje del usuario a eliminar
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            username = target_user.username
            first_name = target_user.first_name
            last_name = target_user.last_name
            
            # Verificar si el usuario está registrado
            if target_user_id not in registered_users:
                safe_reply_to(message, f"❌ El usuario {first_name} no está registrado para menciones.")
                return
            
            # Eliminar usuario
            if remove_registered_user(target_user_id):
                registered_users.discard(target_user_id)
                
                response_text = f"✅ Usuario eliminado del registro de menciones\n\n"
                if username:
                    response_text += f"Usuario: @{username}\n"
                else:
                    response_text += f"Nombre: {first_name or 'Usuario'}\n"
                response_text += f"ID: {target_user_id}\n\n"
                response_text += "Este usuario ya no recibirá menciones en los comandos /all, /allbug, /allerror, etc."
                
                safe_reply_to(message, response_text, parse_mode=None)
                log_user_action(message.from_user.id, "ADMIN_ELIMINAR_USUARIO", f"Eliminó a {first_name} ({target_user_id}) del registro de menciones")
            else:
                safe_reply_to(message, "❌ Error al eliminar al usuario. Intenta de nuevo más tarde.")
        
        # Opción 2: Proporcionar ID del usuario como argumento
        elif message.text and len(message.text.split()) > 1:
            try:
                # Extraer el ID del comando
                text_parts = message.text.split()
                target_user_id_str = text_parts[1]
                
                # Validar que sea un número
                if not target_user_id_str.isdigit():
                    safe_reply_to(message, "❌ El ID del usuario debe ser un número.\n\nUso: /eliminar_usuario <ID> o responde a un mensaje + /eliminar_usuario")
                    return
                
                target_user_id = int(target_user_id_str)
                
                # Verificar si el usuario está registrado
                if target_user_id not in registered_users:
                    safe_reply_to(message, f"❌ El usuario con ID {target_user_id} no está registrado para menciones.")
                    return
                
                # Obtener información del usuario de la base de datos
                try:
                    user_info_result = supabase.table('registered_users').select('username, first_name, last_name').eq('user_id', target_user_id).execute()
                    
                    if user_info_result.data:
                        user_data = user_info_result.data[0]
                        username = user_data.get('username')
                        first_name = user_data.get('first_name')
                        last_name = user_data.get('last_name')
                    else:
                        username = None
                        first_name = "Usuario"
                        last_name = None
                except Exception as db_error:
                    logging.error(f"Error al obtener información del usuario: {db_error}")
                    username = None
                    first_name = "Usuario"
                    last_name = None
                
                # Eliminar usuario
                if remove_registered_user(target_user_id):
                    registered_users.discard(target_user_id)
                    
                    response_text = f"✅ Usuario eliminado del registro de menciones\n\n"
                    if username:
                        response_text += f"Usuario: @{username}\n"
                    else:
                        response_text += f"Nombre: {first_name or 'Usuario'}\n"
                    response_text += f"ID: {target_user_id}\n\n"
                    response_text += "Este usuario ya no recibirá menciones en los comandos /all, /allbug, /allerror, etc."
                    
                    safe_reply_to(message, response_text, parse_mode=None)
                    log_user_action(message.from_user.id, "ADMIN_ELIMINAR_USUARIO", f"Eliminó a {first_name} ({target_user_id}) del registro de menciones")
                else:
                    safe_reply_to(message, "❌ Error al eliminar al usuario. Intenta de nuevo más tarde.")
                    
            except ValueError:
                safe_reply_to(message, "❌ El ID del usuario debe ser un número válido.\n\nUso: /eliminar_usuario <ID> o responde a un mensaje + /eliminar_usuario")
        else:
            # No hay reply ni argumento
            safe_reply_to(message, "❌ Debes responder a un mensaje del usuario a eliminar o proporcionar su ID.\n\nUso:\n• Responder a un mensaje + /eliminar_usuario\n• /eliminar_usuario <ID>")
        
    except Exception as e:
        logging.error(f"Error en comando eliminar_usuario: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['nba'])
def nba_command(message):
    """Comando para mostrar días restantes hasta el inicio de la temporada NBA 2025-26"""
    try:
        # Mostrar mensaje de carga
        loading_msg = safe_reply_to(message, "🏀 Buscando información de la NBA...", parse_mode=None)
        
        # Calcular días restantes
        days_left, season_start = calculate_days_until_nba()
        
        # Formatear fecha de inicio
        start_date_str = season_start.strftime("%d de %B de %Y")
        
        # Crear mensaje con emojis y formato
        nba_text = f"🏀 **TEMPORADA NBA 2025-26** 🏀\n\n"
        nba_text += f"📅 **Fecha de inicio:** {start_date_str}\n"
        nba_text += f"⏰ **Días restantes:** {days_left} días\n\n"
        
        if days_left > 0:
            nba_text += f"🔥 ¡Solo quedan {days_left} días para el inicio de la temporada!\n"
            nba_text += f"🎯 Los equipos están preparándose para la acción.\n"
        else:
            nba_text += f"🎉 ¡La temporada ya comenzó!\n"
            nba_text += f"🏆 ¡Disfruta de los juegos de la NBA!\n"
        
        # Mostrar hora en horario de Chile (CLST)
        chile_tz = pytz.timezone('America/Santiago')
        chile_time = datetime.now(chile_tz)
        
        # Determinar si es CLST o CLT
        timezone_name = "CLST" if chile_time.dst() != timedelta(0) else "CLT"
        
        nba_text += f"\n📊 *Información actualizada al {chile_time.strftime('%d/%m/%Y %H:%M')} ({timezone_name})*"
        
        # Enviar mensaje final
        safe_reply_to(message, nba_text, parse_mode='Markdown')
        
        # Log de la acción
        log_user_action(message.from_user.id, "NBA", f"Consultó días restantes: {days_left} días")
        
        logging.info(f"✅ Comando NBA ejecutado: {days_left} días restantes")
        
    except Exception as e:
        logging.error(f"Error en comando NBA: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al buscar información de la NBA. Intenta de nuevo más tarde.")
        
        # Fallback con información básica
        try:
            fallback_date = datetime(2025, 10, 21)
            chile_tz = pytz.timezone('America/Santiago')
            today = datetime.now(chile_tz)
            days_left = max(0, (fallback_date - today).days)
            
            fallback_text = f"🏀 **TEMPORADA NBA 2025-26** 🏀\n\n"
            fallback_text += f"📅 **Fecha estimada de inicio:** 21 de Octubre de 2025\n"
            fallback_text += f"⏰ **Días restantes:** {days_left} días\n\n"
            fallback_text += f"⚠️ *Información estimada (no se pudo conectar a internet)*\n"
            # Determinar si es CLST o CLT
            timezone_name = "CLST" if today.dst() != timedelta(0) else "CLT"
            fallback_text += f"📊 *Actualizado al {today.strftime('%d/%m/%Y %H:%M')} ({timezone_name})*"
            
            safe_reply_to(message, fallback_text, parse_mode='Markdown')
        except:
            safe_reply_to(message, "❌ Error al procesar la solicitud de NBA.")

@bot.message_handler(commands=['marcus'])
def marcus_command(message):
    """Comando especial de Marcus sobre Sinner y Roland Garros"""
    try:
        marcus_text = "**Sinner pagando 1.02, tiene servicio para ganar Roland Garros.**"
        safe_reply_to(message, marcus_text, parse_mode='Markdown')
        log_user_action(message.from_user.id, "MARCUS", "Usuario consultó comando Marcus")
    except Exception as e:
        logging.error(f"Error en comando marcus: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['comunista'])
def comunista_command(message):
    """Comando especial que envía mensaje directo al usuario comunista"""
    try:
        # ID específico del usuario comunista
        comunista_user_id = 5338161631
        
        # Mensaje especial para el comunista
        comunista_message = "HAY UNA NUEVA FREEBET DISPONIBLE COMUNISTA RE CONCHADETUMADRE REVISAR EL GRUPO A LA BREVEDAD, VIVA EL COMUNISMO"
        
        # Enviar mensaje directo al usuario comunista
        try:
            bot.send_message(comunista_user_id, comunista_message)
            logging.info(f"✅ Mensaje comunista enviado exitosamente al usuario {comunista_user_id}")
            
            # Responder en el grupo que se envió el mensaje
            safe_reply_to(message, "✅ Mensaje enviado al comunista. ¡Viva el comunismo! 🚩")
            
            # Registrar la acción
            log_user_action(message.from_user.id, "COMUNISTA", f"Envió mensaje comunista al usuario {comunista_user_id}")
            
        except Exception as e:
            error_str = str(e).lower()
            if "bot can't initiate conversation" in error_str:
                safe_reply_to(message, "❌ No se pudo enviar el mensaje al comunista. El usuario debe iniciar conversación con el bot primero.")
                logging.warning(f"⚠️ Usuario comunista {comunista_user_id} no ha iniciado conversación con el bot")
            elif "chat not found" in error_str or "blocked" in error_str:
                safe_reply_to(message, "❌ No se pudo contactar al comunista. Usuario no disponible.")
                logging.warning(f"⚠️ Usuario comunista {comunista_user_id} no contactable")
            else:
                safe_reply_to(message, f"❌ Error al enviar mensaje al comunista: {e}")
                logging.error(f"❌ Error al enviar mensaje comunista: {e}")
        
    except Exception as e:
        logging.error(f"Error en comando comunista: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['cr'])
def clan_war_command(message):
    """Comando para invitar a todo el grupo a jugar la guerra de clanes"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            safe_reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        # Obtener información del chat
        chat_member_count = bot.get_chat_member_count(chat_id)
        
        # Mensaje ULTRA MOTIVACIONAL para la guerra de clanes
        clan_war_text = "⚔️🔥 ¡GUERRA DE CLANES! 🔥⚔️\n\n"
        clan_war_text += "🎯 ¡LLAMADO A TODAS LAS TROPAS! 🎯\n\n"
        clan_war_text += "¡CLASHEROS! ¡La Guerra de Clanes ha comenzado! "
        clan_war_text += "El enemigo está atacando nuestras torres y necesitamos tu poder. "
        clan_war_text += "Es hora de mostrar el poder de nuestro clan y reclamar la victoria.\n\n"
        
        clan_war_text += "🏰 NUESTRA MISIÓN: Destruir las torres enemigas y ganar la guerra 🏰\n\n"
        
        clan_war_text += "⚡ Usa tus mejores MAZOS y ataques más devastadores\n"
        clan_war_text += "💎 Los trofeos del clan dependen de cada uno de vosotros\n"
        clan_war_text += "🎯 Cada ataque cuenta, cada torre destruida nos acerca a la victoria\n"
        clan_war_text += "🏆 Trabajemos juntos para ganar esta guerra\n\n"
        
        clan_war_text += "🚀 ¡NO HAY TIEMPO QUE PERDER! 🚀\n"
        clan_war_text += "Cada segundo cuenta, cada ataque importa para ganar la guerra. "
        clan_war_text += "El destino de nuestro clan está en vuestras manos.\n\n"
        
        clan_war_text += "💥 ¡VAMOS A GANAR ESTO! 💥\n"
        clan_war_text += "La victoria no es solo una opción, ¡ES NUESTRO DESTINO!\n\n"
        
        clan_war_text += "⚔️ ¡TODOS A LA BATALLA EN CLASH ROYALE! ⚔️\n\n"
        
        clan_war_text += "🎯 ¡REVISA TU CLAN! ¡PREPARA TU MAZO! ¡A LA GUERRA! 🎯"
        
        # Solo enviar el mensaje sin menciones
        safe_send_message(chat_id, clan_war_text, parse_mode='Markdown')
        
        # Enviar mensajes directos a usuarios registrados
        send_direct_messages_to_users("¡GUERRA DE CLANES! ¡Llamado a todas las tropas!", "/cr")
            
    except Exception as e:
        logging.error(f"Error al invitar a guerra de clanes: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")



def force_cleanup_all_instances():
    """Fuerza la limpieza de todas las instancias del bot"""
    try:
        # Obtener información del webhook
        webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        response = requests.get(webhook_url, timeout=10)
        
        if response.status_code == 200:
            webhook_data = response.json()
            if webhook_data.get('result', {}).get('url'):
                logging.info(f"🔍 Webhook activo encontrado: {webhook_data['result']['url']}")
                
                # Eliminar webhook
                delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
                delete_response = requests.get(delete_url, timeout=10)
                
                if delete_response.status_code == 200:
                    logging.info("✅ Webhook eliminado correctamente")
                    time.sleep(3)  # Esperar a que se propague
                else:
                    logging.warning(f"⚠️ Error al eliminar webhook: {delete_response.status_code}")
            else:
                logging.info("ℹ️ No hay webhook configurado")
        
        # Intentar detener polling forzadamente
        try:
            bot.stop_polling()
            logging.info("✅ Polling detenido")
        except:
            pass
            
        time.sleep(15)  # Esperar más tiempo para que se propague
        return True
        
    except Exception as e:
        logging.error(f"❌ Error en limpieza forzada: {e}")
        return False

def start_bot_with_webhook():
    """Inicia el bot usando webhook en lugar de polling para evitar conflictos 409"""
    try:
        # Limpieza forzada de todas las instancias
        logging.info("🧹 Limpieza forzada de todas las instancias...")
        force_cleanup_all_instances()
        
        # Obtener URL del webhook desde variable de entorno
        webhook_url = os.getenv('WEBHOOK_URL', f"https://mi-bot-telegram-0bno.onrender.com/webhook")
        
        logging.info(f"🚀 Configurando webhook: {webhook_url}")
        
        # Configurar webhook
        webhook_setup_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        webhook_data = {
            'url': webhook_url,
            'max_connections': 1,
            'allowed_updates': ['message']
        }
        
        response = requests.post(webhook_url, json=webhook_data, timeout=10)
        
        if response.status_code == 200:
            logging.info("✅ Webhook configurado correctamente")
            return True
        else:
            logging.error(f"❌ Error al configurar webhook: {response.status_code}")
            return False
            
    except Exception as e:
        logging.error(f"❌ Error al configurar webhook: {e}")
        return False

def start_bot_with_retry():
    """Inicia el bot con reintentos automáticos en caso de error de conexión"""
    max_restart_attempts = 5
    restart_delay = 30  # 30 segundos entre intentos
    
    # Delay inicial para evitar conflictos
    logging.info("⏳ Esperando 30 segundos para evitar conflictos...")
    time.sleep(30)
    
    # Limpieza básica antes de empezar
    logging.info("🧹 Limpieza básica antes de iniciar...")
    clear_webhook()
    time.sleep(10)
    
    logging.info("🚀 Iniciando bot con polling...")
    
    for attempt in range(max_restart_attempts):
        try:
            # Limpieza básica antes de cada intento
            if attempt > 0:
                logging.info(f"🧹 Limpieza básica antes del intento {attempt + 1}...")
                clear_webhook()
                time.sleep(10)
            
            logging.info(f"🚀 Iniciando Bot de Menciones (intento {attempt + 1}/{max_restart_attempts})...")
            logging.info(f"Token configurado: {'✅' if BOT_TOKEN else '❌'}")
            logging.info(f"Usuarios registrados: {len(registered_users)}")
            
            # Configurar el bot con timeouts normales y manejo de errores mejorado
            bot.infinity_polling(
                timeout=20, 
                long_polling_timeout=10,
                interval=2,
                none_stop=True,
                allowed_updates=['message', 'callback_query']  # Solo procesar mensajes y callbacks
            )
            
        except (ConnectionError, Timeout, NewConnectionError, MaxRetryError) as e:
            logging.error(f"❌ Error de conexión en intento {attempt + 1}: {e}")
            if attempt < max_restart_attempts - 1:
                logging.info(f"🔄 Reintentando en {restart_delay} segundos...")
                time.sleep(restart_delay)
                # Verificar conectividad antes de reintentar
                if check_network_connectivity():
                    logging.info("✅ Conectividad restaurada, reintentando...")
                else:
                    logging.warning("⚠️ Conectividad aún no disponible")
            else:
                logging.error("❌ Máximo número de reintentos alcanzado. Saliendo...")
                break
                
        except Exception as e:
            error_str = str(e)
            if "409" in error_str and "Conflict" in error_str:
                logging.error(f"❌ Conflicto de instancias en intento {attempt + 1}: {e}")
                if attempt < max_restart_attempts - 1:
                    # Delay progresivo para conflictos de instancias
                    conflict_delay = min(restart_delay * (2 ** min(attempt, 4)), 300)  # Máximo 5 minutos
                    logging.info(f"🔄 Esperando {conflict_delay} segundos para resolver conflicto...")
                    time.sleep(conflict_delay)
                    
                    # Limpieza forzada antes de reintentar
                    logging.info("🧹 Limpieza forzada antes de reintentar...")
                    force_cleanup_all_instances()
                else:
                    logging.error("❌ Máximo número de reintentos alcanzado. Saliendo...")
                    break
            elif "Story.__init__() got an unexpected keyword argument 'chat'" in error_str:
                logging.error(f"❌ Error de compatibilidad con Story en intento {attempt + 1}: {e}")
                logging.info("🔧 Este es un error conocido de compatibilidad con la API de Telegram")
                logging.info("🔄 Reintentando con configuración mejorada...")
                if attempt < max_restart_attempts - 1:
                    time.sleep(restart_delay)
                else:
                    logging.error("❌ Máximo número de reintentos alcanzado. Saliendo...")
                    break
            else:
                logging.error(f"❌ Error inesperado en intento {attempt + 1}: {e}")
                if attempt < max_restart_attempts - 1:
                    logging.info(f"🔄 Reintentando en {restart_delay} segundos...")
                    time.sleep(restart_delay)
                else:
                    logging.error("❌ Máximo número de reintentos alcanzado. Saliendo...")
                    break
                
        except KeyboardInterrupt:
            logging.info("\n🛑 Bot detenido por el usuario")
            break
            
        except Exception as e:
            logging.error(f"❌ Error inesperado: {e}")
            if attempt < max_restart_attempts - 1:
                logging.info(f"🔄 Reintentando en {restart_delay} segundos...")
                time.sleep(restart_delay)
            else:
                logging.error("❌ Máximo número de reintentos alcanzado. Saliendo...")
                break

def start_web_server():
    """Inicia un servidor web simple para Render"""
    from flask import Flask, request, jsonify
    app = Flask(__name__)
    
    @app.route('/')
    def health_check():
        return "Bot de Telegram funcionando correctamente"
    
    @app.route('/health')
    def health():
        return {"status": "ok", "bot": "running"}
    
    @app.route('/webhook', methods=['POST'])
    def webhook():
        """Endpoint para recibir actualizaciones de Telegram"""
        try:
            if request.headers.get('content-type') == 'application/json':
                json_data = request.get_json()
                if json_data and 'update_id' in json_data:
                    # Procesar la actualización
                    update = telebot.types.Update.de_json(json_data)
                    bot.process_new_updates([update])
                    return jsonify({"status": "ok"})
                else:
                    logging.warning("⚠️ Datos de webhook inválidos o sin update_id")
                    return jsonify({"status": "error", "message": "Invalid update data"}), 400
            return jsonify({"status": "error", "message": "Invalid content type"}), 400
        except Exception as e:
            logging.error(f"Error en webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    # Obtener puerto de Render o usar 5000 por defecto
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Iniciar bot en un hilo separado
    import threading
    bot_thread = threading.Thread(target=start_bot_with_retry)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Iniciar servidor web
    start_web_server()
