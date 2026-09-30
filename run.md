# 启动指南

前后端分离架构：后端为 Python FastAPI（`server/`），前端为 Vue3 + Vite（`client/`）。
npm 相关内容已全部收进 `client/package.json`，项目根目录不再有 package.json。

## 一、首次准备（只需一次）

```powershell
# 1. 安装后端依赖（fastapi / uvicorn / httpx / regex）
pip install -r server/requirements.txt

# 2. 安装前端依赖（主应用）
npm install --prefix client
```

## 二、启动后端（必须）

后端同时提供 API 并托管前端构建产物，**日常使用只需启动它**：

```powershell
# 在项目根目录执行
python server/app.py
# 或者：
npm run server --prefix client
```

- 主应用：[http://localhost:4300](http://localhost:4300)

## 三、启动前端

### 日常使用（无需启动）

后端直接托管 `client/dist/` 构建产物，启动后端后访问 [http://localhost:4300](http://localhost:4300) 即可。

### 开发模式（改前端代码时用，热更新）

```powershell
npm run dev --prefix client
```

- 开发服务器：[http://localhost:5180](http://localhost:5180)（`/api` 自动代理到 4300，**需先启动后端**）

### 改完前端代码后发布

```powershell
npm run build --prefix client
```

构建产物输出到 `client/dist/`，刷新 [http://localhost:4300](http://localhost:4300) 即生效。

## 四、桌面四象限小组件（可选）

pywebview 无边框透明置顶窗口，加载主应用的 `/quadrant` 页面（需先执行过 `npm run build --prefix client`）：

```powershell
python server/desktop_widget.py
```

- 主服务（4300）已在运行时直接复用它；未运行则自动内嵌启动一份独立服务，可脱离主程序单独使用
- 首次使用需在小组件窗口内登录一次（WebView2 会记住登录态）
- 按住标题栏空白处拖动窗口；标题栏右侧有刷新 / 最小化 / 关闭按钮
- 依赖 `pywebview`（已列入 requirements.txt，注释行，纯服务端部署可不安）
- 浏览器调试地址：主服务启动后访问 [http://localhost:4300/quadrant](http://localhost:4300/quadrant)

### 打包成单个 quadrant.exe

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm quadrant.spec
# 产物：dist/quadrant.exe（约 38 MB，单文件、无控制台窗口，双击即用）
```

- 已打包 `client/dist` 静态资源；主服务运行时复用 4300，否则内嵌服务独立运行
- 独立运行时数据放在 exe 同级 `data/` 目录（与源码运行的 `data/` 互不干扰；也可用 `DIDA_USERS_DB_PATH`/`DIDA_USERS_DIR` 覆盖）
- 注意：spec 中打包了 conda `Library/bin` 下的 OpenSSL/libffi/sqlite3 等运行时 DLL，换 Python 环境构建时需确认该目录仍存在

## 五、桌面版整应用（liug.exe）

`server/desktop_app.py`：一个进程搞定全部——系统托盘常驻（pystray）+ 主界面窗口 + 可选桌面小组件 + 内嵌 uvicorn 服务：

```powershell
# 源码运行（开发模式）
python server/desktop_app.py

# 测试库运行
$env:DIDA_USERS_DB_PATH='data/users.test.db'; $env:DIDA_USERS_DIR='data/users-test'; python server/desktop_app.py

# 打包成单个 exe（需先 build 过 client）
pip install pyinstaller pystray pillow
python -m PyInstaller --noconfirm liug.spec
# 产物：dist/liug.exe（约 42 MB，单文件、无控制台窗口，双击即用）
```

- **托盘**：双击图标或菜单「打开流光 LIUG」显示主窗口；右键菜单可勾选开关「显示桌面小组件（四象限）」；「退出」彻底结束进程
- **主窗口点 ×**：仅隐藏到托盘继续驻留（托盘应用惯例），从托盘「退出」才真正退出
- **单实例**：Windows 互斥体锁，重复双击弹提示「已在运行」
- **端口**：内嵌服务优先 4300，被其他程序占用时自动换随机端口（对用户透明）
- **数据与日志**：数据目录在 exe 同级 `data/`；运行日志 `data/desktop.log`、错误日志 `data/desktop.err.log`（排查 exe 问题先看这两个文件）
- 首次启动自动创建默认管理员 `admin / admin123`
- **登录持久化**：WebView2 以非隐私模式运行（`private_mode=False`），cookies/localStorage 落在 exe 同级 `data/webview/`，重启 exe 免登录（除非手动退出登录）；服务端会话有效期 7 天
- **桌面小组件**（无边框透明窗口，`/quadrant` 页面）：
  - 未登录：显示「请先登录」提示卡，点击打开主界面窗口登录；主界面登录成功后小组件**立即**刷新（storage 事件 `liug-sync` 打点，30s 轮询仅兜底）
  - 缩放：标题栏 −/＋ 按钮或 **Ctrl+滚轮**（420×320 ~ 1100×900）
  - 位置/尺寸/置顶记忆：窗口状态存 `data/widget.json`，关闭小组件或退出应用时保存，再次打开原位置原尺寸恢复（超出虚拟屏幕范围自动收回可见区）
  - 置顶：默认**不置顶**（不挡其他应用），标题栏图钉按钮切换（Win32 `SetWindowPos`），状态持久化
  - 配色：标题栏色点按钮循环切换 玻璃白 / 主题色轻染 / 暗色 三档，随主题色联动并记忆
  - 数据同步：任务增删改（`store.js` 各写操作）+ 登录/登出均打点 `liug-sync`，主界面与小组件互听 `storage` 事件**实时**双向同步（弹窗打开时主界面暂缓自动刷新，防打断编辑）
  - 透明窗口下 `backdrop-filter` 会把背景拍成不透明，`body.widget-mode` 全局禁用毛玻璃并以更实的底色替代（`global.css`）

## 六、测试环境（隔离测试库，不得写正式数据）

```powershell
# 主应用测试服务器（4301，首次启动自动创建测试管理员 admin / admin123）
$env:DIDA_USERS_DB_PATH='data/users.test.db'; $env:DIDA_USERS_DIR='data/users-test'; $env:PORT='4301'; python server/app.py
# 访问 http://localhost:4301

# 导入滴答清单备份 CSV 到测试库
$env:DIDA_DB_PATH='data/schedule.test.db'; python server/import_csv.py <csv路径>
```

用完记得清掉环境变量（`Remove-Item Env:DIDA_USERS_DB_PATH` 等）或直接关闭该终端，避免下次误连测试库。

## 七、常见问题

- **端口被占用**：4300 被占时先 `netstat -ano | findstr 4300` 找到 PID，确认是旧服务后 `taskkill /PID <pid> /F`。
- **旧登录态**：会话密钥沿用旧版，升级后浏览器免登录直接可用；若被登出，重新登录一次即可。
