"""FastAPI 主后端（由原 Node Express 版完全重写，接口行为 1:1 对齐）

一个进程同时提供：
- /api/*      业务接口（对应原 server/index.js）
- 其余 GET    Vue 客户端静态托管（client/dist）+ SPA fallback

启动：python app.py（生产端口 4300；测试 PORT=4301 + 重定向用户库环境变量）
"""
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import users
from errors import ApiError
from routes_api import router as api_router

BASE_DIR = Path(__file__).resolve().parent
# 静态资源目录：可用环境变量覆盖（quadrant.exe 冻结模式下指向 PyInstaller 解包目录 _MEIPASS 内的副本）
DIST_DIR = Path(os.environ.get('DIDA_DIST_DIR') or (BASE_DIR.parent / 'client' / 'dist'))
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


@app.get('/{full_path:path}', include_in_schema=False)
def spa_fallback(full_path: str):
    """对齐 Express：express.static(dist) + 非 /api/* 一律回退 index.html"""
    if full_path.startswith('api/'):
        raise ApiError(404, 'Not Found')
    if full_path:
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(DIST_DIR.resolve())
        except ValueError:
            candidate = None  # 防目录穿越
        if candidate and candidate.is_file():
            return FileResponse(candidate)
    # index.html 必须每次回源校验（no-cache + ETag 条件请求）：
    # WebView2 磁盘缓存持久化（%APPDATA%\pywebview），无缓存头时旧 index.html 会被
    # 启发式缓存，导致前端更新后旧 JS 包迟迟不刷新（静态资源带 hash 可安全长缓存）
    return FileResponse(DIST_DIR / 'index.html',
                        headers={'Cache-Control': 'no-cache'})


if __name__ == '__main__':
    # 首次启动：初始化用户主库（默认 admin/admin123 + 旧数据只读迁移），对齐 Node 在 listen 前完成
    users.bootstrap_users(legacy_db_path=BASE_DIR.parent / 'data' / 'schedule.db')
    print(f'[server] running at http://localhost:{PORT}')
    uvicorn.run(app, host='0.0.0.0', port=PORT)
