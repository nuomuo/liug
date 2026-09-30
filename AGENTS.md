# 项目准则（强制遵守）

## 架构说明（前后端分离）

- 后端为 **Python FastAPI**（`server/`，入口 `server/app.py`），提供 `/api/*` JSON API，并托管 `client/dist`（主应用前端）静态站点。依赖见 `server/requirements.txt`。
- 前端为 Vue3 + Vite（`client/`），构建产物在 `client/dist/`；前端改动后需 `npm run build --prefix client`。
- 桌面四象限小组件：`server/desktop_widget.py`（pywebview 无边框透明置顶窗口，加载主应用 `/quadrant` 页面，组件为 `client/src/components/QuadrantWidget.vue`）；优先复用已运行的 4300 主服务，否则内嵌 uvicorn 独立运行，可用 `DIDA_WIDGET_SERVER_URL` 指定服务地址、`DIDA_WIDGET_FORCE_EMBEDDED=1` 强制内嵌。打包为单个 exe：`python -m PyInstaller --noconfirm quadrant.spec`（产物 `dist/quadrant.exe`；冻结模式下数据目录为 exe 同级 `data/`，静态资源用 `DIDA_DIST_DIR` 指向 _MEIPASS 内副本）。
- 桌面版整应用：`server/desktop_app.py`（单进程 = 系统托盘 pystray + 主界面窗口 + 可选四象限小组件 + 内嵌 uvicorn，优先 4300 被占则随机端口；Windows 互斥体单实例防双开；主窗口点 × 隐藏到托盘，托盘「退出」才结束，右键菜单可开关小组件；应用显示名为「流光 LIUG」，严禁再以「滴答清单/dida」命名对外可见的名称）。打包：`python -m PyInstaller --noconfirm liug.spec`（产物 `dist/liug.exe`，单文件无控制台；依赖 pystray/pywebview/pillow；冻结模式数据目录为 exe 同级 `data/`，运行日志 `data/desktop.log`、错误日志 `data/desktop.err.log`）。注意 `console=False` 下 `sys.stdout/stderr` 为 None 会导致原生层静默崩溃，启动器已内置重定向，勿移除。
- 多用户版：`data/users.db` 为用户主库（账户/密码/角色），每个用户的数据存放在 `data/users/<用户唯一ID>.db` 独立 SQLite 文件中。
- 密码哈希（scrypt，`scrypt$salt$hash`）与会话（HMAC 签名 Cookie + `sessions_since`）口径与旧 Node 版完全互通；主应用会话密钥复用 `data/users.db.secret`。
- 旧 Node 后端备份在 `server-node-backup/`，旧 Flask 管理程序备份在 `system-admin-flask-backup/`，均已退役、不再维护。

## 数据库隔离（最高优先级）

以下均为**正式数据**，严禁在任何测试、调试、验证过程中写入、修改或删除：

- `data/schedule.db` —— 旧单用户版的真实数据（已被只读迁移为 admin 账户的独立库，原文件保留不动）。
- `data/users.db` —— 正式用户主库（账户信息）。
- `data/users/` —— 正式用户数据目录（每个用户一个 `<uuid>.db`）。

测试必须使用独立的测试用户主库和测试用户数据目录，通过环境变量指定：

```bash
# 测试服务器（生产为 4300，测试一律用 4301）
DIDA_USERS_DB_PATH=data/users.test.db DIDA_USERS_DIR=data/users-test PORT=4301 python server/app.py

# 测试导入（导入 CLI 仍使用 DIDA_DB_PATH 指定目标库文件）
DIDA_DB_PATH=data/schedule.test.db python server/import_csv.py <csv路径>
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

用户管理模块（独立前端 `admin-client/` 与 `/system/*` JSON API、`/system-admin/` 管理页）已整体移除，项目不再包含任何用户管理代码：

- Vue client（`client/`）不包含任何用户管理代码；`server/` 下无 `routes_system.py`。
- 账户体系仍保留：登录态使用 Cookie `dida_session` 与密钥 `data/users.db.secret`（多用户数据隔离见上文）。
- 若需增删用户/重置密码，需直接维护 `data/users.db`（须用户明确授权）。
