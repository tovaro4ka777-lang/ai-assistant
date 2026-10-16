import logging
import os
from datetime import datetime, timedelta

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    filters,
)

import database as db
import ai_helper
import file_generator

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")



ADMIN_IDS = [5906384388]  # ← вставь свой ID

async def check_user_limit(update, context):
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        return True
    
    if db.has_subscription(user_id):
        return True
    
    used = db.get_usage_today(user_id)
    if used >= db.FREE_LIMIT:
        await update.message.reply_text(
            f"🚫 Лимит на сегодня исчерпан ({db.FREE_LIMIT} запросов).\n\n"
            f"Оформи подписку за 199₽/мес — и общайся без ограничений.\n"
            f"Напиши /premium, чтобы узнать подробнее."
        )
        return False
    
    db.increment_usage(user_id)
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or "", user.first_name or "")

    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            if referrer_id != user.id:
                db.add_bonus_requests(referrer_id, 5)
                db.add_bonus_requests(user.id, 3)
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 По твоей ссылке пришёл новый юзер! Тебе +5 запросов."
                    )
                except Exception:
                    pass
        except ValueError:
            pass

    text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я твой личный ассистент. Вот что я умею:\n\n"
        "📄 /doc <тема> — создать Word-документ\n"
        "📊 /slides <тема> — создать презентацию\n"
        "💻 /code <задача> — написать код\n\n"
        "📝 /note <текст> — сохранить заметку\n"
        "📋 /notes — показать заметки\n"
        "🗑 /delnote <id> — удалить заметку\n\n"
        "⏰ /remind <минуты> <текст> — напоминание\n\n"
        "✅ /habit <название> — добавить привычку\n"
        "📊 /habits — список привычек\n\n"
        "📈 /stats — статистика\n"
        "🧹 /reset — очистить диалог с ИИ\n"
        "👥 /ref — реферальная ссылка\n"
        "💎 /premium — подписка Premium\n\n"
        "🤖 Просто напиши мне что-нибудь — отвечу через ИИ!\n"
        "🎤 Или отправь голосовое — расшифрую."
    )

    keyboard = [
        [InlineKeyboardButton("📄 Политика конфиденциальности", url="https://telegra.ph/Politika-konfidencialnosti-10-09-97")],
        [InlineKeyboardButton("📜 Пользовательское соглашение", url="https://telegra.ph/PUBLICHNAYA-OFERTA-10-09-15")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/AssistantSupportBot")],
        [InlineKeyboardButton("💎 Подписка Premium", callback_data="premium_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = db.get_stats(user_id)
    await update.message.reply_text(
        f"📊 Твоя статистика:\n\n"
        f"📝 Заметок: {s['notes']}\n"
        f"✅ Привычек: {s['habits']}"
    )


async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Использование: /note <текст заметки>")
        return
    note_id = db.add_note(user_id, text)
    await update.message.reply_text(f"✅ Заметка #{note_id} сохранена!")


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = db.get_notes(user_id)
    if not notes:
        await update.message.reply_text("У тебя пока нет заметок.")
        return
    lines = ["📋 Твои заметки:\n"]
    for note in notes[:20]:
        lines.append(f"#{note['id']}: {note['text'][:80]}")
    await update.message.reply_text("\n".join(lines))


async def del_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /delnote <id>")
        return
    try:
        note_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    if db.delete_note(user_id, note_id):
        await update.message.reply_text(f"🗑 Заметка #{note_id} удалена.")
    else:
        await update.message.reply_text("Заметка не найдена.")


async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /remind <минуты> <текст>\n"
            "Пример: /remind 30 позвонить маме"
        )
        return
    try:
        minutes = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Первое число — это минуты.")
        return
    text = " ".join(context.args[1:])
    remind_at = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    db.add_reminder(user_id, text, remind_at)
    await update.message.reply_text(f"⏰ Напомню через {minutes} мин: {text}")


async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = " ".join(context.args) if context.args else ""
    if not name:
        await update.message.reply_text("Использование: /habit <название>")
        return
    db.add_habit(user_id, name)
    await update.message.reply_text(f"✅ Привычка '{name}' добавлена!")


async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    habits = db.get_habits(user_id)
    if not habits:
        await update.message.reply_text("У тебя пока нет привычек.")
        return
    lines = ["✅ Твои привычки:\n"]
    for h in habits:
        lines.append(f"#{h['id']} {h['name']} — 🔥 {h['streak']} дней")
    await update.message.reply_text("\n".join(lines))


async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Использование: /code <задача>\n"
            "Пример: /code калькулятор на Python"
        )
        return
    await update.message.reply_text(f"💻 Пишу код: {topic}...")
    prompt = (
        f"Напиши рабочий код для задачи: {topic}. "
        f"Верни ТОЛЬКО код, без пояснений, без markdown-разметки, "
        f"без тройных кавычек. Только чистый код. "
        f"Определи язык программирования сам и укажи его первой строкой в формате: "
        f"LANG: <язык>\n"
    )
    raw = await ai_helper.ask_ai([{"role": "user", "content": prompt}])
    language = "python"
    code = raw
    if "LANG:" in raw:
        lines = raw.split("\n", 1)
        lang_line = lines[0].replace("LANG:", "").strip().lower()
        if lang_line:
            language = lang_line
            code = lines[1].strip() if len(lines) > 1 else ""
    code = code.replace("```python", "").replace("```", "").strip()
    try:
        filepath = file_generator.create_code_file(topic, code, language)
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=os.path.basename(filepath))
            )
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def doc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Использование: /doc <тема>\n"
            "Пример: /doc доклад про Марс"
        )
        return
    await update.message.reply_text(f"📄 Генерирую документ: {topic}...")
    prompt = (
        f"Напиши большой, подробный документ на тему: {topic}. "
        f"Структура: введение (2-3 абзаца), основная часть (3-4 раздела), заключение. "
        f"Минимум 1500 слов. Без markdown. Каждый абзац с новой строки."
    )
    content = await ai_helper.ask_ai([{"role": "user", "content": prompt}])
    try:
        filepath = file_generator.create_docx(topic, content)
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=os.path.basename(filepath))
            )
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def slides_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Использование: /slides <тема>\n"
            "Пример: /slides Марс"
        )
        return
    await update.message.reply_text(f"📊 Генерирую презентацию: {topic}...")
    prompt = (
        f"Составь большую подробную презентацию на тему: {topic}. "
        f"Нужно 8 слайдов. На каждом слайде МИНИМУМ 5-6 пунктов, "
        f"каждый пункт — полноценное предложение с фактами. "
        f"Для каждого слайда напиши:\n"
        f"ЗАГОЛОВОК: <заголовок>\n"
        f"ТЕКСТ:\n- пункт 1\n- пункт 2\n- пункт 3\n- пункт 4\n- пункт 5\n\n"
        f"Разделяй слайды строкой ---."
    )
    raw = await ai_helper.ask_ai([{"role": "user", "content": prompt}])
    slides_data = []
    for block in raw.split("---"):
        block = block.strip()
        if not block:
            continue
        title = "Слайд"
        content = block
        if "ЗАГОЛОВОК:" in block:
            parts = block.split("ЗАГОЛОВОК:", 1)[1]
            if "ТЕКСТ:" in parts:
                title = parts.split("ТЕКСТ:", 1)[0].strip()
                content = parts.split("ТЕКСТ:", 1)[1].strip()
            else:
                title = parts.strip()
                content = ""
        slides_data.append({"title": title, "content": content})
    if not slides_data:
        await update.message.reply_text("Не удалось сгенерировать слайды.")
        return
    try:
        filepath = file_generator.create_pptx(topic, slides_data)
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=os.path.basename(filepath))
            )
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    await update.message.reply_text(
        f"👥 Твоя реферальная ссылка:\n\n{link}\n\n"
        f"За друга: тебе +5 запросов, ему +3."
    )


