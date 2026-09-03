用户问的是一个信息类问题：项目是否前后端分离、怎么启动。让我先看看结构和配置文件来回答。

用户只是问信息性问题，我直接从文件里读清楚了，不需要动代码或调用 skill。直接回答即可。
## 前后端分离架构

**是的，这是一个标准的前后端分离项目：**

| 层 | 技术 | 目录 | 默认端口 |
|---|---|---|---|
| 前端 | Vue 3 + Vite 6 | `client/` | **5180**（开发） |
| 后端 | Express 4 + Node 24 `node:sqlite` | `server/` | **4300**（生产）/ **4301**（测试） |

Vite 配置了 `/api` 反向代理到后端 `http://localhost:4300`，前端只负责 UI 和 REST 调用，数据库（SQLite）由后端独占管理。

## 启动方式

### 开发模式（两个终端分别跑）

```bash
# 终端 1：启动后端（http://localhost:4300）
npm run server

# 终端 2：启动前端（http://localhost:5180）
npm run client
```

### 生产模式（单一服务）

后端 Express 会直接托管 `client/dist/` 静态文件，只需一个进程：

```bash
# 先构建前端
cd client && npm run build
# 再启动后端（它会同时提供 API 和前端页面）
cd ../server && npm start
# 浏览器直接访问 http://localhost:4300
```

### 测试模式（数据隔离）

按 [AGENTS.md](file:///root/trae/dida_mock/dida-clone/AGENTS.md) 要求，所有测试必须走独立测试库（端口 4301）：

```bash
# 测试服务器
DIDA_USERS_DB_PATH=data/users.test.db DIDA_USERS_DIR=data/users-test PORT=4301 node server/index.js
# 然后浏览器自动化测试目标地址是 http://localhost:4301
```

### 首次运行别忘了装依赖

```bash
npm run install:all   # 等价于 npm install --prefix server && npm install --prefix client
```

## 总结

- **分离是彻底的**——`server/` 和 `client/` 各有独立的 `package.json`、`node_modules`，根目录只是编排脚本
- **开发时**两个进程并行，Vite 代理 `/api` → 后端
- **生产时**前端 build 成 `dist/`，后端 express.static 托管它，对外一个端口搞定