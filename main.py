import os
import io
import json
import time
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BotCommand

# Супер-мотор заведён!
BOT_TOKEN = "8756947943:AAGlks0pwb9gkdXErTHdj1fnnkAJOt-6LMc"
MINIMAX_API_KEY = "sk-api-6FZUguzV5Y51HVQvpoa6Fn0Blr_d9comCh_hZ6EJrHL516j55VoDVCQSZen3JQafjjXiV3QIAw2GvWqfR8O8QtRpDaBTf-ZdWoLFLOEN7gYZ6nJ6-QgYjvk"
ADMIN_ID = 6687790461
GENERATE_URL = "https://api.minimax.chat/v1/music_generation"
MODEL_NAME = "music-2.6-free"
PROMOS_FILE = "promos.json"
USERS_FILE = "users.json"
DAILY_GIFT = 2
DAILY_COOLDOWN = 86400

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_selections = {}

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def get_user_data(user_id: int) -> dict:
    users = load_json(USERS_FILE)
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"generations": 4, "last_daily": 0}
        save_json(USERS_FILE, users)
    return users[uid]

def use_generation(user_id: int) -> bool:
    users = load_json(USERS_FILE)
    uid = str(user_id)
    if uid in users and users[uid]["generations"] > 0:
        users[uid]["generations"] -= 1
        save_json(USERS_FILE, users)
        return True
    return False

def add_generations(user_id: int, amount: int):
    users = load_json(USERS_FILE)
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"generations": 4, "last_daily": 0}
    users[uid]["generations"] += amount
    save_json(USERS_FILE, users)

def can_get_daily(user_id: int):
    data = get_user_data(user_id)
    now = int(time.time())
    last = data.get("last_daily", 0)
    if now - last >= DAILY_COOLDOWN:
        return True, 0
    remain = DAILY_COOLDOWN - (now - last)
    return False, remain

async def generate_music(prompt: str, lyrics: str):
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3"
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GENERATE_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    logging.error(f"MiniMax error: {await resp.text()}")
                    return None
                data = await resp.json()
                audio_hex = data.get("data", {}).get("audio")
                if audio_hex:
                    return bytes.fromhex(audio_hex)
                return None
    except Exception as e:
        logging.error(f"Network error: {e}")
        return None

# ========== АДМИН-КОМАНДЫ ==========
@dp.message(Command("addpromo"))
async def add_promo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3:
        return await message.reply("Формат: /addpromo <код> <количество>")
    code = args[1].upper()
    try: gens = int(args[2])
    except ValueError: return await message.reply("Количество должно быть числом.")
    promos = load_json(PROMOS_FILE)
    if code in promos:
        return await message.reply("Такой промокод уже есть.")
    promos[code] = {"uses_left": gens, "generations_per_use": gens}
    save_json(PROMOS_FILE, promos)
    await message.reply(f"✅ Промокод {code} создан. Даёт {gens} ген.")

@dp.message(Command("delpromo"))
async def del_promo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 2: return await message.reply("Формат: /delpromo <код>")
    code = args[1].upper()
    promos = load_json(PROMOS_FILE)
    if code not in promos: return await message.reply("Нет такого кода.")
    del promos[code]
    save_json(PROMOS_FILE, promos)
    await message.reply(f"🗑 Промокод {code} удалён.")

