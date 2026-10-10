# 启动指南

前后端分离架构：后端为 Python FastAPI（`server/`），前端为 Vue3 + Vite（`client/`）。
npm 相关内容已全部收进 `client/package.json`，项目根目录不再有 package.json。

## 一、首次准备（只需一次）

```powershell
# 1. 安装后端依赖（fastapi / uvicorn / httpx / regex）
pip install -r server/requirements.txt

# 2. 安装前端依赖（主应用）
npm install --prefix client

# 3. 安装管理端前端依赖（可选，需要用户管理功能时安装）
npm install --prefix admin_client
```

## 二、一键管理脚本（推荐）

日常编译、启动、停止全部通过根目录的 `manage.py` 完成，**Windows / Linux 通用**：

```powershell
python manage.py build      # 编译前后端所有模块（Python 语法检查 + client + admin_client）
python manage.py start      # 启动后端（4300 正式库，后台常驻，不占终端）
python manage.py stop       # 停止后端（只杀 python 进程，不误杀桌面端 liug.exe）
python manage.py restart    # 重启后端（改了后端代码后生效用）
python manage.py status     # 查看端口与进程状态
```

- 首次部署顺序：`pip install -r server/requirements.txt` → `python manage.py build` → `python manage.py start`
- `build` 对两个前端在缺 `node_modules` 时自动执行 `npm install`，无需单独装依赖
- 运行日志写入 `data/server.log`（启动失败时脚本会自动打印日志末尾便于排查）
- 所有命令均可加 `--test` 切换到测试环境（见「七、测试环境」）
- **Linux 服务器部署**：在 venv 中运行 `python manage.py start`，服务以 `setsid` 后台常驻，SSH 断开后仍存活；停止时先 SIGTERM 优雅退出、超时再 SIGKILL；端口探测依赖 `ss`（或老系统 `netstat`），非 root 用户查看他人进程需 `sudo`

### 服务环境变量：config.yaml

`start / restart` 会读取根目录 `config.yaml` 的 `env` 段并注入为服务进程的环境变量，**修改后 restart 即生效**（无需 export，服务器上也不必装 PyYAML——内置了简易解析，只支持 `env` 段下的 `KEY: value` 与注释）：

```yaml
env:
  # 管理端 /admin 的 IP 白名单：逗号分隔，支持单 IP / CIDR 网段（192.168.1.0/24）/ * 全放行
  # 不配置（注释掉）= 不做限制，任意 IP 可访问 /admin
  # LIUG_ADMIN_ALLOWED_IPS: "127.0.0.1,::1,203.0.113.10"
```

- 配置文件优先于 shell 中已 export 的同名变量（配置文件即唯一真相源）；启动时会打印实际注入的每个变量
- `LIUG_ADMIN_ALLOWED_IPS` **不配置即不限制**（任意 IP 可访问 /admin，仍有账号密码 + 管理员角色防线）；配置后仅放行名单内来源，名单外访问 /admin 一律 403
- 更稳妥的公网管理方式：用 SSH 隧道 `ssh -L 4300:localhost:4300 root@服务器` 后本地访问 `http://localhost:4300/admin/`，无需对外放行
- 注意：反向代理（nginx 等）部署时后端看到的来源是代理 IP，配置了白名单需把代理 IP 一并加入或直连端口访问；`PORT` 由 manage.py 统一管理（4300/4301），在 config.yaml 里配置会被忽略并警告

## 三、启动后端（手动方式，必须了解）

后端同时提供 API 并托管前端构建产物，**日常使用只需启动它**：

```powershell
# 在项目根目录执行
python server/app.py
# 或者：
npm run server --prefix client
```

