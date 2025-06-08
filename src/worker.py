import sys
import json
import asyncio
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from workers import DurableObject

sys.path.insert(0, "/session/metadata/vendor")
sys.path.insert(0, "/session/metadata")


def setup_server():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route
    from starlette.middleware.cors import CORSMiddleware
    
    async def execute_python_code_streaming(code: str):
        """流式执行 Python 代码并实时返回结果"""
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        # 首先发送开始执行的信号
        yield json.dumps({
            "type": "execution_start",
            "timestamp": asyncio.get_event_loop().time()
        }) + "\n"
        
        try:
            # 重定向标准输出和错误输出
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # 创建一个安全的执行环境
                exec_globals = {
                    '__builtins__': {
                        'print': print,
                        'len': len,
                        'str': str,
                        'int': int,
                        'float': float,
                        'list': list,
                        'dict': dict,
                        'tuple': tuple,
                        'set': set,
                        'range': range,
                        'enumerate': enumerate,
                        'zip': zip,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'round': round,
                        'sorted': sorted,
                        'reversed': reversed,
                        'type': type,
                        'isinstance': isinstance,
                        'hasattr': hasattr,
                        'getattr': getattr,
                        'setattr': setattr,
                        'bool': bool,
                    }
                }
                
                # 执行代码
                exec(code, exec_globals)
                
            # 发送标准输出
            stdout_content = stdout_capture.getvalue()
            if stdout_content:
                yield json.dumps({
                    "type": "stdout",
                    "content": stdout_content
                }) + "\n"
            
            # 发送标准错误
            stderr_content = stderr_capture.getvalue()
            if stderr_content:
                yield json.dumps({
                    "type": "stderr", 
                    "content": stderr_content
                }) + "\n"
            
            # 发送成功完成信号
            yield json.dumps({
                "type": "execution_complete",
                "success": True,
                "timestamp": asyncio.get_event_loop().time()
            }) + "\n"
            
        except Exception as e:
            # 发送错误输出（如果有）
            stderr_content = stderr_capture.getvalue()
            if stderr_content:
                yield json.dumps({
                    "type": "stderr",
                    "content": stderr_content
                }) + "\n"
            
            # 发送异常信息
            yield json.dumps({
                "type": "error",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }) + "\n"
            
            # 发送执行完成信号（失败）
            yield json.dumps({
                "type": "execution_complete",
                "success": False,
                "timestamp": asyncio.get_event_loop().time()
            }) + "\n"
    
    async def execute_python_code(code: str) -> dict:
        """非流式执行 Python 代码（用于兼容性）"""
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec_globals = {
                    '__builtins__': {
                        'print': print,
                        'len': len,
                        'str': str,
                        'int': int,
                        'float': float,
                        'list': list,
                        'dict': dict,
                        'tuple': tuple,
                        'set': set,
                        'range': range,
                        'enumerate': enumerate,
                        'zip': zip,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'round': round,
                        'sorted': sorted,
                        'reversed': reversed,
                        'type': type,
                        'isinstance': isinstance,
                        'hasattr': hasattr,
                        'getattr': getattr,
                        'setattr': setattr,
                        'bool': bool,
                    }
                }
                
                exec(code, exec_globals)
                
            result = {
                "success": True,
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
                "error": None
            }
            
        except Exception as e:
            result = {
                "success": False,
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
                "error": f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            }
        
        return result
    
    # MCP 工具列表
    async def list_tools(request):
        tools = [
            {
                "name": "execute_python",
                "description": "Execute Python code and return the result",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute"
                        },
                        "stream": {
                            "type": "boolean", 
                            "description": "Whether to stream the response",
                            "default": False
                        }
                    },
                    "required": ["code"]
                }
            }
        ]
        return JSONResponse({"tools": tools})
    
    # 调用工具
    async def call_tool(request):
        body = await request.json()
        tool_name = body.get("name")
        args = body.get("arguments", {})
        
        if tool_name == "execute_python":
            code = args.get("code", "")
            stream = args.get("stream", False)
            
            if not code:
                return JSONResponse({
                    "content": [{"type": "text", "text": "Error: No code provided"}]
                }, status_code=400)
            
            if stream:
                # 返回流式响应
                return StreamingResponse(
                    execute_python_code_streaming(code),
                    media_type="application/x-ndjson",  # Newline Delimited JSON
                    headers={
                        "Cache-Control": "no-cache",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    }
                )
            else:
                # 返回标准响应
                result = await execute_python_code(code)
                
                # 格式化输出
                output_parts = []
                if result["stdout"]:
                    output_parts.append(f"Output:\n{result['stdout']}")
                if result["stderr"]:
                    output_parts.append(f"Errors:\n{result['stderr']}")
                if result["error"]:
                    output_parts.append(f"Exception:\n{result['error']}")
                
                if not output_parts:
                    output_parts.append("Code executed successfully with no output.")
                
                response_text = "\n\n".join(output_parts)
                
                return JSONResponse({
                    "content": [{"type": "text", "text": response_text}]
                })
        
        return JSONResponse({"error": "Tool not found"}, status_code=404)
    
    # 流式执行端点
    async def stream_execute(request):
        """专门的流式执行端点"""
        body = await request.json()
        code = body.get("code", "")
        
        if not code:
            return JSONResponse({
                "error": "No code provided"
            }, status_code=400)
        
        return StreamingResponse(
            execute_python_code_streaming(code),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }
        )
    
    # WebSocket 风格的持久连接（可选）
    async def websocket_style_stream(request):
        """模拟 WebSocket 的持久流式连接"""
        async def persistent_stream():
            # 发送连接建立信号
            yield json.dumps({
                "type": "connection_established",
                "timestamp": asyncio.get_event_loop().time()
            }) + "\n"
            
            # 保持连接并等待进一步指令
            # 在实际应用中，这里可以处理多个代码执行请求
            try:
                while True:
                    await asyncio.sleep(1)
                    # 发送心跳
                    yield json.dumps({
                        "type": "heartbeat",
                        "timestamp": asyncio.get_event_loop().time()
                    }) + "\n"
                    
            except asyncio.CancelledError:
                # 连接关闭
                yield json.dumps({
                    "type": "connection_closed",
                    "timestamp": asyncio.get_event_loop().time()
                }) + "\n"
        
        return StreamingResponse(
            persistent_stream(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS", 
                "Access-Control-Allow-Headers": "*",
            }
        )
    
    # 根路径
    async def root(request):
        return JSONResponse({
            "name": "Python Code Executor MCP Server",
            "version": "1.0.0",
            "description": "Execute Python code via MCP protocol with streaming support",
            "endpoints": {
                "tools": "/tools",
                "call_tool": "/tools/call",
                "stream_execute": "/stream/execute",
                "persistent_stream": "/stream/persistent"
            },
            "streaming_formats": [
                "application/x-ndjson",
                "application/json-stream"
            ]
        })
    
    routes = [
        Route("/", root, methods=["GET"]),
        Route("/tools", list_tools, methods=["GET"]),
        Route("/tools/call", call_tool, methods=["POST"]),
        Route("/stream/execute", stream_execute, methods=["POST"]),
        Route("/stream/persistent", websocket_style_stream, methods=["GET"]),
    ]
    
    app = Starlette(routes=routes)
    app.add_middleware(
        CORSMiddleware, 
        allow_origins=["*"], 
        allow_methods=["*"], 
        allow_headers=["*"]
    )
    
    return app


