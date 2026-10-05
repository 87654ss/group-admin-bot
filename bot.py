# -*- coding: utf-8 -*-
"""
群管理助手机器人

功能：
- 入群欢迎（可自定义，支持 {name} 占位符）
- 群规展示 /rules（管理员可设置 /setrules）
- 关键词自动回复（管理员可增删 /addreply /delreply /listreply）
- 防广告开关 /antispam on|off（需机器人为群管理员且有删除权限）
- 管理命令仅限群管理员使用
- 数据存储：data/bot_data.json；日志：logs/bot.log

启动方式：
- 本地轮询：设置环境变量 BOT_TOKEN（或项目根目录 .env 文件）后运行 python bot.py
- 云端 Webhook：再设置 WEBHOOK_URL（如 https://xxx.onrender.com）与 PORT，机器人会自动注册 Webhook
"""

import json
import logging
import os
import re
import threading
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from telegram import ChatMember, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
PORT = int(os.getenv("PORT", "8080"))
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "bot_data.json")
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger("group_bot")

if not BOT_TOKEN:
    logger.error("未设置 BOT_TOKEN 环境变量，机器人无法启动。")
    raise SystemExit(1)

DEFAULT_WELCOME = (
    "欢迎 {name} 加入本群！\n\n"
    "请先阅读群规（发送 /rules 查看），文明交流。\n"
    "有任何问题可以联系群管理员。"
)

DATA_LOCK = threading.Lock()


def load_data():
    """读取全部群数据"""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("读取数据文件失败: %s", exc)
        return {}


def save_data(data):
    """原子写入数据文件"""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def get_group(chat_id):
    """获取某个群的配置（不存在则初始化）"""
    with DATA_LOCK:
        data = load_data()
        gid = str(chat_id)
        if gid not in data:
            data[gid] = {
                "welcome": DEFAULT_WELCOME,
                "rules": "",
                "replies": {},
                "antispam": False,
            }
            save_data(data)
        return data[gid]


def update_group(chat_id, group):
    """保存某个群的配置"""
    with DATA_LOCK:
        data = load_data()
        data[str(chat_id)] = group
        save_data(data)


async def is_admin(context, chat_id, user_id):
    """判断用户是否为群管理员/群主"""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception as exc:
        logger.warning("查询成员权限失败: %s", exc)
        return False


def is_private(update):
    return update.effective_chat is not None and update.effective_chat.type == "private"


# ---------- 基础命令 ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是群管理助手。\n\n"
        "可用指令：\n"
        "/rules - 查看群规\n"
        "/ping - 健康检查\n"
        "/help - 帮助\n\n"
        "管理员可用：\n"
        "/setwelcome <内容> - 设置入群欢迎（可用 {name} 代表新成员昵称）\n"
        "/setrules <内容> - 设置群规\n"
        "/addreply 关键词|回复 - 添加关键词自动回复\n"
        "/delreply 关键词 - 删除关键词回复\n"
        "/listreply - 查看关键词回复列表\n"
        "/antispam on|off - 开关广告拦截\n\n"
        "管理命令请在群内使用。"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


# ---------- 入群欢迎 ----------

async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.message.reply_text("大家好，我是群管理助手，已就位！")
            continue
        group = get_group(chat.id)
        welcome = group.get("welcome") or DEFAULT_WELCOME
        name = member.full_name or member.username or "新成员"
        try:
            await update.message.reply_text(welcome.format(name=name))
        except Exception:
            await update.message.reply_text(welcome)


# ---------- 群规 ----------

async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内使用 /rules。")
        return
    group = get_group(chat.id)
    rules = (group.get("rules") or "").strip()
    if not rules:
        await update.message.reply_text("本群暂未设置群规。")
        return
    await update.message.reply_text("📋 群规：\n" + rules)


async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.effective_user is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内设置群规。")
        return
    if not await is_admin(context, chat.id, update.effective_user.id):
        await update.message.reply_text("只有群管理员可以设置群规。")
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("用法：/setrules 群规内容")
        return
    group = get_group(chat.id)
    group["rules"] = text
    update_group(chat.id, group)
    await update.message.reply_text("✅ 群规已更新。")


# ---------- 欢迎语 ----------

async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.effective_user is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内设置欢迎语。")
        return
    if not await is_admin(context, chat.id, update.effective_user.id):
        await update.message.reply_text("只有群管理员可以设置欢迎语。")
        return
    text = " ".join(context.args).strip()
    group = get_group(chat.id)
    if not text:
        group["welcome"] = DEFAULT_WELCOME
        update_group(chat.id, group)
        await update.message.reply_text("✅ 已恢复默认欢迎语。")
        return
    group["welcome"] = text
    update_group(chat.id, group)
    await update.message.reply_text("✅ 欢迎语已更新。可用 {name} 代表新成员昵称。")


