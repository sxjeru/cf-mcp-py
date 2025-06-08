from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None, headers: dict = None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


async def http_exception(request: Request, exc: Exception) -> Response:
    if isinstance(exc, HTTPException):
        if exc.status_code in {204, 304}:
            return Response(status_code=exc.status_code, headers=exc.headers)
        return PlainTextResponse(
            exc.detail or "Internal Server Error", 
            status_code=exc.status_code, 
            headers=exc.headers
        )
    
    # 处理其他异常
    return PlainTextResponse(
        "Internal Server Error", 
        status_code=500
    )