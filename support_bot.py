import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import os
SUPPORT_BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Это служба поддержки.\n\n"
        "Напиши свой вопрос одним сообщением, и я передам его администратору. "
        "Обычно отвечаем в течение пары часов."
    )

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_message = update.message.text

    # Отправляем сообщение админу с пометкой, от кого оно
    try:
        await context.bot.send_message(
    chat_id=ADMIN_ID,
    text=f"📩 Новое сообщение в поддержку\n\n"
         f"От: {user.first_name} (@{user.username})\n"
         f"ID: {user.id}\n\n"
         f"Текст: {user_message}"
)
        await update.message.reply_text("✅ Твое сообщение отправлено. Ожидай ответа!")
    except Exception as e:
        await update.message.reply_text("❌ Ошибка отправки. Попробуй позже.")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если пишет админ и делает Reply (ответ) на сообщение
    if update.effective_user.id == ADMIN_ID:
        # Проверяем, что это именно ответ на сообщение
        if update.message.reply_to_message:
            # Вытаскиваем ID пользователя из текста сообщения, на которое отвечает админ
            original_text = update.message.reply_to_message.text
            try:
                # Ищем строку с ID
                id_line = [line for line in original_text.split('\n') if line.startswith('ID:')][0]
                user_id = int(id_line.replace('ID:', '').replace('`', '').strip())
                
                # Отправляем ответ пользователю
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"💬 **Ответ поддержки:**\n\n{update.message.text}",
                    parse_mode="Markdown"
                )
                await update.message.reply_text("✅ Ответ доставлен пользователю.")
            except Exception as e:
                await update.message.reply_text("❌ Не удалось найти ID пользователя. Убедись, что отвечаешь на сообщение из поддержки.")
        else:
            await update.message.reply_text("Чтобы ответить пользователю, нажми «Ответить» (Reply) на его сообщение.")

def main():
    app = Application.builder().token(SUPPORT_BOT_TOKEN).build()

    # Команда /start
    app.add_handler(CommandHandler("start", start))
    
    # Обработчик ответов от админа (должен быть первым)
    app.add_handler(MessageHandler(filters.User(ADMIN_ID) & filters.REPLY, handle_admin_reply))
    
    # Обработчик сообщений от пользователей
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    print("Бот поддержки запущен, ожидание сообщений...")
    app.run_polling()

if __name__ == '__main__':
    main()