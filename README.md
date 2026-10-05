# 群管理助手机器人

一个合规的 Telegram 群管理机器人，支持 24 小时云端运行。

## 功能

| 功能 | 说明 | 命令 |
|---|---|---|
| 入群欢迎 | 新成员进群自动发送欢迎语（可自定义，`{name}` 代表昵称） | `/setwelcome <内容>` |
| 群规展示 | 一键查看群规 | `/rules`、`/setrules <内容>` |
| 关键词回复 | 管理员添加关键词，群成员发关键词自动回复 | `/addreply 关键词\|回复`、`/delreply 关键词`、`/listreply` |
| 防广告 | 拦截非管理员的链接消息（需机器人为群管理员） | `/antispam on\|off` |
| 权限控制 | 管理命令仅群管理员可用 | — |
| 健康检查 | 验证机器人存活 | `/ping` |

## 文件说明

- `bot.py` — 机器人主程序（轮询 / Webhook 双模式）
- `requirements.txt` — Python 依赖
- `Dockerfile` — 容器构建文件
- `render.yaml` — Render 云平台部署配置
- `.env.example` — 环境变量模板（复制为 `.env` 填写）
- `.env` — 本地 Token（已被 git 忽略，不会上传）
- `data/` — 运行时数据（自动生成）
- `logs/` — 运行日志（自动生成）

## 本地运行（测试用）

```bash
py -3.11 -m venv venv
venv\Scripts\pip install -r requirements.txt
# 确保 .env 里有 BOT_TOKEN
venv\Scripts\python bot.py
```

## 云端 24 小时部署（Render 免费版）

### 第 1 步：把代码放到 GitHub 公开仓库（约 5 分钟，纯网页操作）

1. 打开 https://github.com/new 新建一个仓库，名字随意（如 `group-admin-bot`），可见性选 **Public**；
2. 创建后进入仓库页面，点 **Add file → Upload files**；
3. 把以下 **5 个文件** 拖进上传框（**不要**上传 `.env`、`data/`、`logs/`、`venv/`）：
   - `bot.py`
   - `requirements.txt`
   - `Dockerfile`
   - `render.yaml`
   - `README.md`
4. 点 **Commit changes** 提交。

### 第 2 步：注册 Render（约 5 分钟，邮箱即可，无需信用卡）

1. 打开 https://render.com ，点 **Get Started / Sign up**，用邮箱注册并验证；
2. 登录后进入控制台 dashboard。

### 第 3 步：导入并部署

1. 点 **New → Blueprint Instance**（或 New → Web Service）；
2. 粘贴你 GitHub 仓库的地址（如 `https://github.com/你的用户名/group-admin-bot`），点 **Continue**；
3. 在环境变量（Environment）里设置两项：

   | 变量名 | 值 |
   |---|---|
   | `BOT_TOKEN` | `你的机器人Token` |
   | `WEBHOOK_URL` | `https://你的服务名.onrender.com`（服务名 = 第 4 步填的名字） |

4. 服务名填 `group-admin-bot`（或任意名字），Plan 选 **Free**，点 **Deploy**；
5. 等构建完成（约 2-5 分钟），状态变 **Live** 即成功。

### 第 4 步：验证

1. 在 Telegram 私聊你的机器人，发 `/ping`，应回复 `pong ✅`；
2. 把机器人拉进你的群，**在群设置里把机器人设为管理员**（否则防广告无法删消息）；
3. 让一个新人进群测试欢迎语；管理员发 `/setrules 群规内容` 测试群规。

## 免费实例须知（重要）

- Render 免费实例闲置 15 分钟后会休眠，收到消息时自动唤醒（冷启动约 30-60 秒，第一条回复可能稍慢，之后正常）；
- `data/` 里的欢迎语/群规/关键词配置保存在实例磁盘上，**重新部署后会被重置**；如需跨重启保留配置，后续可升级为 PostgreSQL 存储；
- 免费额度 750 实例小时/月，按需唤醒的用量完全够用。

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
