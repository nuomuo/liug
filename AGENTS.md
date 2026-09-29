# 项目准则（强制遵守）

## 多用户架构说明

系统为多用户版：`data/users.db` 为用户主库（账户/密码/角色），每个用户的数据存放在 `data/users/<用户唯一ID>.db` 独立 SQLite 文件中。

## 数据库隔离（最高优先级）

以下均为**正式数据**，严禁在任何测试、调试、验证过程中写入、修改或删除：

- `data/schedule.db` —— 旧单用户版的真实数据（已被只读迁移为 admin 账户的独立库，原文件保留不动）。
- `data/users.db` —— 正式用户主库（账户信息）。
- `data/users/` —— 正式用户数据目录（每个用户一个 `<uuid>.db`）。

测试必须使用独立的测试用户主库和测试用户数据目录，通过环境变量指定：

```bash
# 测试服务器（生产为 4300，测试一律用 4301）
DIDA_USERS_DB_PATH=data/users.test.db DIDA_USERS_DIR=data/users-test PORT=4301 node server/index.js

# 测试导入（导入 CLI 仍使用 DIDA_DB_PATH 指定目标库文件）
DIDA_DB_PATH=data/schedule.test.db node server/import-csv.js <csv路径>
```

- 测试服务器首次启动会自动在测试用户主库中创建默认管理员 `admin / admin123`。
- 浏览器自动化测试的目标地址一律为 `http://localhost:4301`（测试库），不得对 `http://localhost:4300`（正式库）执行任何写操作。
- 修改正式数据库的唯一合法途径：用户本人在页面上操作，或明确授权的数据维护。

## 前端通用组件复用（强制）

可复用的交互模块必须沉淀为独立通用组件，放在 `client/src/components/` 下，禁止在页面组件内重复实现：

- **已有通用组件（优先复用，勿重复造轮子）**：
  - `MarkdownEditor.vue` —— Markdown 编辑器（左右分栏实时预览、可拖动分割条、右键格式化菜单）。用法：`<MarkdownEditor v-model="内容" placeholder="..." />`。
  - `DatePicker.vue` —— 玻璃风格日期选择器（农历/节假日、清除日期，替代原生 date picker）。用法：`<DatePicker v-model="日期YYYY-MM-DD" title="..." />`；组件暴露 `close()` 方法。
- **组件化要求**：
  - 新增功能若包含可复用的 UI/交互（编辑器、选择器、弹层、菜单等），必须先抽成独立组件再接入页面，而不是把逻辑写死在某个页面组件里。
  - 通用组件必须自包含：不依赖特定页面的数据/store 字段，通过 `props` / `emits`（`v-model`）通信，样式（含玻璃风格变量）随组件走。
  - 弹层类组件统一用 `<Teleport to="body">` + `store.js` 的 `placeDropdown()` 定位，保证跨页面行为一致。