- 主应用：[http://localhost:4300](http://localhost:4300)

## 四、启动前端

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

### 管理端（用户管理，可选）

独立的用户管理控制台，仅服务器端提供（桌面 exe 不包含）。首次使用需安装依赖并构建：

```powershell
npm run build --prefix admin_client    # 需先 npm install --prefix admin_client
```

- 访问 [http://localhost:4300/admin/](http://localhost:4300/admin/)，用管理员账号（默认 `admin`）登录
- 功能：新增用户、启用/禁用、重置密码、切换管理员/普通角色、删除用户；不能对自己禁用/降级/删除，系统至少保留一个可用管理员
- **IP 白名单**：环境变量 `LIUG_ADMIN_ALLOWED_IPS`（逗号分隔，支持 IP / CIDR / `*`，默认 `127.0.0.1,::1` 仅本机）；白名单外访问任何 /admin 资源（含页面与登录）一律 403，不影响主应用。例如放行局域网：

```powershell
$env:LIUG_ADMIN_ALLOWED_IPS='127.0.0.1,::1,192.168.1.0/24'; python server/app.py
```

- 开发模式（改管理端前端代码时用，热更新）：

```powershell
npm run dev --prefix admin_client
```

- 开发服务器 [http://localhost:5181](http://localhost:5181)（`/admin` 自动代理到 4300，**需先启动后端**）
- 静态资源目录可用 `LIUG_ADMIN_DIST_DIR` 覆盖（默认 `admin_client/dist`）；未构建时访问 /admin/ 返回 404 提示

## 五、桌面四象限小组件（可选）

pywebview 无边框透明置顶窗口，加载主应用的 `/quadrant` 页面（需先执行过 `npm run build --prefix client`）：

```powershell
python desktop/desktop_widget.py
```

- 主服务（4300）已在运行时直接复用它；未运行则自动内嵌启动一份独立服务（本地单用户认证），可脱离主程序单独使用
- 首次使用需在小组件窗口内登录一次（WebView2 会记住登录态）
- 按住标题栏空白处拖动窗口；标题栏右侧有刷新 / 最小化 / 关闭按钮
- 依赖见 `desktop/requirements.txt`（pywebview / pystray / pillow 等）
- 浏览器调试地址：主服务启动后访问 [http://localhost:4300/quadrant](http://localhost:4300/quadrant)

## 六、桌面版整应用（liug.exe）

`desktop/main.py`：一个进程搞定全部——系统托盘常驻（pystray）+ 主界面窗口 + 可选桌面小组件 + 内嵌 uvicorn 服务。
桌面客户端支持**单机模式（免登录）**与**远程账号（云端同步）**两种使用方式（不含用户管理逻辑，账户体系仅在 `server/` 远程后端）：

```powershell
# 源码运行（开发模式）
python desktop/main.py

# 测试数据目录（不碰项目 data/ 正式数据）
$env:LIUG_DATA_DIR='<临时目录>'; $env:LIUG_USERS_DIR='<临时目录>/users'; python desktop/main.py

# 打包成单个 exe（需先 build 过 client）
pip install pyinstaller
python -m PyInstaller --noconfirm liug.spec
# 产物：dist/liug.exe（约 42 MB，单文件、无控制台窗口，双击即用）
```

- **托盘**：双击图标或菜单「打开流光 LIUG」显示主窗口；右键菜单可勾选开关「显示桌面小组件（四象限）」；「退出」彻底结束进程
- **主窗口点 ×**：仅隐藏到托盘继续驻留（托盘应用惯例），从托盘「退出」才真正退出
- **单实例**：Windows 互斥体锁，重复双击弹提示「已在运行」
- **端口**：内嵌服务使用粘性动态端口——上次端口 → 4300 → 随机（socket 预绑定后交给 uvicorn，无竞态窗口），端口记录在 `<数据目录>/service-port.json` 供小组件发现；端口跳变会导致 WebView localStorage（主题色等）按 origin 隔离而"丢失"，粘性策略保跨重启稳定
- **数据与日志（exe）**：数据目录在用户家目录 `~/.liug`（如 `C:\Users\<用户>\.liug`），首次启动自动把 exe 同级旧 `data/` 整体迁移过去；目录设为隐藏+系统属性并用 ACL 拒绝删除，防误删（应用读写不受影响；确需删除：`icacls "$env:USERPROFILE\.liug" /remove:d "$env:USERDOMAIN\$env:USERNAME"` 后再删）；运行日志 `~/.liug/desktop.log`、错误日志 `~/.liug/desktop.err.log`（排查 exe 问题先看这两个文件）。开发模式仍是项目 `data/`
- **单机模式（免登录）**：登录页点「单机使用（免登录）」即进入，无账号无密码，数据仅在 `<数据目录>/users/local.db` 单文件，不同步任何服务器；点一次后跨重启免登录（本地会话有效期 10 年，密钥 `<数据目录>/local.secret`）
- **云端账号（离线可用 + 双向同步）**：登录页「登录账号（云端同步）」填写服务器地址（存 `<数据目录>/config.json`）与账号密码，本地服务代理登录远程服务器（WebView 不整页跳转）；数据保存在本地镜像库 `<数据目录>/users/<远程用户ID>.db`，**断网照常使用**；联网后由同步引擎自动双向同步（本地写后防抖 3 秒 + 每 5 分钟定时 + 设置面板手动「立即同步」），LWW 合并（新者胜）；远程令牌存 `<数据目录>/remote-session.json`，过期后设置面板提示重新登录（不影响离线使用），同步状态存 `<数据目录>/sync-state.json`
- **登录持久化**：WebView2 以非隐私模式运行（`private_mode=False`），cookies/localStorage 落在 `<数据目录>/webview/`（exe 为 `~/.liug/webview/`），重启 exe 免登录（除非手动退出登录）；单机会话 10 年、云端本地会话 30 天（远程令牌 7 天，过期仅影响同步）
- **桌面小组件**（无边框透明窗口，`/quadrant` 页面）：
  - 未登录：显示「请先登录」提示卡，点击打开主界面窗口登录；主界面登录成功后小组件**立即**刷新（storage 事件 `liug-sync` 打点，30s 轮询仅兜底）
  - 缩放：标题栏 −/＋ 按钮或 **Ctrl+滚轮**（420×320 ~ 1100×900）
  - 位置/尺寸/置顶记忆：窗口状态存 `<数据目录>/widget.json`，关闭小组件或退出应用时保存，再次打开原位置原尺寸恢复（超出虚拟屏幕范围自动收回可见区）
  - 置顶：默认**不置顶**（不挡其他应用），标题栏图钉按钮切换（Win32 `SetWindowPos`），状态持久化
  - 配色：标题栏色点按钮循环切换 玻璃白 / 主题色轻染 / 暗色 三档，随主题色联动并记忆
  - 数据同步：任务增删改（`store.js` 各写操作）+ 登录/登出均打点 `liug-sync`，主界面与小组件互听 `storage` 事件**实时**双向同步（弹窗打开时主界面暂缓自动刷新，防打断编辑）
  - 透明窗口下 `backdrop-filter` 会把背景拍成不透明，`body.widget-mode` 全局禁用毛玻璃并以更实的底色替代（`global.css`）

## 七、测试环境（隔离测试库，不得写正式数据）

```powershell
# 方式一：一键脚本（推荐，自动设置隔离环境变量并后台启动）
python manage.py start --test
python manage.py stop --test

# 方式二：手动启动（4301，首次启动自动创建测试管理员 admin / admin123）
$env:LIUG_USERS_DB_PATH='data/users.test.db'; $env:LIUG_USERS_DIR='data/users-test'; $env:PORT='4301'; python server/app.py
# 访问 http://localhost:4301（管理端测试：http://localhost:4301/admin/）

# 导入外部清单应用备份 CSV 到测试库
$env:LIUG_DB_PATH='data/schedule.test.db'; python core/import_csv.py <csv路径>
```

用完记得清掉环境变量（`Remove-Item Env:LIUG_USERS_DB_PATH` 等）或直接关闭该终端，避免下次误连测试库。

## 八、常见问题

- **端口被占用**：`python manage.py status` 查看占用情况；确认是旧服务后 `python manage.py stop`（或手动 `taskkill /PID <pid> /F`）。
- **旧登录态**：会话密钥沿用旧版，升级后浏览器免登录直接可用；若被登出，重新登录一次即可。