async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.has_subscription(user_id):
        await update.message.reply_text("✅ У тебя активная подписка. Безлимит включён!")
    else:
        await update.message.reply_text(
            "💎 Подписка Premium — 100 ⭐ (~200₽) в месяц\n\n"
            "Что даёт:\n"
            "• Безлимит на все функции\n"
            "• Документы и презентации без ограничений\n"
            "• Приоритетная скорость ответа\n\n"
            "Нажми /buy, чтобы оплатить звёздами Telegram."
        )


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Подписка Premium",
        description="Безлимит на все функции бота на 30 дней",
        payload="premium_30_days",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 дней", amount=100)],
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    db.give_subscription(user_id, days=30, plan="premium")
    await update.message.reply_text(
        f"✅ Оплата прошла! Подписка Premium активна на 30 дней.\n"
        f"💎 Сумма: {payment.total_amount} ⭐"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "premium_info":
        user_id = query.from_user.id
        if db.has_subscription(user_id):
            await query.message.reply_text("✅ У тебя активная подписка. Безлимит включён!")
        else:
            await query.message.reply_text(
                "💎 Подписка Premium — 100 ⭐ (~200₽) в месяц\n\n"
                "Что даёт:\n"
                "• Безлимит на все функции\n"
                "• Документы и презентации без ограничений\n\n"
                "Нажми /buy, чтобы оплатить."
            )


async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return
    text = update.effective_message.text
    if not text:
        return
    history = context.user_data.get('history', [])
    history.append({"role": "user", "content": text})
    if len(history) > 20:
        history = history[-20:]
    await update.effective_chat.send_action("typing")
    answer = await ai_helper.ask_ai(history)
    history.append({"role": "assistant", "content": answer})
    context.user_data['history'] = history
    for part in ai_helper.split_message(answer):
        await update.message.reply_text(part)
async def voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return

    voice = update.message.voice
    await update.message.reply_text("🎤 Слушаю...")

    try:
        file = await context.bot.get_file(voice.file_id)
        file_path = f"voice_{voice.file_unique_id}.ogg"
        await file.download_to_drive(file_path)

        text = await ai_helper.transcribe_audio(file_path)
        os.remove(file_path)

        if text.startswith("Ошибка"):
            await update.message.reply_text(text)
            return

        await update.message.reply_text(f"📝 Ты сказал: {text}")

        history = context.user_data.get('history', [])
        history.append({"role": "user", "content": text})
        if len(history) > 20:
            history = history[-20:]

        await update.effective_chat.send_action("typing")
        answer = await ai_helper.ask_ai(history)

        history.append({"role": "assistant", "content": answer})
        context.user_data['history'] = history

        for part in ai_helper.split_message(answer):
            await update.message.reply_text(part)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")        

async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_limit(update, context):
        return

    photo = update.message.photo[-1]
    caption = update.message.caption

    if caption:
        prompt = caption
    else:
        prompt = "Опиши подробно, что изображено на этой картинке. Если это задача — реши её."

    await update.message.reply_text("📸 Обрабатываю изображение...")

    try:
        file = await context.bot.get_file(photo.file_id)
        file_path = f"photo_{photo.file_unique_id}.jpg"
        await file.download_to_drive(file_path)

        answer = await ai_helper.ask_ai_with_image(file_path, prompt=prompt)
        os.remove(file_path)

        for part in ai_helper.split_message(answer):
            await update.message.reply_text(part)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def reset_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    await update.message.reply_text("🧹 История диалога очищена.")


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    reminders = db.get_pending_reminders()
    for r in reminders:
        try:
            await context.bot.send_message(
                chat_id=r['user_id'],
                text=f"⏰ Напоминание: {r['text']}"
            )
            db.mark_reminder_sent(r['id'])
        except Exception as e:
            logger.error(f"Ошибка напоминания: {e}")


def main():
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не задан!")
        return

    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("doc", doc_command))
    application.add_handler(CommandHandler("slides", slides_command))
    application.add_handler(CommandHandler("code", code_command))
    application.add_handler(CommandHandler("note", add_note))
    application.add_handler(CommandHandler("notes", list_notes))
    application.add_handler(CommandHandler("delnote", del_note))
    application.add_handler(CommandHandler("remind", add_reminder))
    application.add_handler(CommandHandler("habit", add_habit))
    application.add_handler(CommandHandler("habits", list_habits))
    application.add_handler(CommandHandler("ref", ref_command))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("reset", reset_chat))

    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.VOICE, voice_message))
    application.add_handler(MessageHandler(filters.PHOTO, photo_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))

    if application.job_queue:
        application.job_queue.run_repeating(check_reminders, interval=30, first=10)

    print("Бот запущен, ожидание сообщений...")
    application.run_polling()


if __name__ == '__main__':
    main()      
