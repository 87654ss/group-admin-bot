/**
 * 群管理助手机器人 - Cloudflare Workers 版
 *
 * 功能：入群欢迎、群规、关键词自动回复、防广告、管理员指令
 * 持久化：Cloudflare KV（绑定名 BOT_KV），按群存储配置（欢迎语/群规/关键词/防广告开关）
 *
 * 环境变量 / Secrets：
 *   BOT_TOKEN       机器人 Token（Secret）
 *   WEBHOOK_SECRET  Webhook 密钥（Secret，Telegram 请求头校验）
 *   BOT_ID          机器人数字 ID（可选，默认 getMe 自动获取）
 *
 * KV 绑定：BOT_KV
 */

const DEFAULT_WELCOME =
  "欢迎 {name} 加入本群！\n\n请先阅读群规（发送 /rules 查看），文明交流。\n有任何问题可以联系群管理员。";

const HELP_TEXT = [
  "你好，我是群管理助手。",
  "",
  "可用指令：",
  "/rules - 查看群规",
  "/ping - 健康检查",
  "/help - 帮助",
  "",
  "管理员可用：",
  "/setwelcome <内容> - 设置入群欢迎（可用 {name} 代表新成员昵称）",
  "/setrules <内容> - 设置群规",
  "/addreply 关键词|回复 - 添加关键词自动回复",
  "/delreply 关键词 - 删除关键词回复",
  "/listreply - 查看关键词回复列表",
  "/antispam on|off - 开关广告拦截",
  "",
  "管理命令请在群内使用。",
].join("\n");

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/webhook" && request.method === "POST") {
      const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
      if (env.WEBHOOK_SECRET && secret !== env.WEBHOOK_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      let update;
      try {
        update = await request.json();
      } catch {
        return new Response("Bad Request", { status: 400 });
      }
      ctx.waitUntil(processUpdate(update, env));
      return new Response("OK", { status: 200 });
    }
    return new Response("群管理助手机器人运行中", { status: 200 });
  },
};

/** 调用 Telegram Bot API */
async function api(method, params, env) {
  try {
    const res = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    return await res.json();
  } catch (e) {
    console.error("api error", method, e);
    return null;
  }
}

async function send(chatId, text, env) {
  return api("sendMessage", { chat_id: chatId, text }, env);
}

async function getBotId(env) {
  if (env.BOT_ID) return String(env.BOT_ID);
  const me = await api("getMe", {}, env);
  return me && me.ok ? String(me.result.id) : "0";
}

/** 读取某个群的配置（不存在则返回默认值） */
async function getCfg(chatId, env) {
  const key = "chat:" + chatId;
  const raw = await env.BOT_KV.get(key);
  if (raw) {
    try {
      return JSON.parse(raw);
    } catch (e) {}
  }
  return { welcome: DEFAULT_WELCOME, rules: "", replies: {}, antispam: false };
}

async function saveCfg(chatId, cfg, env) {
  const key = "chat:" + chatId;
  await env.BOT_KV.put(key, JSON.stringify(cfg));
}

/** 判断用户是否为群管理员/群主 */
async function isAdmin(chatId, userId, env) {
  try {
    const r = await api("getChatMember", { chat_id: chatId, user_id: userId }, env);
    if (r && r.ok) {
      return r.result.status === "administrator" || r.result.status === "creator";
    }
  } catch (e) {}
  return false;
}

function isGroup(chat) {
  return chat && (chat.type === "group" || chat.type === "supergroup");
}

/** 处理一条 Telegram 更新 */
async function processUpdate(update, env) {
  try {
    const msg = update.message;
    if (!msg) return;
    const chat = msg.chat;
    const chatId = chat.id;

    // 入群欢迎
    if (msg.new_chat_members && msg.new_chat_members.length > 0) {
      const botId = await getBotId(env);
      for (const m of msg.new_chat_members) {
        if (String(m.id) === botId) {
          await send(chatId, "大家好，我是群管理助手，已就位！", env);
          continue;
        }
        const cfg = await getCfg(chatId, env);
        const name = m.first_name || m.username || "新成员";
        const welcome = (cfg.welcome || DEFAULT_WELCOME).replace(/\{name\}/g, name);
        await send(chatId, welcome, env);
      }
      return;
    }

    const text = (msg.text || "").trim();
    const from = msg.from;
    if (!text || !from) return;
    if (String(from.id) === String(await getBotId(env))) return;

    if (text.startsWith("/")) {
      await handleCommand(text, chat, from, env);
      return;
    }

    // 普通文本：防广告 + 关键词回复
    const cfg = await getCfg(chatId, env);

    if (cfg.antispam && !(await isAdmin(chatId, from.id, env))) {
      const LINK_RE = /(https?:\/\/|t\.me\/|www\.)/i;
      if (LINK_RE.test(text)) {
        try {
          await api("deleteMessage", { chat_id: chatId, message_id: msg.message_id }, env);
        } catch (e) {}
        const name = from.first_name || from.username || "";
        await send(chatId, `⚠️ ${name} 请勿在群内发送广告/链接。`, env);
        return;
      }
    }

    const replies = cfg.replies || {};
    const lower = text.toLowerCase();
    for (const k of Object.keys(replies)) {
      if (k.toLowerCase() === lower) {
        await send(chatId, replies[k], env);
        return;
      }
    }
  } catch (e) {
    console.error("processUpdate error:", e);
  }
}

