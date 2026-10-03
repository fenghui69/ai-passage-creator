# AI 爆款文章创作器

> 基于多智能体（Multi-Agent）编排的 AI 图文文章创作平台。用户输入选题与风格，系统自动完成**标题方案 → 大纲 → 正文 → 配图方案 → 配图生成 → 图文合成**的全流程，并支持关键节点的人工确认与编辑。

后端使用 **FastAPI + SQLAlchemy + 阿里云 DashScope（Qwen）**，前端使用 **Vue 3 + Vite + Ant Design Vue**，通过 **SSE** 实时推送创作进度。

---

## 目录

- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [多智能体创作流程](#多智能体创作流程)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [API 接口概览](#api-接口概览)
- [数据库设计](#数据库设计)
- [默认账号](#默认账号)
- [开发命令](#开发命令)

---

## 核心功能

| 模块 | 说明 |
| --- | --- |
| 📝 AI 文章创作 | 输入选题 + 补充描述 + 文章风格，一键生成完整图文文章 |
| 🧠 多智能体编排 | 6 个智能体分工协作，支持流式输出与并行配图 |
| 🖐 分阶段人工干预 | 标题方案选择、大纲在线编辑、AI 辅助改大纲 |
| 🎨 多种配图方式 | 图库检索、AI 生图、Mermaid 流程图、Iconify 图标、表情包、SVG 示意图，失败自动降级 |
| ⚡ SSE 实时进度 | 实时推送每个智能体的执行状态、流式文本与配图进度 |
| 📊 智能体日志 | 记录每个智能体的 Prompt、输入输出、耗时与执行状态 |
| 👤 用户体系 | 注册 / 登录 / 权限管理，基于 Session + Redis |
| 🎫 配额与会员 | 新用户默认 5 次配额，Stripe 支付开通永久 VIP 会员，支持退款 |
| 📈 数据统计 | 管理端查看文章、用户、智能体执行等统计数据 |

### 文章风格

`tech`（科技）、`emotional`（情感）、`educational`（教育）、`humorous`（幽默）

### 配图方式

| 枚举值 | 说明 | 类型 |
| --- | --- | --- |
| `PEXELS` | Pexels 图库检索 | 图库 |
| `NANO_BANANA` | Gemini (Nano Banana) AI 生图 | AI 生成 |
| `MERMAID` | Mermaid CLI 生成流程图 | AI 生成 |
| `SVG_DIAGRAM` | SVG 示意图 | AI 生成 |
| `ICONIFY` | Iconify 图标库 | 素材 |
| `EMOJI_PACK` | Bing 图片搜索表情包 | 素材 |
| `PICSUM` | 随机占位图（**降级方案**） | 降级 |

所有图片统一上传至**腾讯云 COS** 后再写入文章。

---

## 技术栈

### 前端（`frontend/`）

- **Vue 3.5** + **TypeScript** + **Vite 7**
- **Ant Design Vue 4** 组件库
- **Pinia** 状态管理、**Vue Router 4** 路由
- **Axios** 请求封装、**marked** Markdown 渲染、**ECharts** 图表
- **@umijs/openapi** 依据后端 OpenAPI 生成 TS 接口代码
- ESLint + Prettier

### 后端（`python-backend/`）

- **Python 3.12** + **FastAPI 0.115** + **Uvicorn**
- **SQLAlchemy 2 + databases[mysql]**（MySQL 8 异步访问）
- **Redis** 会话存储、**Passlib** 密码工具
- **OpenAI SDK**（DashScope 兼容模式调用 Qwen 模型流式生成）
- **google-genai**（Nano Banana 生图）、**Stripe**（支付）、**cos-python-sdk-v5**（对象存储）
- **@mermaid-js/mermaid-cli** 生成流程图
- 依赖管理：**uv**（`pyproject.toml` + `uv.lock`）

---

## 系统架构

```
ai-passage-creator/
├── frontend/                    # Vue 3 前端
│   ├── src/
│   │   ├── api/                 # OpenAPI 自动生成的接口层
│   │   ├── components/          # 公共组件（头部、页脚、状态徽章等）
│   │   ├── layouts/             # 布局组件
│   │   ├── pages/               # 页面
│   │   │   ├── admin/           # 用户管理、数据统计
│   │   │   ├── article/         # 创作、列表、详情
│   │   │   ├── user/            # 登录、注册
│   │   │   ├── HomePage.vue
│   │   │   └── VipPage.vue
│   │   ├── router/              # 路由配置
│   │   ├── stores/              # Pinia（登录用户）
│   │   ├── utils/               # sse / markdown / article / permission 工具
│   │   └── request.ts           # Axios 封装
│   ├── nginx.conf               # 生产环境 Nginx（含 SSE 反代配置）
│   └── Dockerfile
├── python-backend/              # FastAPI 后端
│   ├── app/
│   │   ├── agent/               # 多智能体
│   │   │   ├── agents/          # 标题/大纲/正文/配图分析/图文合成智能体
│   │   │   ├── parallel/        # 并行配图生成
│   │   │   ├── context/         # 流式输出处理器
│   │   │   └── orchestrator.py  # 编排器
│   │   ├── routers/             # 路由（user/article/payment/statistics/health）
│   │   ├── services/            # 业务服务（文章、智能体、图片策略、支付、COS 等）
│   │   ├── models/              # SQLAlchemy 模型 + 枚举
│   │   ├── schemas/             # Pydantic 请求/响应模型
│   │   ├── constants/           # 常量与 Prompt
│   │   ├── managers/            # SSE 连接管理
│   │   ├── utils/               # session / password
│   │   ├── config.py            # 配置（pydantic-settings）
│   │   ├── database.py          # 数据库连接
│   │   └── main.py              # 应用入口
│   ├── docker-compose.yml       # MySQL + Redis + 后端 + 前端 一键编排
│   └── pyproject.toml
└── sql/                         # 数据库初始化与增量脚本
    ├── create_table.sql         # 用户表、文章表、智能体日志表
    ├── update_quota.sql         # 用户配额字段
    ├── add_phase_fields.sql     # 文章阶段/标题方案/配图方式字段
    ├── add_article_style.sql    # 文章风格字段
    └── add_vip_payment.sql      # VIP 会员字段 + 支付记录表
```

**请求链路：** 浏览器 → Nginx（`/api/` 反向代理，SSE 关闭缓冲）→ FastAPI → MySQL / Redis / 外部 AI 与图片服务。

---

## 多智能体创作流程

创作任务按阶段推进，`article.phase` 字段记录当前所处阶段：

```
PENDING → TITLE_GENERATING → TITLE_SELECTING → OUTLINE_GENERATING
        → OUTLINE_EDITING → CONTENT_GENERATING → 完成
```

| 阶段 | 智能体 | 职责 | 是否人工确认 |
| --- | --- | --- | --- |
| 1 | `agent1_generate_titles` | 生成 3–5 个标题方案 | ✅ 用户选择标题 |
| 2 | `agent2_generate_outline` | 流式生成文章大纲 | ✅ 用户可编辑 / AI 改大纲 |
| 3 | `agent3_generate_content` | 流式生成正文（Markdown） | — |
| 3 | `agent4_analyze_image_requirements` | 分析正文配图需求与位置 | — |
| 3 | `agent5_generate_images` | 按选定方式**并行**生成/检索配图 | — |
| 3 | `agent6_merge_content` | 图文合成，输出完整 Markdown | — |

- 通过 `/api/article/progress/{taskId}`（SSE）推送 `AGENT*_COMPLETE`、`AGENT*_STREAMING`、`IMAGE_COMPLETE`、`MERGE_COMPLETE`、`ALL_COMPLETE`、`ERROR` 等事件。
- 每个智能体的 Prompt、输入输出、耗时、状态写入 `agent_log` 表，可在文章详情查看执行统计。
- 配图并行度由 `AGENT_IMAGE_MAX_CONCURRENCY` 控制，失败策略由 `AGENT_IMAGE_FAIL_FAST` 控制。

---

## 快速开始

### 方式一：Docker Compose 一键部署（推荐）

```bash
cd python-backend

# 1. 准备环境变量
cp .env.example .env
#    编辑 .env，至少填写 DASHSCOPE_API_KEY 与 PEXELS_API_KEY
#    （NANO_BANANA_API_KEY / 腾讯云 COS / Stripe 按需填写）

# 2. 构建并启动（MySQL + Redis + 后端 + 前端）
docker compose up -d --build

# 3. 查看状态与日志
docker compose ps
docker compose logs -f backend
```

启动后：

- 前端：http://localhost（默认 80，可用 `FRONTEND_PORT` 修改）
- 后端 API：http://localhost:8123 （可用 `BACKEND_PORT` 修改）
- 接口文档：http://localhost:8123/docs

MySQL 首次启动会自动执行 `sql/` 下的全部脚本完成建表与初始化数据。如需重置数据：`docker compose down -v`。

> 若拉取基础镜像缓慢，可在 `frontend/Dockerfile`、`python-backend/Dockerfile` 中改用注释里给出的国内镜像源。

### 方式二：本地开发

**前置依赖：** Python 3.12、Node.js 22+、MySQL 8、Redis 7、uv、Mermaid CLI（`npm i -g @mermaid-js/mermaid-cli`）

**后端**

```bash
cd python-backend
cp .env.example .env        # 填写数据库、Redis、各 API Key
uv sync                     # 安装依赖
uv run python -m app.main   # 默认监听 0.0.0.0:8567，代码热重载
```

**数据库**：先手动执行 `sql/` 下的脚本（按文件名顺序），或直接使用 Docker 启动 MySQL/Redis：

```bash
cd python-backend
docker compose up -d mysql redis
```

**前端**

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

> ⚠️ **注意端口对齐**：`frontend/vite.config.ts` 中 `/api` 代理默认指向 `http://localhost:8000`，而后端本地默认端口为 `8567`。请将代理 `target` 改为后端实际端口（或在 `frontend/.env.development` 中调整 `VITE_API_BASE_URL`）。

---

## 环境变量

后端配置见 [python-backend/.env.example](python-backend/.env.example)，主要分组：

| 分组 | 关键变量 | 说明 |
| --- | --- | --- |
| 服务器 | `SERVER_PORT` / `SERVER_HOST` | 本地默认 `8567`，容器内固定 `8123` |
| 数据库 | `DB_HOST` `DB_PORT` `DB_NAME` `DB_USER` `DB_PASSWORD` | MySQL 连接 |
| Redis | `REDIS_HOST` `REDIS_PORT` `REDIS_DB` `REDIS_PASSWORD` | 会话存储 |
| 会话 | `SESSION_SECRET_KEY` `SESSION_MAX_AGE` | 默认 30 天 |
| 密码 | `PASSWORD_SALT` | MD5 加盐 |
| AI 文本 | `DASHSCOPE_API_KEY` `DASHSCOPE_MODEL` | 阿里云 DashScope（Qwen） |
| AI 生图 | `NANO_BANANA_API_KEY` `NANO_BANANA_MODEL` 等 | Gemini 生图 |
| 图库 | `PEXELS_API_KEY` | Pexels 配图检索 |
| 对象存储 | `TENCENT_COS_SECRET_ID/KEY` `TENCENT_COS_REGION` `TENCENT_COS_BUCKET` `TENCENT_COS_DOMAIN` | 腾讯云 COS |
| 示意图 | `MERMAID_*` `ICONIFY_*` `EMOJI_PACK_*` `SVG_DIAGRAM_*` | 各类配图服务 |
| 并行 | `AGENT_IMAGE_MAX_CONCURRENCY` `AGENT_IMAGE_FAIL_FAST` | 配图并发与失败策略 |
| 支付 | `STRIPE_API_KEY` `STRIPE_WEBHOOK_SECRET` `STRIPE_SUCCESS_URL` `STRIPE_CANCEL_URL` | Stripe 会员支付 |

前端配置见 `frontend/.env.development` / `.env.production`：

- `VITE_API_BASE_URL`：接口基础路径（默认 `/api`，走 Nginx / Vite 代理）
- `VITE_DEPLOY_DOMAIN`：部署域名

---

## API 接口概览

所有接口以 `/api` 为前缀，统一返回 `{ code, data, message }` 结构。完整文档见运行后的 `/docs`。

### 用户 `/api/user`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/register` | 用户注册 |
| POST | `/login` | 登录（写入 `SESSION` Cookie） |
| POST | `/logout` | 退出登录 |
| GET | `/get/login` | 获取当前登录用户 |
| GET | `/get` | 获取用户信息 |
| POST | `/list/page` | 分页查询用户（管理员） |
| POST | `/add` `/update` `/delete` | 用户增改删（管理员） |

### 文章 `/api/article`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/create` | 创建创作任务（校验并消耗配额） |
| GET | `/progress/{taskId}` | **SSE** 实时进度推送 |
| GET | `/{taskId}` | 文章详情 |
| POST | `/list` | 分页查询文章列表 |
| POST | `/delete` | 删除文章 |
| POST | `/confirm-title` | 确认所选标题方案 |
| POST | `/confirm-outline` | 确认大纲 |
| POST | `/ai-modify-outline` | AI 辅助修改大纲 |
| GET | `/execution-logs/{taskId}` | 智能体执行统计 |

### 支付 `/api/payment` 与回调 `/api/webhook`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/payment/create-vip-session` | 创建 VIP 支付会话，返回 Stripe Checkout URL |
| POST | `/payment/refund` | 申请退款（仅 VIP） |
| GET | `/payment/records` | 当前用户支付记录 |
| POST | `/webhook/stripe` | Stripe 支付回调 |

### 其他

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/statistics/overview` | 系统统计（仅管理员） |

---

## 数据库设计

库名：`ai_passage_creator`（`utf8mb4` / `utf8mb4_unicode_ci`）

| 表 | 说明 |
| --- | --- |
| `user` | 用户（账号、密码 MD5 加盐、角色、**配额 quota**、**会员时间 vipTime**） |
| `article` | 文章任务（选题、风格、标题方案、大纲、正文、配图、状态 `status`、阶段 `phase`） |
| `agent_log` | 智能体执行日志（Prompt、输入输出、耗时、状态） |
| `payment_record` | Stripe 支付记录（会话 ID、金额、状态、退款信息） |

**文章关键字段**

- `status`：`PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`
- `phase`：`PENDING` → `TITLE_GENERATING` → `TITLE_SELECTING` → `OUTLINE_GENERATING` → `OUTLINE_EDITING` → `CONTENT_GENERATING`
- `outline` / `images` / `titleOptions` / `enabledImageMethods` 为 JSON 字段
- `content`（纯正文 Markdown）与 `fullContent`（含配图的完整 Markdown）

---

## 默认账号

初始化脚本会插入以下测试账号（密码均为 `12345678`，MD5 + 盐值 `fenghui` 加密）：

| 账号 | 角色 | 说明 |
| --- | --- | --- |
| `admin` | admin | 管理员 |
| `user` | user | 普通用户 |
| `test` | user | 测试账号 |

> ⚠️ 生产环境请务必修改默认密码、`PASSWORD_SALT`、`SESSION_SECRET_KEY` 及数据库/Redis 密码。

---

## 开发命令

### 前端（`frontend/`）

```bash
npm run dev          # 启动开发服务器（5173）
npm run build        # 类型检查 + 生产构建
npm run type-check   # 仅类型检查
npm run lint         # ESLint 自动修复
npm run format       # Prettier 格式化
npm run openapi2ts   # 依据后端 OpenAPI 生成接口代码
```

### 后端（`python-backend/`）

```bash
uv sync                        # 安装依赖
uv run python -m app.main      # 本地开发（热重载）
docker compose up -d --build   # 容器化部署
docker compose logs -f backend # 查看后端日志
```

---

## License

本项目仅供学习与交流使用。