@dp.message(Command("listpromos"))
async def list_promos(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    promos = load_json(PROMOS_FILE)
    if not promos: return await message.reply("Промокодов нет.")
    text = "🎟 Активные промокоды:\n"
    for c, d in promos.items():
        text += f"• {c} — ост. {d['uses_left']} активаций\n"
    await message.reply(text)

@dp.message(Command("give"))
async def give_generations(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3: return await message.reply("Формат: /give <id> <кол-во>")
    try:
        target = int(args[1])
        amount = int(args[2])
    except ValueError: return await message.reply("ID и количество — числа.")
    add_generations(target, amount)
    await message.reply(f"✅ Пользователю {target} начислено {amount} ген.")

# ========== ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ ==========
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    data = get_user_data(message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="🎵 Создать песню", callback_data="create_music")
    await message.reply(
        f"🎵 Привет! Я бот-композитор.\nУ тебя <b>{data['generations']}</b> генераций.\n"
        "Выбери действие или команды: /activate КОД, /daily, /id",
        parse_mode="HTML", reply_markup=builder.as_markup()
    )

@dp.message(Command("id"))
async def show_id(message: types.Message):
    await message.reply(f"Твой ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

@dp.message(Command("activate"))
async def activate_promo(message: types.Message):
    args = message.text.split()
    if len(args) != 2: return await message.reply("Формат: /activate КОД")
    code = args[1].upper()
    promos = load_json(PROMOS_FILE)
    if code not in promos: return await message.reply("Неверный промокод.")
    if promos[code]["uses_left"] <= 0: return await message.reply("Промокод закончился.")
    gens = promos[code]["generations_per_use"]
    promos[code]["uses_left"] -= 1
    if promos[code]["uses_left"] == 0: del promos[code]
    save_json(PROMOS_FILE, promos)
    add_generations(message.from_user.id, gens)
    await message.reply(f"🎉 Промокод активирован! +{gens} генераций.")

@dp.message(Command("daily"))
async def daily_gift(message: types.Message):
    user_id = message.from_user.id
    can, remain = can_get_daily(user_id)
    if not can:
        h = remain // 3600
        m = (remain % 3600) // 60
        return await message.reply(f"⏳ Приходи через {h} ч {m} мин.")
    add_generations(user_id, DAILY_GIFT)
    data = get_user_data(user_id)
    data["last_daily"] = int(time.time())
    save_json(user_id, data)
    await message.reply(f"🎁 +{DAILY_GIFT} ген! Теперь у тебя {data['generations']} ген.")

@dp.callback_query(F.data == "create_music")
async def ask_genre(callback: types.CallbackQuery):
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎸 Поп", callback_data="genre_pop")
    builder.button(text="🎹 Рок", callback_data="genre_rock")
    builder.button(text="🎺 Хип-хоп", callback_data="genre_hiphop")
    builder.button(text="🎻 Классика", callback_data="genre_classical")
    builder.button(text="🎷 Джаз", callback_data="genre_jazz")
    builder.button(text="💃 Танцевальная", callback_data="genre_dance")
    builder.button(text="😢 Грустная", callback_data="genre_sad")
    builder.button(text="🌟 Свой стиль", callback_data="genre_custom")
    builder.adjust(2)
    await callback.message.reply("Выбери стиль:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("genre_"))
async def process_genre(callback: types.CallbackQuery):
    await callback.answer()
    genre = callback.data.split("_")[1]
    if genre == "custom":
        user_selections[callback.from_user.id] = {"state": "waiting_genre"}
        return await callback.message.reply("Опиши стиль своими словами:")
    user_selections[callback.from_user.id] = {"genre": genre}
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Мужской", callback_data="voice_male")
    builder.button(text="👩 Женский", callback_data="voice_female")
    builder.button(text="🎤 Дуэт", callback_data="voice_duet")
    builder.button(text="🤷 Любой", callback_data="voice_any")
    builder.adjust(2)
    await callback.message.reply("Выбери голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("voice_"))
async def process_voice(callback: types.CallbackQuery):
    await callback.answer()
    voice = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_selections: user_selections[uid] = {}
    user_selections[uid]["voice"] = voice
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Я напишу текст", callback_data="mode_lyrics")
    builder.button(text="💡 Только название", callback_data="mode_title")
    builder.adjust(1)
    await callback.message.reply("Как создаём?", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("mode_"))
async def process_mode(callback: types.CallbackQuery):
    await callback.answer()
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_selections: user_selections[uid] = {}
    user_selections[uid]["mode"] = mode
    if mode == "title":
        user_selections[uid]["state"] = "waiting_title"
        await callback.message.reply("Напиши название будущей песни:")
    else:
        user_selections[uid]["state"] = "waiting_lyrics"
        await callback.message.reply(
            "Пришли мне текст.\n"
            "Можно с тегами [verse], [chorus] и т.д.\n"
            "Например:\n"
            "[verse]\nСегодня лучший день...\n"
            "[chorus]\nИ танцует весь мир...")

@dp.message()
async def handle_all(message: types.Message):
    if message.text and message.text.startswith("/"): return
    uid = message.from_user.id
    sel = user_selections.get(uid, {})

    if sel.get("state") == "waiting_genre":
        sel["genre"] = message.text.strip()
        sel["state"] = None
        user_selections[uid] = sel
        builder = InlineKeyboardBuilder()
        builder.button(text="👨 Мужской", callback_data="voice_male")
        builder.button(text="👩 Женский", callback_data="voice_female")
        builder.button(text="🎤 Дуэт", callback_data="voice_duet")
        builder.button(text="🤷 Любой", callback_data="voice_any")
        builder.adjust(2)
        return await message.reply("Выбери голос:", reply_markup=builder.as_markup())

    if sel.get("state") in ("waiting_lyrics", "waiting_title"):
        text = message.text.strip()
        if not text:
            return await message.reply("Пожалуйста, введи текст или название.")
        await start_generation(message, sel, text)
        return

    await manual_generation(message)

async def start_generation(message, sel, text):
    uid = message.from_user.id
    data = get_user_data(uid)
    if data["generations"] <= 0:
        await message.reply(
            "😢 У тебя закончились генерации.\n"
            "Попроси у админа (@Battlebobil) промокод или подарок, "
            "или возвращайся завтра за ежедневным бонусом!\n"
            "Напиши /daily, чтобы проверить.")
        return

    genre = sel.get("genre", "pop")
    voice = sel.get("voice", "any")
    mode = sel.get("mode", "lyrics")

    genre_map = {
        "pop": "поп", "rock": "рок", "hiphop": "хип-хоп",
        "classical": "классика", "jazz": "джаз", "dance": "танцевальная",
        "sad": "грустная"
    }
    voice_map = {
        "male": "мужской вокал", "female": "женский вокал",
        "duet": "дуэт", "any": ""
    }

    prompt = f"{genre_map.get(genre, genre)}, {voice_map.get(voice, voice)}".strip(", ")
    lyrics = f"[verse]\n{text}\n[chorus]\n{text}" if mode == "title" else text

    if not use_generation(uid):
        return await message.reply("Не удалось списать генерацию.")

    msg = await message.reply(f"🎼 Готовлю трек...")
    audio_bytes = await generate_music(prompt, lyrics)

    if audio_bytes is None:
        add_generations(uid, 1)
        return await msg.edit_text("😔 Ошибка. Генерация возвращена.")

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "song.mp3"
    await msg.delete()
    await message.reply_audio(audio=audio_file, caption=f"🎤 Твой трек готов!")
    user_selections.pop(uid, None)

async def manual_generation(message):
    uid = message.from_user.id
    data = get_user_data(uid)
    if data["generations"] <= 0:
        await message.reply(
            "😢 У тебя закончились генерации.\n"
            "Попроси у админа (@Battlebobil) промокод или подарок, "
            "или возвращайся завтра за ежедневным бонусом!\n"
            "Напиши /daily, чтобы проверить.")
        return
    if '|' not in message.text:
        return await message.reply("Используй кнопки или формат: Жанр | Текст песни")
    parts = message.text.split('|', 1)
    prompt = parts[0].strip()
    lyrics = parts[1].strip()
    if not prompt or not lyrics:
        return await message.reply("Заполни и жанр, и текст.")
    if not use_generation(uid):
        return await message.reply("Не удалось списать генерацию.")
    msg = await message.reply(f"🎼 Готовлю трек...")
    audio_bytes = await generate_music(prompt, lyrics)
    if audio_bytes is None:
        add_generations(uid, 1)
        return await msg.edit_text("😔 Ошибка. Генерация возвращена.")
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "song.mp3"
    await msg.delete()
    await message.reply_audio(audio=audio_file, caption=f"🎤 Трек готов!")
    await message.reply(f"Осталось генераций: {get_user_data(uid)['generations']}")

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Главное меню"),
        BotCommand(command="/activate", description="Активировать промокод"),
        BotCommand(command="/daily", description="Ежедневный бонус"),
        BotCommand(command="/id", description="Узнать свой ID"),
    ]
    await bot.set_my_commands(commands)

async def main():
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