class FastMCPServer(DurableObject):
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env
        self.app = setup_server()

    async def on_fetch(self, request, env, ctx):
        # 直接使用 Starlette 应用处理请求，避免使用有问题的 ASGI 适配器
        try:
            # 创建一个简单的 ASGI 适配器来处理 Cloudflare Workers 请求
            from starlette.responses import Response
            
            # 构建 ASGI scope
            method = request.method
            path = request.url.split('?')[0].split('/', 3)[-1] if '/' in request.url else '/'
            if not path.startswith('/'):
                path = '/' + path
            
            query_string = request.url.split('?', 1)[1] if '?' in request.url else ''
            
            # 处理请求头 - 修复原始错误
            headers = []
            if hasattr(request, 'headers') and request.headers:
                for key, value in request.headers.items():
                    headers.append([key.lower().encode('latin-1'), value.encode('latin-1')])
            
            scope = {
                'type': 'http',
                'method': method,
                'path': path,
                'query_string': query_string.encode('latin-1'),
                'headers': headers,
            }
            
            # 读取请求体
            body = b''
            if method in ['POST', 'PUT', 'PATCH']:
                body_text = await request.text()
                body = body_text.encode('utf-8')
            
            # ASGI receive callable
            async def receive():
                return {
                    'type': 'http.request',
                    'body': body,
                    'more_body': False,
                }
            
            # ASGI send callable 和响应收集
            response_started = False
            response_status = 200
            response_headers = []
            response_body = b''
            
            async def send(message):
                nonlocal response_started, response_status, response_headers, response_body
                
                if message['type'] == 'http.response.start':
                    response_started = True
                    response_status = message['status']
                    response_headers = message.get('headers', [])
                elif message['type'] == 'http.response.body':
                    response_body += message.get('body', b'')
            
            # 调用 Starlette 应用
            await self.app(scope, receive, send)
            
            # 构建响应
            headers_dict = {}
            for header_pair in response_headers:
                key = header_pair[0].decode('latin-1')
                value = header_pair[1].decode('latin-1')
                headers_dict[key] = value
            
            return Response(
                content=response_body,
                status_code=response_status,
                headers=headers_dict
            )
            
        except Exception as e:
            # 错误处理
            error_response = {
                "error": f"Internal server error: {str(e)}",
                "traceback": traceback.format_exc()
            }
            return Response(
                content=json.dumps(error_response),
                status_code=500,
                headers={"content-type": "application/json"}
            )


async def on_fetch(request, env):
    id = env.ns.idFromName("A")
    obj = env.ns.get(id)
    return await obj.fetch(request)