"""共享 FastAPI 应用工厂：业务路由 + 认证路由 + 静态托管（SPA fallback）

服务端（多用户账户体系）与桌面客户端（本地单用户）各自注入认证实现，业务核心完全共享：
    app = create_app(get_user_id_dependency, auth_router)

静态资源目录：LIUG_DIST_DIR 环境变量（桌面冻结模式指向 _MEIPASS 内副本），缺省 <根>/client/dist。
"""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from core import routes as core_routes
from core.errors import ApiError

ROOT_DIR = Path(__file__).resolve().parents[1]


def _dist_dir() -> Path:
    d = os.environ.get('LIUG_DIST_DIR')
    return Path(d).resolve() if d else (ROOT_DIR / 'client' / 'dist')


def _web_dir() -> Path:
    """官网静态站目录（/liug 路径托管），可用 LIUG_WEB_DIR 覆盖"""
    d = os.environ.get('LIUG_WEB_DIR')
    return Path(d).resolve() if d else (ROOT_DIR / 'web')


def create_app(get_user_id_dep, auth_router, extra_routers=()):
    """组装完整 FastAPI 应用

    :param get_user_id_dep: 认证依赖（接收 Request，校验会话，返回用户库 ID 字符串），
                            覆盖 core.routes.get_user_id 占位
    :param auth_router:     认证路由（login / logout / me / change-password，prefix='/api'）
    :param extra_routers:   额外路由（如桌面端同步引擎路由）；必须在 SPA catch-all 之前
                            注册，否则其 GET 端点会被 fallback 吞掉返回 404
    """
    # redirect_slashes=False：对齐 Express（/api/tasks/ 不做 307 重定向）；关闭 /docs 等文档暴露面
    app = FastAPI(redirect_slashes=False, docs_url=None, redoc_url=None, openapi_url=None)

    # 与 Express cors() 默认行为一致（同源部署下本就无需 CORS，仅保持对外部 Origin 行为一致）
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        # 统一错误响应形状 {"error": "中文消息"}（FastAPI 默认 {"detail": ...} 与前端不符）
        return JSONResponse({'error': exc.message}, status_code=exc.status)

    app.dependency_overrides[core_routes.get_user_id] = get_user_id_dep
    app.include_router(auth_router)
    app.include_router(core_routes.router)
    for r in extra_routers:
        app.include_router(r)

    @app.get('/{full_path:path}', include_in_schema=False)
    def spa_fallback(full_path: str):
        """对齐 Express：express.static(dist) + 非 /api/* 一律回退 index.html"""
        if full_path.startswith('api/'):
            raise ApiError(404, 'Not Found')
        # 官网静态站：/liug 与 /liug/* 由 web/ 目录托管；
        # 目录不存在时（如桌面 exe 未打包 web/）保持原 SPA 行为
        if full_path == 'liug' or full_path.startswith('liug/'):
            web = _web_dir()
            if web.is_dir():
                rel = full_path[len('liug'):].lstrip('/') or 'index.html'
                candidate = (web / rel).resolve()
                try:
                    candidate.relative_to(web.resolve())
                except ValueError:
                    raise ApiError(404, 'Not Found')  # 防目录穿越
                if not candidate.is_file():
                    raise ApiError(404, 'Not Found')
                # index.html 每次回源校验（口径同主应用 SPA，防 WebView2 旧缓存）
                headers = {'Cache-Control': 'no-cache'} if rel == 'index.html' else None
                return FileResponse(candidate, headers=headers)
        if full_path:
            dist = _dist_dir()
            candidate = (dist / full_path).resolve()
            try:
                candidate.relative_to(dist.resolve())
            except ValueError:
                candidate = None  # 防目录穿越
            if candidate and candidate.is_file():
                return FileResponse(candidate)
        # index.html 必须每次回源校验（no-cache + ETag 条件请求）：
        # WebView2 磁盘缓存持久化（%APPDATA%\pywebview），无缓存头时旧 index.html 会被
        # 启发式缓存，导致前端更新后旧 JS 包迟迟不刷新（静态资源带 hash 可安全长缓存）
        return FileResponse(_dist_dir() / 'index.html',
                            headers={'Cache-Control': 'no-cache'})

    return app
