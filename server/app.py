"""FastAPI 主后端（由原 Node Express 版完全重写，接口行为 1:1 对齐）

一个进程同时提供：
- /api/*      业务接口（对应原 server/index.js）
- /system/*   用户管理接口（由原 system-admin Flask 程序合并而来）
- /system-admin/  用户管理静态前端（web_admin/）
- 其余 GET    Vue 客户端静态托管（client/dist）+ SPA fallback

启动：python app.py（生产端口 4300；测试 PORT=4301 + 重定向用户库环境变量）
"""
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import users
from errors import ApiError
from routes_api import router as api_router
from routes_system import router as system_router

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR.parent / 'client' / 'dist'
PORT = int(os.environ.get('PORT') or '4300')

# redirect_slashes=False：对齐 Express（/api/tasks/ 不做 307 重定向）
# 关闭 /docs 等文档暴露面（Express 没有）
app = FastAPI(redirect_slashes=False, docs_url=None, redoc_url=None, openapi_url=None)

# 与 Express cors() 默认行为一致（同源部署下本就无需 CORS，仅保持对外部 Origin 行为一致）
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    # 统一错误响应形状 {"error": "中文消息"}（FastAPI 默认 {"detail": ...} 与前端不符）
    return JSONResponse({'error': exc.message}, status_code=exc.status)


app.include_router(api_router)
app.include_router(system_router)


@app.get('/system-admin', include_in_schema=False)
def system_admin_redirect():
    return RedirectResponse('/system-admin/')


app.mount('/system-admin', StaticFiles(directory=BASE_DIR / 'web_admin', html=True), name='system-admin')


@app.get('/{full_path:path}', include_in_schema=False)
def spa_fallback(full_path: str):
    """对齐 Express：express.static(dist) + 非 /api/* 一律回退 index.html（含 /system/* 排除）"""
    if full_path.startswith(('api/', 'system/')):
        raise ApiError(404, 'Not Found')
    if full_path:
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(DIST_DIR.resolve())
        except ValueError:
            candidate = None  # 防目录穿越
        if candidate and candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(DIST_DIR / 'index.html')


if __name__ == '__main__':
    # 首次启动：初始化用户主库（默认 admin/admin123 + 旧数据只读迁移），对齐 Node 在 listen 前完成
    users.bootstrap_users(legacy_db_path=BASE_DIR.parent / 'data' / 'schedule.db')
    print(f'[server] running at http://localhost:{PORT}')
    uvicorn.run(app, host='0.0.0.0', port=PORT)