/** 处理命令 */
async function handleCommand(text, chat, from, env) {
  const chatId = chat.id;
  const afterSlash = text.slice(1);
  const parts = afterSlash.split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const args = afterSlash.slice(parts[0].length).trim();
  const isPriv = chat.type === "private";

  const requireAdmin = async () => {
    if (isPriv) {
      await send(chatId, "请在群内使用该命令。", env);
      return null;
    }
    if (!(await isAdmin(chatId, from.id, env))) {
      await send(chatId, "只有群管理员可以使用该命令。", env);
      return null;
    }
    return true;
  };

  switch (cmd) {
    case "ping":
      await send(chatId, "pong ✅", env);
      break;
    case "start":
    case "help":
      await send(chatId, HELP_TEXT, env);
      break;
    case "rules": {
      if (isPriv) {
        await send(chatId, "请在群内使用 /rules。", env);
        break;
      }
      const cfg = await getCfg(chatId, env);
      await send(chatId, cfg.rules ? "📋 群规：\n" + cfg.rules : "本群暂未设置群规。", env);
      break;
    }
    case "setrules": {
      const ok = await requireAdmin();
      if (!ok) break;
      if (!args) {
        await send(chatId, "用法：/setrules 群规内容", env);
        break;
      }
      const cfg = await getCfg(chatId, env);
      cfg.rules = args;
      await saveCfg(chatId, cfg, env);
      await send(chatId, "✅ 群规已更新。", env);
      break;
    }
    case "setwelcome": {
      const ok = await requireAdmin();
      if (!ok) break;
      const cfg = await getCfg(chatId, env);
      if (!args) {
        cfg.welcome = DEFAULT_WELCOME;
        await saveCfg(chatId, cfg, env);
        await send(chatId, "✅ 已恢复默认欢迎语。", env);
      } else {
        cfg.welcome = args;
        await saveCfg(chatId, cfg, env);
        await send(chatId, "✅ 欢迎语已更新。可用 {name} 代表新成员昵称。", env);
      }
      break;
    }
    case "addreply": {
      const ok = await requireAdmin();
      if (!ok) break;
      const idx = args.indexOf("|");
      if (idx <= 0 || idx === args.length - 1) {
        await send(chatId, "用法：/addreply 关键词|回复内容", env);
        break;
      }
      const keyword = args.slice(0, idx).trim();
      const reply = args.slice(idx + 1).trim();
      if (!keyword || !reply) {
        await send(chatId, "关键词和回复内容都不能为空。", env);
        break;
      }
      const cfg = await getCfg(chatId, env);
      cfg.replies = cfg.replies || {};
      cfg.replies[keyword] = reply;
      await saveCfg(chatId, cfg, env);
      await send(chatId, `✅ 已添加关键词：${keyword}`, env);
      break;
    }
    case "delreply": {
      const ok = await requireAdmin();
      if (!ok) break;
      const keyword = args.trim();
      if (!keyword) {
        await send(chatId, "用法：/delreply 关键词", env);
        break;
      }
      const cfg = await getCfg(chatId, env);
      if (cfg.replies && Object.prototype.hasOwnProperty.call(cfg.replies, keyword)) {
        delete cfg.replies[keyword];
        await saveCfg(chatId, cfg, env);
        await send(chatId, `✅ 已删除关键词：${keyword}`, env);
      } else {
        await send(chatId, "该关键词不存在。", env);
      }
      break;
    }
    case "listreply": {
      if (isPriv) {
        await send(chatId, "请在群内查看关键词列表。", env);
        break;
      }
      const cfg = await getCfg(chatId, env);
      const replies = cfg.replies || {};
      const keys = Object.keys(replies);
      if (!keys.length) {
        await send(chatId, "本群暂无关键词回复。", env);
        break;
      }
      await send(
        chatId,
        "📋 关键词回复列表：\n" + keys.map((k) => `${k} → ${replies[k]}`).join("\n"),
        env
      );
      break;
    }
    case "antispam": {
      const ok = await requireAdmin();
      if (!ok) break;
      const arg = args.toLowerCase();
      const cfg = await getCfg(chatId, env);
      if (arg === "on") {
        cfg.antispam = true;
        await saveCfg(chatId, cfg, env);
        await send(chatId, "✅ 广告拦截已开启（需要机器人是群管理员并有删除权限）。", env);
      } else if (arg === "off") {
        cfg.antispam = false;
        await saveCfg(chatId, cfg, env);
        await send(chatId, "✅ 广告拦截已关闭。", env);
      } else {
        await send(chatId, "用法：/antispam on 或 /antispam off", env);
      }
      break;
    }
    default:
      // 未知命令不回复
      break;
  }
}
