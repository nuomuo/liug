"""服务端入口（远程后端：多用户账户体系 + 业务 API + 静态托管）

本目录只保留「用户管理 + 应用组装」，不再包含：
- 桌面壳 / exe 打包逻辑（已迁移至 desktop/）
- 业务路由与数据层（已沉淀至 core/，与桌面端共享）

启动：python server/app.py（生产端口 4300；测试 PORT=4301 + 重定向用户库环境变量）
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # 让 server/ 内模块能找到根目录的 core 包

import uvicorn

import users
from core.app_factory import create_app
from routes_admin import router as admin_router
from routes_auth import get_user_id, router as auth_router

PORT = int(os.environ.get('PORT') or '4300')

# 初次启动初始化（幂等）：数据目录 + 用户主库 users.db + .secret + 默认 admin/admin123
# 及其独立数据库（存在旧正式库时只读迁移）。放在模块级，无论 python server/app.py
# 还是 uvicorn server.app:app 方式启动，都在 listen 前完成初始化。
users.bootstrap_users(legacy_db_path=_ROOT / 'data' / 'schedule.db')

# 管理端路由（/admin：用户管理 + admin_client/dist 托管）须在 SPA catch-all 之前注册
app = create_app(get_user_id, auth_router, extra_routers=[admin_router])


if __name__ == '__main__':
    print(f'[server] running at http://localhost:{PORT}')
    uvicorn.run(app, host='0.0.0.0', port=PORT)
