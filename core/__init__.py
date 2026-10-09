"""流光 LIUG 业务核心（双端共用的 FastAPI 业务层）

包含：数据访问（db）、统一错误（errors）、节假日（holidays）、CSV 导入（import_csv）、
认证纯函数（auth）、业务路由（routes）、应用工厂（app_factory）。

本包不包含：
- 用户管理/账户体系（仅 server/ 远程后端持有，桌面 exe 不打包）
- 桌面壳与打包逻辑（desktop/）
"""
