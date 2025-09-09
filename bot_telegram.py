import telebot
import logging
import os
import json
import time
from telebot import types

# Configuración del bot
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN no está configurado")
    exit(1)

# Crear instancia del bot
bot = telebot.TeleBot(BOT_TOKEN)

# Configurar logging
logging.basicConfig(level=logging.INFO)

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

# Cargar usuarios registrados al iniciar
registered_users = load_registered_users()

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
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

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
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['register'])
def register_user(message):
    """Registra al usuario para recibir menciones"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        if user_id in registered_users:
            bot.reply_to(message, "✅ Ya estás registrado para recibir menciones.")
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
        
        bot.reply_to(message, mention_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Error al registrar usuario: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al registrarte.")

@bot.message_handler(commands=['unregister'])
def unregister_user(message):
    """Desregistra al usuario de las menciones"""
    try:
        user_id = message.from_user.id
        
        if user_id not in registered_users:
            bot.reply_to(message, "❌ No estás registrado.")
            return
        
        registered_users.remove(user_id)
        save_registered_users(registered_users)
        
        bot.reply_to(message, "✅ Te has desregistrado de las menciones.")
        
    except Exception as e:
        logging.error(f"Error al desregistrar usuario: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al desregistrarte.")

@bot.message_handler(commands=['all'])
def mention_all(message):
    """Menciona a todos los miembros del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            bot.reply_to(message, "❌ Este comando solo funciona en grupos.")
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
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                mentions.append(f"@{admin.user.username}")
            elif not admin.user.is_bot:
                full_name = admin.user.first_name
                if admin.user.last_name:
                    full_name += f" {admin.user.last_name}"
                mentions.append(f"[{full_name}](tg://user?id={admin.user.id})")
        
        if mentions:
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            bot.send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar a todos: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['allbug'])
def mention_all_bug(message):
    """Menciona a todos para alerta de bug"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            bot.reply_to(message, "❌ Este comando solo funciona en grupos.")
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
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                mentions.append(f"@{admin.user.username}")
            elif not admin.user.is_bot:
                full_name = admin.user.first_name
                if admin.user.last_name:
                    full_name += f" {admin.user.last_name}"
                mentions.append(f"[{full_name}](tg://user?id={admin.user.id})")
        
        if mentions:
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            bot.send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar para bug: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['allerror'])
def mention_all_error(message):
    """Menciona a todos para alerta de error de cuota"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            bot.reply_to(message, "❌ Este comando solo funciona en grupos.")
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
        
        # Agregar administradores primero
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                mentions.append(f"@{admin.user.username}")
            elif not admin.user.is_bot:
                full_name = admin.user.first_name
                if admin.user.last_name:
                    full_name += f" {admin.user.last_name}"
                mentions.append(f"[{full_name}](tg://user?id={admin.user.id})")
        
        if mentions:
            # Dividir menciones en grupos de 5 para evitar límites
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            bot.send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar para error: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['admins'])
def mention_admins(message):
    """Menciona solo a los administradores del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            bot.reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        administrators = bot.get_chat_administrators(chat_id)
        
        mention_text = "🔔 **MENCIÓN A ADMINISTRADORES** 🔔\n\n"
        mentions = []
        
        for admin in administrators:
            if not admin.user.is_bot and admin.user.username:
                mentions.append(f"@{admin.user.username}")
            elif not admin.user.is_bot:
                full_name = admin.user.first_name
                if admin.user.last_name:
                    full_name += f" {admin.user.last_name}"
                mentions.append(f"[{full_name}](tg://user?id={admin.user.id})")
        
        if mentions:
            mention_text += " ".join(mentions)
            bot.send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            bot.
