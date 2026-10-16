import os
import base64
import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = (
    "Ты — личный помощник, говоришь по-русски, общаешься как реальный человек, "
    "как опытный друг, который шарит в теме. НЕ пиши 'Здравствуйте', 'Отличный вопрос', "
    "'Рад помочь', 'Конечно!' и прочую воду. Сразу переходи к делу.\n\n"
    "Правила:\n"
    "1. Отвечай коротко и по делу. Если можно ответить в 2 строчках — отвечай в 2 строчках.\n"
    "2. Говори честно, не выдумывай. Если не знаешь — так и скажи.\n"
    "3. Объясняй простыми словами, без академического тона.\n"
    "4. Если просят код — дай рабочий код с коротким пояснением.\n"
    "5. Если просят что-то сделать — делай сразу, не спрашивай лишнего.\n"
    "6. Не извиняйся без причины. Будь дружелюбным, но не подхалимничай."
)


async def ask_ai(messages):
    """Отправляет историю сообщений в ИИ и возвращает ответ."""
    if not GROQ_API_KEY:
        return "Ошибка: ключ API не задан."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    data = {
        "model": MODEL,
        "messages": full_messages,
        "max_tokens": 4096
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(API_URL, headers=headers, json=data)

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code}"

    except Exception as e:
        return f"Ошибка: {e}"


def split_message(text, max_length=4000):
    """Разбивает длинный текст на части для Telegram."""
    if len(text) <= max_length:
        return [text]

    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break

        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = max_length

        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    return parts


async def transcribe_audio(file_path):
    """Распознаёт голосовое сообщение в текст через Whisper."""
    if not GROQ_API_KEY:
        return "Ошибка: ключ API не задан."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, "audio/ogg"),
                    "model": (None, "whisper-large-v3-turbo"),
                }
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                )
        if response.status_code == 200:
            return response.json().get("text", "")
        else:
            return f"Ошибка API: {response.status_code}"
    except Exception as e:
        return f"Ошибка: {e}"


async def ask_ai_with_image(image_path, prompt="Реши задачу на этом изображении. Дай подробное решение."):
    """Отправляет изображение в ИИ через OpenRouter."""
    if not OPENROUTER_KEY:
        return "Ошибка: ключ OpenRouter не задан."

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    }
                ]
            }
        ],
        "max_tokens": 2048
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data
            )

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code} — {response.text[:300]}"

    except Exception as e:
        return f"Ошибка: {e}"