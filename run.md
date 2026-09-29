# 启动指南

前后端分离架构：后端为 Python FastAPI（`server/`），前端为 Vue3 + Vite（`client/`）。
npm 相关内容已全部收进 `client/package.json`，项目根目录不再有 package.json。

## 一、首次准备（只需一次）

```powershell
# 1. 安装后端依赖（fastapi / uvicorn / httpx / regex）
pip install -r server/requirements.txt

# 2. 安装前端依赖（主应用 + 用户管理前端）
npm install --prefix client
npm install --prefix admin-client
```

## 二、启动后端（必须）

后端同时提供 API 并托管前端构建产物和用户管理页，**日常使用只需启动它**：

```powershell
# 在项目根目录执行
python server/app.py
# 或者：
npm run server --prefix client
```

- 主应用：<http://localhost:4300>
- 用户管理页：<http://localhost:4300/system-admin/>（仅管理员）

## 三、启动前端

### 日常使用（无需启动）

后端直接托管 `client/dist/` 构建产物，启动后端后访问 <http://localhost:4300> 即可。

### 开发模式（改前端代码时用，热更新）

```powershell
npm run dev --prefix client
```

- 开发服务器：<http://localhost:5180>（`/api` 自动代理到 4300，**需先启动后端**）

### 改完前端代码后发布

```powershell
npm run build --prefix client
```

构建产物输出到 `client/dist/`，刷新 <http://localhost:4300> 即生效。

### 用户管理前端（admin-client/，独立 Vue3 程序）

```powershell
# 开发模式（热更新，/system 代理到 4300）
npm run dev --prefix admin-client
# 访问 http://localhost:5181/system-admin/

# 构建发布（产物 admin-client/dist/，由后端托管在 /system-admin/）
npm run build --prefix admin-client
```

## 四、测试环境（隔离测试库，不得写正式数据）

```powershell
# 主应用测试服务器（4301，首次启动自动创建测试管理员 admin / admin123）
$env:DIDA_USERS_DB_PATH='data/users.test.db'; $env:DIDA_USERS_DIR='data/users-test'; $env:PORT='4301'; python server/app.py
# 访问 http://localhost:4301，用户管理页 http://localhost:4301/system-admin/

# 导入滴答清单备份 CSV 到测试库
$env:DIDA_DB_PATH='data/schedule.test.db'; python server/import_csv.py <csv路径>
```

用完记得清掉环境变量（`Remove-Item Env:DIDA_USERS_DB_PATH` 等）或直接关闭该终端，避免下次误连测试库。

## 五、常见问题

- **端口被占用**：4300 被占时先 `netstat -ano | findstr 4300` 找到 PID，确认是旧服务后 `taskkill /PID <pid> /F`。
- **旧登录态**：会话密钥沿用旧版，升级后浏览器免登录直接可用；若被登出，重新登录一次即可。
