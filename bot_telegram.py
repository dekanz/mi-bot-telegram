import telebot
import logging
import os
import json
import time
import requests
import socket
import sqlite3
from telebot import types
from requests.exceptions import ConnectionError, Timeout, RequestException
from urllib3.exceptions import NewConnectionError, MaxRetryError

# Configuración del bot
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN no está configurado")
    exit(1)

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

# Base de datos para usuarios registrados
DATABASE_FILE = 'bot_database.db'

def init_database():
    """Inicializa la base de datos SQLite"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Crear tabla de usuarios registrados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registered_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✅ Base de datos inicializada correctamente")
        return True
    except Exception as e:
        logging.error(f"❌ Error al inicializar base de datos: {e}")
        return False

def load_registered_users():
    """Carga los usuarios registrados desde la base de datos"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM registered_users')
        user_ids = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return set(user_ids)
    except Exception as e:
        logging.error(f"❌ Error al cargar usuarios registrados: {e}")
        return set()

def add_registered_user(user_id, username=None, first_name=None, last_name=None):
    """Agrega un usuario a la base de datos"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO registered_users 
            (user_id, username, first_name, last_name, registered_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
        logging.info(f"✅ Usuario {user_id} agregado a la base de datos")
        return True
    except Exception as e:
        logging.error(f"❌ Error al agregar usuario {user_id}: {e}")
        return False

def remove_registered_user(user_id):
    """Remueve un usuario de la base de datos"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM registered_users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        logging.info(f"✅ Usuario {user_id} removido de la base de datos")
        return True
    except Exception as e:
        logging.error(f"❌ Error al remover usuario {user_id}: {e}")
        return False

def get_user_info(user_id):
    """Obtiene información de un usuario registrado"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, first_name, last_name, registered_at 
            FROM registered_users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'username': result[0],
                'first_name': result[1],
                'last_name': result[2],
                'registered_at': result[3]
            }
        return None
    except Exception as e:
        logging.error(f"❌ Error al obtener información del usuario {user_id}: {e}")
        return None

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
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logging.info("✅ Webhook limpiado correctamente")
                return True
            else:
                logging.warning(f"⚠️ Error al limpiar webhook: {response.status_code}")
        except (ConnectionError, Timeout, NewConnectionError, MaxRetryError) as e:
            logging.warning(f"⚠️ Intento {attempt + 1} fallido al limpiar webhook: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            logging.error(f"❌ Error inesperado al limpiar webhook: {e}")
            break
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
        return text
    
    # Limpiar caracteres problemáticos
    text = str(text)
    
    # Escapar caracteres especiales
    text = escape_markdown(text)
    
    # Limpiar caracteres de control
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    return text

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
                        # Limpiar el texto y enviar sin formato
                        clean_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
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
                        # Limpiar el texto y enviar sin formato
                        clean_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
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
🤖 **¡Hola! Soy el Bot de Menciones** 

Estoy aquí para ayudarte a mencionar a todos los integrantes de tu grupo.

**Comandos principales:**
• `/all` - Menciona a todos
• `/allbug` - Alerta de bug
• `/allerror` - Alerta de error de cuota
• `/register` - Registrarse para menciones
• `/unregister` - Desregistrarse
• `/help` - Ver ayuda completa

¡Agrégame a un grupo y hazme administrador para empezar!
    """
    safe_reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    """Muestra la ayuda del bot"""
    help_text = """
 **Bot de Menciones - Ayuda**

**Comandos disponibles:**
• `/all` - Menciona a todos los miembros del grupo
• `/allbug` - Alerta de bug (menciona a todos)
• `/allerror` - Alerta de error de cuota (menciona a todos)
• `/admins` - Menciona solo a los administradores
• `/register` - Registrarse para recibir menciones
• `/unregister` - Desregistrarse de las menciones
• `/count` - Muestra estadísticas del grupo
• `/help` - Muestra esta ayuda

**Notas importantes:**
• El bot debe ser administrador del grupo
• Solo funciona en grupos y supergrupos
• Para mencionar a todos, el bot necesita permisos especiales
• Los usuarios registrados recibirán menciones especiales
    """
    safe_reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['register'])
