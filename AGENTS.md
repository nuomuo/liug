# 项目准则（强制遵守）

## 架构说明（前后端分离 + 业务核心下沉）

- **业务核心 `core/`（双端共享，不含认证与桌面逻辑）**：`db.py`（每用户 SQLite 数据层：业务表含 `guid`/`updated_at` 列，触发器自动补全与触碰、硬删除写 `_sync_tombstones` 墓碑，老库打开时自动迁移）、`routes.py`（/api/* 业务路由，鉴权通过 `get_user_id` 依赖注入；含 `POST /api/sync` 同步端点）、`sync.py`（同步核心：快照构建 / LWW 合并 / 幂等应用，guid 空间 + FK 重映射 + 拓扑插入）、`app_factory.py`（FastAPI 组装工厂：业务路由 + 认证路由 + 额外路由 + SPA 静态托管）、`auth.py`（scrypt/HMAC 纯函数）、`errors.py`、`holidays.py`、`import_csv.py`。用户数据目录由 `LIUG_USERS_DIR` 指定（惰性解析），静态资源目录由 `LIUG_DIST_DIR` 指定。
- **远程后端 `server/`（唯一保留用户管理的地方）**：入口 `server/app.py`，组装 core + 账户体系（`users.py` 多用户主库 + `routes_auth.py` 认证路由）+ 管理端路由（`routes_admin.py`，/admin 前缀 API 与管理页托管），托管 `client/dist` 静态站点。依赖见 `server/requirements.txt`。多用户版：`data/users.db` 为用户主库（账户/密码/角色），每个用户的数据存放在 `data/users/<用户唯一ID>.db` 独立 SQLite 文件中。密码哈希（scrypt，`scrypt$salt$hash`）与会话（HMAC 签名 Cookie + `sessions_since`）口径与旧 Node 版完全互通；主应用会话密钥复用 `data/users.db.secret`。
- 前端为 Vue3 + Vite（`client/`），构建产物在 `client/dist/`；前端改动后需 `npm run build --prefix client`。
- **桌面客户端 `desktop/`（不含用户管理，账户体系不进 exe）**：`main.py` 为整应用启动器（单进程 = 系统托盘 pystray + 主界面窗口 + 可选四象限小组件 + 内嵌 uvicorn，**粘性动态端口**：上次端口 → 4300 → 随机，socket 预绑定消除竞态，端口记录在 `<data>/service-port.json` 供小组件发现；Windows 互斥体单实例防双开；主窗口点 × 隐藏到托盘，托盘「退出」才结束；应用显示名统一为「流光 LIUG」，对外可见的名称必须使用「流光 LIUG」，不得使用其他名称）。认证用 `local_auth.py`：
  - **单机模式**：`POST /api/auth/local` 免密签发固定 `LOCAL_UID='local'` 会话（TTL 10 年，密钥 `<data>/local.secret`，登出为进程内内存吊销）；业务数据在 `<LIUG_USERS_DIR>/local.db` 单文件；`/api/auth/me` 返回 user 带 `mode='standalone'` 供前端识别。
  - **云端账号（离线可用 + 双向同步）**：登录页「登录账号（云端同步）」配置服务器地址（`<data>/config.json` 的 remoteUrl，由 `GET/PUT /api/desktop/config` 读写）与账号密码，`POST /api/auth/remote` 由本地服务代理登录远程服务器（WebView 不整页跳转）；远程令牌存 `<data>/remote-session.json`，本地签发 uid=远程用户 ID 的 30 天会话；登录成功即以不播种方式建空镜像库 `<LIUG_USERS_DIR>/<远程ID>.db`（与单机 `local.db` 完全隔离），断网照常使用，`me` 返回 `mode='cloud'`。
  - **同步引擎 `desktop/sync.py`**（随主服务启动，小组件内嵌模式不启动防双引擎）：本地写操作后前端 fire-and-forget `POST /api/sync/kick`（防抖 3 秒）+ 定时 300 秒 + 设置面板手动「立即同步」`POST /api/sync/run`；协议为 `POST /api/sync` 全量快照 LWW 合并（详见 `core/sync.py`）；状态持久化 `<data>/sync-state.json`，前端 30s 轮询 `GET /api/sync/status`，`lastChangedAt` 前进时自动刷新数据；远程令牌过期报 `expired` 引导重登、断网报 `offline` 恢复后自动补同步，均不影响离线使用。
  `desktop_widget.py` 为独立小组件启动器（按 `service-port.json` 发现主服务、兜底 4300，否则内嵌 uvicorn 独立运行，可用 `LIUG_WIDGET_SERVER_URL` 指定服务地址、`LIUG_WIDGET_FORCE_EMBEDDED=1` 强制内嵌）。依赖见 `desktop/requirements.txt`。
- 打包：`python -m PyInstaller --noconfirm liug.spec`（产物 `dist/liug.exe`，单文件无控制台；入口 `desktop/main.py`，`excludes` 显式排除用户管理模块；冻结模式数据目录为用户家目录 `~/.liug`（`desktop/app_paths.py`：首次启动自动从 exe 同级旧 `data/` 整体迁移，目录隐藏+系统属性并用 ACL 拒绝删除防误删）、静态资源用 `LIUG_DIST_DIR` 指向 _MEIPASS 内副本，运行日志 `~/.liug/desktop.log`、错误日志 `~/.liug/desktop.err.log`）。注意 `console=False` 下 `sys.stdout/stderr` 为 None 会导致原生层静默崩溃，启动器已内置重定向，勿移除。
- 旧 Node 后端与旧 Flask 管理程序均已退役、不再维护（备份目录已从仓库移除）。

## 数据库隔离（最高优先级）

以下均为**正式数据**，严禁在任何测试、调试、验证过程中写入、修改或删除：

- `data/schedule.db` —— 旧单用户版的真实数据（已被只读迁移为 admin 账户的独立库，原文件保留不动）。
- `data/users.db` —— 正式用户主库（账户信息）。
- `data/users/` —— 正式用户数据目录（每个用户一个 `<uuid>.db`）。

测试必须使用独立的测试用户主库和测试用户数据目录，通过环境变量指定：

```bash
# 测试服务器（生产为 4300，测试一律用 4301）
LIUG_USERS_DB_PATH=data/users.test.db LIUG_USERS_DIR=data/users-test PORT=4301 python server/app.py

# 测试导入（导入 CLI 仍使用 LIUG_DB_PATH 指定目标库文件）
LIUG_DB_PATH=data/schedule.test.db python core/import_csv.py <csv路径>
```

- 测试服务器首次启动会自动在测试用户主库中创建默认管理员 `admin / admin123`。
- 浏览器自动化测试的目标地址一律为 `http://localhost:4301`（测试库），不得对 `http://localhost:4300`（正式库）执行任何写操作。
- 修改正式数据库的唯一合法途径：用户本人在页面上操作，或明确授权的数据维护。

## 前端通用组件复用（强制）

可复用的交互模块必须沉淀为独立通用组件，放在 `client/src/components/` 下，禁止在页面组件内重复实现：

- **已有通用组件（优先复用，勿重复造轮子）**：
  - `MarkdownEditor.vue` —— Markdown 编辑器（左右分栏实时预览、可拖动分割条、右键格式化菜单）。用法：`<MarkdownEditor v-model="内容" placeholder="..." />`。
  - `DatePicker.vue` —— 玻璃风格日期选择器（农历/节假日、清除日期，替代原生 date picker）。用法：`<DatePicker v-model="日期YYYY-MM-DD" title="..." />`；组件暴露 `close()` 方法。
  - `GlassSelect.vue` —— 玻璃风格下拉选择器（替代原生 select，Teleport 弹层、选中项对勾、可选项色点）。用法：`<GlassSelect v-model="值" :options="[{ value, label, dot? }]" />`；组件暴露 `close()` 方法。
- **组件化要求**：
  - 新增功能若包含可复用的 UI/交互（编辑器、选择器、弹层、菜单等），必须先抽成独立组件再接入页面，而不是把逻辑写死在某个页面组件里。
  - 通用组件必须自包含：不依赖特定页面的数据/store 字段，通过 `props` / `emits`（`v-model`）通信，样式（含玻璃风格变量）随组件走。
  - 弹层类组件统一用 `<Teleport to="body">` + `store.js` 的 `placeDropdown()` 定位，保证跨页面行为一致。

## 用户管理

用户管理通过独立的「管理端」模块提供，仅远程后端（`server/`）具备，桌面端 exe 不包含：

- **后端 `server/routes_admin.py`**：`/admin` 前缀 API（login/logout/me/users 增删改），复用主应用会话体系（同一 Cookie `liug_session`、`data/users.db.secret`、`sessions_since`/`revoked_sessions` 口径）；同时把 `admin_client/dist` 托管在 `/admin/` 路径（API 路由先注册，静态 catch-all 后注册；dist 可由 `LIUG_ADMIN_DIST_DIR` 覆盖，未构建时返回 404 提示）。
- **前端 `admin_client/`**：独立 Vue3 + Vite 工程（与 `client/` 完全隔离，不被 PyInstaller 打包，`liug.spec` 的 `excludes` 已排除 `routes_admin`）。构建：`npm run build --prefix admin_client`（生产 `base: '/admin/'`，开发 5181 端口 + proxy）；访问地址 `http://<host>:4300/admin/`。
- **双重防线**：① IP 白名单 `LIUG_ADMIN_ALLOWED_IPS`（逗号分隔，支持 IP/CIDR/`*`；**未配置或为空时不做限制**，配置后名单外访问任何 /admin 资源——含页面与登录——一律 403，不影响主应用；可经根目录 config.yaml 的 env 段配置，由 manage.py 注入）；② 会话校验 + `role='admin'`（非管理员即使已登录也 403）。管理端有独立登录页，登录时即校验管理员角色。
- **保护规则**：不能对自己执行禁用/降级/删除；系统至少保留一个可用管理员（`admin_count()`）；重置密码后吊销目标用户全部会话；删除用户保留其 `data/users/<uid>.db` 数据文件。
- 主应用前端（`client/`）与管理端互不包含：管理功能只走 /admin 前缀接口。
