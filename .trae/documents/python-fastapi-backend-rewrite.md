# Python FastAPI 后端完全重写计划

## Context

用户要求：用 Python **完全重写** `server/` 目录下所有后端逻辑（Node Express → Python），前端保持 Vue/Vite（Node 工具链），实现前后端分离。用户已拍板：

1. 框架：**FastAPI**
2. 旧 Node `server/` 验证通过后重命名为 `server-node-backup/` 留底
3. **system-admin（Flask 用户管理）合并进新主后端**：一个进程同时提供 `/api/*`、`/system/*` 和两个静态前端
4. Python 后端接管 4300 端口（测试 4301），Vite 代理与前端 api.js **零改动**

## 关键事实（已核查）

| 事实 | 结论 |
|---|---|
| Node 会话密钥文件 | `data/users.db.secret`（`USERS_DB_PATH + '.secret'`）。**Python 沿用同名文件 → 现有已登录用户 cookie 迁移后免登录** |
| system-admin 前端 fetch | 全部绝对路径 `/system/...`，合并后无需改 |
| system-admin 静态引用 | `index.html` L7 `/style.css`、L103 `/app.js` 为**根绝对路径** → 必须改为相对路径（2 行），否则挂子路径 404 |
| Node 静态语义 | `express.static(dist)` + catch-all 正则 `/^(?!\/api\/).*/`；未知 `/api/*` → 404，其余 GET → index.html。Python 版 catch-all 需同时排除 `/api/` 和 `/system/` |
| node:sqlite 差异 | 外键默认开启 → Python 需 `PRAGMA foreign_keys=ON`；BigInt 问题 Python 无 |
| 本机 Python | 3.13（miniconda），pip 不在 PATH → 统一用 `python -m pip` |
| system-admin 未 git 提交 | 切换生产前先 commit 当前工作区 |

## 新目录结构（开发期 `server-py/`，验证后改名 `server/`）

```
server-py/
├── app.py            # 入口：FastAPI 实例、CORS、路由挂载、静态托管 + SPA fallback、ApiError 处理器、uvicorn.run
├── db.py             # 每用户独立 SQLite：SCHEMA、连接缓存 dict[uid]->(conn,RLock)、WAL、默认数据 seed
├── users.py          # 用户主库（单连接+全局 RLock）、scrypt、HMAC 会话、吊销机制、bootstrapUsers + VACUUM INTO 迁移
├── holidays.py       # 节假日三源回退（httpx.AsyncClient）+ 内存缓存 + 并发去重
├── import_csv.py     # CSV 导入函数 + argparse CLI（DIDA_DB_PATH）
├── routes_api.py     # /api/* 全部业务路由（同步 def 端点，跑线程池）
├── routes_system.py  # /system/* 用户管理路由 + require_admin 依赖
├── web_admin/        # 拷贝自 system-admin/web/（index.html 改 2 处相对路径），挂载在 /system-admin/
└── requirements.txt  # fastapi、uvicorn、httpx、regex
```

迁移映射：`db.py`←db.js；`users.py`←users.js（scrypt/会话口径直接复用已验证的 system-admin/app.py L116-241）；`holidays.py`←holidays.js；`import_csv.py`←import-csv.js；`routes_api.py`←index.js 全部路由；`routes_system.py`←system-admin/app.py 路由。不设 Pydantic 模型层（请求体用 `dict = Body(default={})` + 字段白名单，对齐 Express 风格）。

## 关键实现口径