def register_user(message):
    """Registra al usuario para recibir menciones"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        if user_id in registered_users:
            safe_reply_to(message, "✅ Ya estás registrado para recibir menciones.")
            return
        
        # Agregar a la base de datos
        if add_registered_user(user_id, username, first_name, last_name):
            registered_users.add(user_id)
            
            # Crear mención personalizada
            mention_text = f"✅ **¡Registro exitoso!**\n\n"
            if username:
                mention_text += f"Usuario: @{username}\n"
            else:
                mention_text += f"Nombre: {first_name or 'Usuario'}\n"
            mention_text += f"ID: {user_id}\n\n"
            mention_text += "Ahora recibirás menciones especiales cuando uses los comandos de alerta."
            
            safe_reply_to(message, mention_text, parse_mode='Markdown')
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
        
        mention_text = f"🔔 **MENCIÓN GENERAL** 🔔\n\n"
        mention_text += f" Total de miembros: {chat_member_count}\n"
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
                    if f"@{admin.user.username}" not in mentioned_users:
                        mentions.append(f"@{admin.user.username}")
                        mentioned_users.add(f"@{admin.user.username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = safe_markdown_text(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {safe_markdown_text(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        if f"@{member.user.username}" not in mentioned_users:
                            mentions.append(f"@{member.user.username}")
                            mentioned_users.add(f"@{member.user.username}")
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
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            safe_send_message(chat_id, mention_text, parse_mode='Markdown')
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
        
        mention_text = f"🚨 **ALERTA DE BUG** 🚨\n\n"
        mention_text += f" Total de miembros: {chat_member_count}\n"
        mention_text += f"📝 Usuarios registrados: {len(registered_users)}\n\n"
        mention_text += "⚠️ **Se ha detectado un bug crítico que requiere atención inmediata**\n\n"
        
        # Obtener administradores
        administrators = bot.get_chat_administrators(chat_id)
        
        # Lista para almacenar las menciones
        mentions = []
        mentioned_users = set()
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot:
                if admin.user.username:
                    if f"@{admin.user.username}" not in mentioned_users:
                        mentions.append(f"@{admin.user.username}")
                        mentioned_users.add(f"@{admin.user.username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = safe_markdown_text(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {safe_markdown_text(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        if f"@{member.user.username}" not in mentioned_users:
                            mentions.append(f"@{member.user.username}")
                            mentioned_users.add(f"@{member.user.username}")
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
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            safe_send_message(chat_id, mention_text, parse_mode='Markdown')
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
        
        mention_text = f"💥 **ALERTA DE ERROR DE CUOTA** 💥\n\n"
        mention_text += f" Total de miembros: {chat_member_count}\n"
        mention_text += f"📝 Usuarios registrados: {len(registered_users)}\n\n"
        mention_text += "⚠️ **Se ha alcanzado el límite de cuota del sistema**\n"
        mention_text += "🔧 **Se requiere intervención inmediata del equipo técnico**\n\n"
        
        # Obtener administradores
        administrators = bot.get_chat_administrators(chat_id)
        
        # Lista para almacenar las menciones
        mentions = []
        mentioned_users = set()
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot:
                if admin.user.username:
                    if f"@{admin.user.username}" not in mentioned_users:
                        mentions.append(f"@{admin.user.username}")
                        mentioned_users.add(f"@{admin.user.username}")
                else:
                    user_id = admin.user.id
                    if f"user_{user_id}" not in mentioned_users:
                        full_name = safe_markdown_text(admin.user.first_name or "Usuario")
                        if admin.user.last_name:
                            full_name += f" {safe_markdown_text(admin.user.last_name)}"
                        mentions.append(f"[{full_name}](tg://user?id={user_id})")
                        mentioned_users.add(f"user_{user_id}")
        
        # Agregar usuarios registrados que no sean administradores
        for user_id in registered_users:
            try:
                # Verificar si el usuario está en el grupo
                member = bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    if member.user.username:
                        if f"@{member.user.username}" not in mentioned_users:
                            mentions.append(f"@{member.user.username}")
                            mentioned_users.add(f"@{member.user.username}")
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
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            safe_send_message(chat_id, mention_text, parse_mode='Markdown')
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
        
        mention_text = "🔔 **MENCIÓN A ADMINISTRADORES** 🔔\n\n"
        mentions = []
        
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                mentions.append(f"@{admin.user.username}")
            elif not admin.user.is_bot:
                full_name = safe_markdown_text(admin.user.first_name or "Usuario")
                if admin.user.last_name:
                    full_name += f" {safe_markdown_text(admin.user.last_name)}"
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
📊 **INFORMACIÓN DEL GRUPO**

 Total de miembros: {member_count}
 Administradores: {admin_count}
 Miembros normales: {member_count - admin_count}
📝 Usuarios registrados: {len(registered_users)}

**Nota:** Solo puedo mencionar a administradores por limitaciones de la API de Telegram.
        """
        
        safe_reply_to(message, count_text, parse_mode='Markdown')
        
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
        
        # Obtener información detallada de la base de datos
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, username, first_name, last_name, registered_at 
                FROM registered_users ORDER BY registered_at DESC
            ''')
            
            users_info = cursor.fetchall()
            conn.close()
            
            count_text = f"📊 **USUARIOS REGISTRADOS**\n\n"
            count_text += f"Total registrados: {len(registered_users)}\n\n"
            
            # Mostrar últimos 10 usuarios registrados
            count_text += "**Últimos registros:**\n"
            for i, (user_id, username, first_name, last_name, registered_at) in enumerate(users_info[:10]):
                display_name = username if username else f"{first_name or 'Usuario'}"
                if last_name:
                    display_name += f" {last_name}"
                count_text += f"{i+1}. {display_name} (ID: {user_id})\n"
            
            if len(users_info) > 10:
                count_text += f"\n... y {len(users_info) - 10} más"
            
            count_text += "\n\nLos usuarios registrados recibirán menciones especiales en los comandos de alerta."
            
        except Exception as db_error:
            logging.error(f"Error al consultar base de datos: {db_error}")
            count_text = f"""
📊 **USUARIOS REGISTRADOS**

Total registrados: {len(registered_users)}

Los usuarios registrados recibirán menciones especiales en los comandos de alerta.
            """
        
        safe_reply_to(message, count_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Error al mostrar usuarios registrados: {e}")
        safe_reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

def start_bot_with_retry():
    """Inicia el bot con reintentos automáticos en caso de error de conexión"""
    max_restart_attempts = 10
    restart_delay = 60  # 1 minuto
    
    for attempt in range(max_restart_attempts):
        try:
            logging.info(f"🚀 Iniciando Bot de Menciones (intento {attempt + 1}/{max_restart_attempts})...")
            logging.info(f"Token configurado: {'✅' if BOT_TOKEN else '❌'}")
            logging.info(f"Usuarios registrados: {len(registered_users)}")
            
            # Configurar el bot con timeouts más largos
            bot.infinity_polling(
                timeout=30, 
                long_polling_timeout=20,
                interval=1,
                none_stop=True
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

if __name__ == '__main__':
    start_bot_with_retry()
