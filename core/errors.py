"""统一业务错误：所有接口的错误响应形状为 {"error": "中文消息"}（对齐 Express 版，前端读取 err.data.error）"""


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message
