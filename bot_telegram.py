import telebot
import logging
import os
from telebot import types

# Configuración del bot
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Variable de entorno

# Crear instancia del bot
bot = telebot.TeleBot(BOT_TOKEN)

# Configurar logging
logging.basicConfig(level=logging.INFO)

@bot.message_handler(commands=['all', 'mentionall'])
def mention_all(message):
    """Menciona a todos los miembros del grupo"""
    try:
        chat_id = message.chat.id
        
        if message.chat.type not in ['group', 'supergroup']:
            bot.reply_to(message, "❌ Este comando solo funciona en grupos.")
            return
        
        chat_member_count = bot.get_chat_member_count(chat_id)
        administrators = bot.get_chat_administrators(chat_id)
        
        mention_text = "🔔 **MENCIÓN GENERAL** 🔔\n\n"
        mention_text += f"   Total de miembros: {chat_member_count}\n\n"
        
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
            for i in range(0, len(mentions), 5):
                batch = mentions[i:i+5]
                mention_text += " ".join(batch) + "\n"
            
            bot.send_message(chat_id, mention_text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ No se pudieron obtener los miembros del grupo.")
            
    except Exception as e:
        logging.error(f"Error al mencionar a todos: {e}")
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
            bot.reply_to(message, "❌ No se encontraron administradores.")
            
    except Exception as e:
        logging.error(f"Error al mencionar administradores: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al procesar la solicitud.")

@bot.message_handler(commands=['help', 'ayuda'])
def help_command(message):
    """Muestra la ayuda del bot"""
    help_text = """
   **Bot de Menciones - Ayuda**

**Comandos disponibles:**
• `/all` o `/mentionall` - Menciona a todos los miembros del grupo
• `/admins` - Menciona solo a los administradores
• `/help` o `/ayuda` - Muestra esta ayuda
• `@all` - También funciona escribiendo @all en el chat

**Notas importantes:**
• El bot debe ser administrador del grupo
• Solo funciona en grupos y supergrupos
• El bot necesita permisos para leer mensajes

**Desarrollado para facilitar la comunicación grupal**   
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: '@all' in message.text.lower() if message.text else False)
def handle_at_all(message):
    """Detecta cuando alguien escribe @all y menciona a todos"""
    mention_all(message)

@bot.message_handler(commands=['start'])
def start_command(message):
    """Comando de inicio del bot"""
    welcome_text = """
🤖 **¡Hola! Soy el Bot de Menciones** 

Estoy aquí para ayudarte a mencionar a todos los integrantes de tu grupo.

**Comandos principales:**
• `/all` - Menciona a todos
• `/admins` - Menciona solo administradores
• `/help` - Ver ayuda completa

¡Agrégame a un grupo y hazme administrador para empezar!   
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

if __name__ == '__main__':
    print("   Iniciando Bot de Menciones...")
    print("Presiona Ctrl+C para detener el bot")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error: {e}")