# 群管理助手机器人

一个合规的 Telegram 群管理机器人，部署在 Cloudflare Workers，**免费、免绑信用卡、真 7×24 在线**。

## 功能

| 功能 | 说明 | 命令 |
|---|---|---|
| 入群欢迎 | 新成员进群自动发送欢迎语（可自定义，`{name}` 代表昵称） | `/setwelcome <内容>` |
| 群规展示 | 一键查看群规 | `/rules`、`/setrules <内容>` |
| 关键词回复 | 管理员添加关键词，群成员发关键词自动回复 | `/addreply 关键词|回复`、`/delreply 关键词`、`/listreply` |
| 防广告 | 拦截非管理员的链接消息（需机器人为群管理员） | `/antispam on|off` |
| 权限控制 | 管理命令仅群管理员可用 | — |
| 健康检查 | 验证机器人存活 | `/ping` |

## 当前线上部署（Cloudflare Workers）

- Worker 地址：`https://group-admin-bot.<你的子域>.workers.dev/`
- Webhook：`https://group-admin-bot.<你的子域>.workers.dev/webhook`（校验 `X-Telegram-Bot-Api-Secret-Token`）
- 免费额度：100,000 请求/天，常驻不休眠
- 配置持久化：Workers KV（命名空间 `BOT_KV`，按群存储欢迎语/群规/关键词/防广告开关）

### 重新部署 / 更新（用 wrangler）

```bash
# 1. 安装依赖（Node.js 环境）
npm install -g wrangler

# 2. 登录（或设置 CLOUDFLARE_API_TOKEN 环境变量）
wrangler login

# 3. 部署（wrangler.toml 已配置 BOT_ID 变量与 BOT_KV 绑定）
wrangler deploy
```

### 设置 / 更新环境变量

| 变量名 | 类型 | 说明 |
|---|---|---|
| `BOT_TOKEN` | Secret | Telegram 机器人 Token |
| `WEBHOOK_SECRET` | Secret | Webhook 校验密钥（与 setWebhook 的 secret_token 一致） |
| `BOT_ID` | 明文 | 机器人数字 ID（可选，默认 getMe 自动获取） |

```bash
wrangler secret put BOT_TOKEN
wrangler secret put WEBHOOK_SECRET
```

### 设置 Telegram Webhook

```bash
curl -s -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://group-admin-bot.<你的子域>.workers.dev/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

## 文件说明

- `worker.js` — Cloudflare Workers 版机器人（ESM，/webhook + KV 持久化）
- `wrangler.toml` — wrangler 部署配置（含 BOT_KV 绑定）
- `bot.py` — 机器人主程序（Python，轮询/Webhook 双模式，本地调试用）
- `requirements.txt` — Python 依赖
- `Dockerfile`、`render.yaml` — Render 部署配置（备用方案，Render 免费版需绑卡）
- `.env.example` — 环境变量模板（复制为 `.env` 填写）
- `.env` — 本地 Token（已被 git 忽略，不会上传）

## 本地运行（测试用）

```bash
py -3.11 -m venv venv
venv\Scripts\pip install -r requirements.txt
# 确保 .env 里有 BOT_TOKEN
venv\Scripts\python bot.py
```

## 常用命令速查

```
/ping             存活检查
/rules            查看群规
/setrules 内容    设置群规（管理员）
/setwelcome 内容  设置欢迎语（管理员，空内容恢复默认）
/addreply 词|回复 添加关键词回复（管理员）
/delreply 词      删除关键词回复（管理员）
/listreply        查看关键词回复列表
/antispam on|off  开关防广告（管理员）
```

## 上线前安全检查

- 若 Token 曾在聊天/日志中明文出现，请在 @BotFather 执行 Revoke 后重新设置 `BOT_TOKEN` 并重设 Webhook；
- Cloudflare API 令牌用完即删（Profile → API Tokens），仅保留 wrangler 登录凭证。