- **SQLite 线程安全**：用户主库单连接 `check_same_thread=False` + 全局 RLock；每用户库 `dict[uid]->(conn,RLock)` 缓存（对应 Node openConnections Map）。统一 `isolation_level=None`（autocommit）+ WAL + `foreign_keys=ON` + `row_factory=sqlite3.Row`。WAL+锁串行与 Node 单线程语义等价，够用。
- **scrypt**：`hashlib.scrypt(pwd.encode(), salt=salt.encode('utf-8'), n=16384, r=8, p=1, dklen=64, maxmem=64MB)`，salt 为 hex 字符串直接作 bytes，格式 `scrypt$salt$hash`，比对 `hmac.compare_digest`。
- **会话**：token=`base64url(json).base64url(hmac)`；`sessions_since > iat` **严格大于**（change-password 当前会话续期的关键，不能写 `>=`）；密钥文件读入后 `.strip()`。
- **错误响应**：自定义 `ApiError` + exception_handler 统一返回 `{"error":"中文消息"}`（FastAPI 默认 `{"detail":...}` 形状不符，前端会读 `err.data.error`）。
- **FastAPI 构造**：`redirect_slashes=False`、`docs_url=None, redoc_url=None, openapi_url=None`（对齐 Express 无 /docs）。
- **静态托管**（Starlette 按注册顺序）：① /api 与 /system 路由 → ② `GET /system-admin` 307 → ③ `mount('/system-admin', StaticFiles(html=True))` → ④ catch-all `/{full_path:path}`：`api/`、`system/` 前缀返回 404；dist 内存在文件则 FileResponse（resolve + `is_relative_to` 防目录穿越），否则返回 index.html。
- **holidays**：三源回退顺序与 8s 超时、TTL（有数据 7 天/空 1 天）、inflight asyncio.Task 去重，1:1 复刻；输出 `{year, source, days}`。
- **import_csv**：标准库 `csv.reader`（utf-8-sig 去 BOM）替代手写解析；**`leadingEmoji` 的 `\p{Extended_Punctographic}` 正则 Python re 不支持 → 必须用 `regex` 包**（新依赖的硬理由）；两遍法处理父子任务；`BEGIN/COMMIT/ROLLBACK` 显式事务；CLI 打开目标库不 seed 默认数据。
- **时间口径**：`beijingNowIso()` 用 `strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]` 固定**毫秒 3 位**（Node toISOString 恒 3 位）。
- **Windows 删除用户**：DELETE 前先 `close_user_db(uid)` 释放句柄，再删 `.db`/`-wal`/`-shm`（合并进程后新增强制步骤）。
- **默认值口径**（对齐 Node 的 `??`/`=== false` 语义）：`isAllDay === false` 才为 0（Python `0 if v is False else 1`）、`sortOrder ?? MIN(sort_order)-1`、projects/countdowns `maxOrder+1` 不过滤 is_deleted、projects PUT 未命中返回 `null`+200（复刻 Node 无存在性检查）、tasks/countdowns PUT 未命中 404。
- **鉴权白名单**：`/api/auth/login`、`/api/holidays` 公开；其余 `/api/*` 需有效会话（401 未登录或会话已过期 / 403 账户已被禁用 / 401 会话已失效，请重新登录）。
- **启动**：`python server-py/app.py` 内嵌 `uvicorn.run(app, host='0.0.0.0', port=PORT)`，`PORT = int(os.environ.get('PORT') or '4300')`；启动前先 bootstrapUsers。

## 接口清单（目标：与 Node 版零行为差异）