# ---------- 关键词回复 ----------

async def cmd_addreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.effective_user is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内添加关键词回复。")
        return
    if not await is_admin(context, chat.id, update.effective_user.id):
        await update.message.reply_text("只有群管理员可以添加关键词回复。")
        return
    text = " ".join(context.args).strip()
    if "|" not in text:
        await update.message.reply_text("用法：/addreply 关键词|回复内容")
        return
    keyword, reply = text.split("|", 1)
    keyword = keyword.strip()
    reply = reply.strip()
    if not keyword or not reply:
        await update.message.reply_text("关键词和回复内容都不能为空。")
        return
    group = get_group(chat.id)
    group["replies"][keyword] = reply
    update_group(chat.id, group)
    await update.message.reply_text(f"✅ 已添加关键词：{keyword}")


async def cmd_delreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.effective_user is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内删除关键词回复。")
        return
    if not await is_admin(context, chat.id, update.effective_user.id):
        await update.message.reply_text("只有群管理员可以删除关键词回复。")
        return
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("用法：/delreply 关键词")
        return
    group = get_group(chat.id)
    if keyword in group["replies"]:
        del group["replies"][keyword]
        update_group(chat.id, group)
        await update.message.reply_text(f"✅ 已删除关键词：{keyword}")
    else:
        await update.message.reply_text("该关键词不存在。")


async def cmd_listreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内查看关键词列表。")
        return
    group = get_group(chat.id)
    replies = group.get("replies", {})
    if not replies:
        await update.message.reply_text("本群暂无关键词回复。")
        return
    lines = [f"{k} → {v}" for k, v in replies.items()]
    await update.message.reply_text("📋 关键词回复列表：\n" + "\n".join(lines))


# ---------- 防广告 ----------

LINK_RE = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)


async def cmd_antispam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or update.effective_user is None:
        return
    if is_private(update):
        await update.message.reply_text("请在群内操作。")
        return
    if not await is_admin(context, chat.id, update.effective_user.id):
        await update.message.reply_text("只有群管理员可以开关防广告。")
        return
    arg = (context.args[0] if context.args else "").lower()
    group = get_group(chat.id)
    if arg == "on":
        group["antispam"] = True
        update_group(chat.id, group)
        await update.message.reply_text("✅ 广告拦截已开启（需要机器人是群管理员并有删除权限）。")
    elif arg == "off":
        group["antispam"] = False
        update_group(chat.id, group)
        await update.message.reply_text("✅ 广告拦截已关闭。")
    else:
        await update.message.reply_text("用法：/antispam on 或 /antispam off")


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """普通文本消息：广告拦截 + 关键词回复"""
    chat = update.effective_chat
    message = update.message
    user = update.effective_user
    if chat is None or message is None or user is None:
        return
    if user.id == context.bot.id:
        return
    if chat.type not in ("group", "supergroup"):
        return
    text = (message.text or "").strip()

    group = get_group(chat.id)

    # 广告拦截：非管理员发送链接即删除并警告
    if group.get("antispam") and not await is_admin(context, chat.id, user.id):
        if LINK_RE.search(text):
            try:
                await message.delete()
                await message.reply_text(
                    f"⚠️ {user.full_name or user.username} 请勿在群内发送广告/链接。"
                )
            except Exception as exc:
                logger.warning("删除广告消息失败（请确认机器人为群管理员）: %s", exc)
            return

    # 关键词自动回复（大小写不敏感）
    replies = group.get("replies", {})
    if text:
        lower_map = {k.lower(): v for k, v in replies.items()}
        reply = lower_map.get(text.lower())
        if reply:
            await message.reply_text(reply)


# ---------- 错误处理 ----------

async def on_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("处理更新时出错: %s", context.error)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                ADMIN_CHAT_ID,
                f"⚠️ 机器人出错：{type(context.error).__name__}: {context.error}",
            )
        except Exception:
            pass


# ---------- 启动 ----------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("setrules", cmd_setrules))
    app.add_handler(CommandHandler("setwelcome", cmd_setwelcome))
    app.add_handler(CommandHandler("addreply", cmd_addreply))
    app.add_handler(CommandHandler("delreply", cmd_delreply))
    app.add_handler(CommandHandler("listreply", cmd_listreply))
    app.add_handler(CommandHandler("antispam", cmd_antispam))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
    app.add_error_handler(on_error)

    if WEBHOOK_URL:
        logger.info("以 Webhook 模式启动，PORT=%s，路径=%s", PORT, WEBHOOK_PATH)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH,
            secret_token=WEBHOOK_SECRET or None,
            allowed_updates=["message"],
        )
    else:
        logger.info("以轮询模式启动（本地/测试）")
        app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
