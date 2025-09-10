import telebot
import logging
import os
import json
import time
import requests
import socket
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

# Archivo para guardar usuarios registrados
REGISTERED_USERS_FILE = 'registered_users.json'

def load_registered_users():
    """Carga los usuarios registrados desde el archivo"""
    try:
        if os.path.exists(REGISTERED_USERS_FILE):
            with open(REGISTERED_USERS_FILE, 'r') as f:
                return set(json.load(f))
        return set()
    except Exception as e:
        logging.error(f"Error al cargar usuarios registrados: {e}")
        return set()

def save_registered_users(users):
    """Guarda los usuarios registrados en el archivo"""
    try:
        with open(REGISTERED_USERS_FILE, 'w') as f:
            json.dump(list(users), f)
    except Exception as e:
        logging.error(f"Error al guardar usuarios registrados: {e}")

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
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def safe_send_message(chat_id, text, parse_mode='Markdown', max_retries=5):
    """Envía un mensaje con reintentos en caso de error de conexión"""
    for attempt in range(max_retries):
        try:
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
        
        if user_id in registered_users:
            safe_reply_to(message, "✅ Ya estás registrado para recibir menciones.")
            return
        
        registered_users.add(user_id)
        save_registered_users(registered_users)
        
        # Crear mención personalizada
        mention_text = f"✅ **¡Registro exitoso!**\n\n"
        if username:
            mention_text += f"Usuario: @{username}\n"
        else:
            mention_text += f"Nombre: {first_name}\n"
        mention_text += f"ID: {user_id}\n\n"
        mention_text += "Ahora recibirás menciones especiales cuando uses los comandos de alerta."
        
        safe_reply_to(message, mention_text, parse_mode='Markdown')
        
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
        
        registered_users.remove(user_id)
        save_registered_users(registered_users)
        
        safe_reply_to(message, "✅ Te has desregistrado de las menciones.")
        
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
                        full_name = escape_markdown(admin.user.first_name)
                        if admin.user.last_name:
                            full_name += f" {escape_markdown(admin.user.last_name)}"
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
                        full_name = escape_markdown(admin.user.first_name)
                        if admin.user.last_name:
                            full_name += f" {escape_markdown(admin.user.last_name)}"
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
                        full_name = escape_markdown(admin.user.first_name)
                        if admin.user.last_name:
                            full_name += f" {escape_markdown(admin.user.last_name)}"
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
                full_name = escape_markdown(admin.user.first_name)
                if admin.user.last_name:
                    full_name += f" {escape_markdown(admin.user.last_name)}"
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
        
        count_text = f"""
 **USUARIOS REGISTRADOS**

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