- **/api/***：auth 4 个（login/logout/me/change-password）、holidays、bootstrap、tasks CRUD、projects CRUD、search、countdowns CRUD、import、reset —— 逐个对照 `server/index.js` 复刻（含 cookie 属性 Path=/; HttpOnly; SameSite=Lax; Max-Age=604800、search 去 `%`/`_`、任务软删含直接子任务、项目 id=1 删除保护、reset 只清 tasks/projects/folders 并重新 seed）。
- **/system/***：auth 3 个（仅 admin 可登录）+ users CRUD（唯一管理员保护、不能删自己、改密吊销全部会话、建用户立即建独立库）—— 逐行移植 `system-admin/app.py`。
- **静态**：`/system-admin/*` 管理页；其余 GET → SPA。

已知可接受差异：非法 JSON 请求体 Node 400 vs FastAPI 422（客户端恒发合法 JSON，不触发）；未知路径 404 文案；Cookie 属性大小写。

## 实施步骤

### 阶段 1：开发
1. `git commit` 当前工作区（可回滚点）
2. 创建 `server-py/` 全部文件 + `web_admin/`（拷贝 3 文件，index.html L7/L103 去根斜杠）
3. `python -m pip install -r server-py/requirements.txt`
4. 自测：Python hash/verify 与 users.test.db 的 admin123 哈希互验；Node 签发 token 用 Python 验签

### 阶段 2：4301 测试库冒烟（严守 AGENTS.md 隔离）
```
$env:DIDA_USERS_DB_PATH='data/users.test.db'; $env:DIDA_USERS_DIR='data/users-test'; $env:PORT='4301'; python server-py/app.py
```
- auth 4 件套（改密后旧 token 401、当前会话续期）
- bootstrap → task 建改查删（默认值/tags/毫秒时间）→ search → projects（含 id=1 保护）→ countdowns → reset（默认数据回来）
- import：先 CLI 跑 `DIDA_DB_PATH=data/schedule.test.db python server-py/import_csv.py <测试csv>`，再走 API
- holidays：2007-2100 边界 + 502 容错
- /system/* 7 端点：建用户 → 验证 `data/users-test/<uuid>.db` 已建 → 改密/禁用 → 删除 → 验证 db/-wal/-shm 一并删除
- 浏览器端到端 http://localhost:4301：Vue 全功能、/system-admin/ 管理页、SPA 深链刷新
- 可选对拍：Node 测试实例（4305）与 Python（4301）同请求比对 JSON

### 阶段 3：切换生产
1. 停 Node 4300
2. 重命名：`server/` → `server-node-backup/`；`server-py/` → `server/`
3. `system-admin/` 退役（Flask 版代码功能已延续进 `server/routes_system.py` + `server/web_admin/`）
4. 根 `package.json` 脚本更新：
   - `"install:all": "npm install --prefix client"`
   - `"server": "python server/app.py"`、`"start": "python server/app.py"`
   - `"import": "python server/import_csv.py"`
5. AGENTS.md 更新：架构表述改 Python FastAPI；测试命令改 `python server/app.py` / `python server/import_csv.py`；「系统管理独立程序」整节改为「已合并进主后端」（**4302/4303 端口废弃**，管理页地址 `http://localhost:4300/system-admin/`，独立 cookie `dida_system_session` + 密钥 `users.db.system-secret`）
6. 启动 `python server/app.py`（4300）回归：
   - **核心验证点：迁移前的旧浏览器 cookie 直接访问 4300 免登录**（密钥文件复用成功）
   - 生产数据只读核验：bootstrap 各计数与迁移前一致
   - /system-admin/ 管理页正常
7. git 提交完整 cutover

## 风险清单（要点）

1. `\p{Extended_Pictographic}` 正则 → 用 `regex` 包（否则导入 emoji 全丢）
2. 错误 JSON 形状 → ApiError 处理器（否则前端读不到 error 字段）
3. 密钥文件复用 → 文件名严格 `<USERS_DB_PATH>.secret`，内容 `.strip()`
4. Windows 删用户文件锁 → 先 close_user_db 再删文件
5. `sessions_since > iat` 严格大于 → 改密续期依赖此
6. 毫秒精度 created_at → `strftime(...%f)[:-3]`
7. `VACUUM INTO` → 参数绑定 + `file:...?mode=ro` 只读连接
8. FastAPI redirect_slashes 307 → 关闭对齐 Express 404
9. catch-all 防目录穿越 → resolve + is_relative_to

## 验证方式

- 阶段 2 全部冒烟项通过 + 浏览器端到端（4301 测试库）
- 阶段 3 切换后：旧 cookie 免登录、生产数据只读核验、管理页可用
- 全程不触碰 data/users.db、data/users/、data/schedule.db（只读 VACUUM INTO 迁移除外，且仅在首次启动触发）
