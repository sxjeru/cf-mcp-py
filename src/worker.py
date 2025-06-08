import sys
import json
import asyncio
import traceback
import time
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from workers import DurableObject, Response

sys.path.insert(0, "/session/metadata/vendor")
sys.path.insert(0, "/session/metadata")


async def execute_python_code(code: str) -> dict:
    """执行 Python 代码并返回结果"""
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


async def execute_python_code_stream(code: str):
    """执行 Python 代码并返回流式结果"""
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    
    try:
        # 发送开始事件
        yield f"data: {json.dumps({'type': 'start', 'timestamp': time.time()})}\n\n"
        
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
            
            # 发送执行中事件
            yield f"data: {json.dumps({'type': 'executing', 'code': code[:100] + ('...' if len(code) > 100 else '')})}\n\n"
            
            exec(code, exec_globals)
            
        # 发送输出事件
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        if stdout_output:
            yield f"data: {json.dumps({'type': 'stdout', 'content': stdout_output})}\n\n"
        
        if stderr_output:
            yield f"data: {json.dumps({'type': 'stderr', 'content': stderr_output})}\n\n"
        
        # 发送成功完成事件
        yield f"data: {json.dumps({'type': 'success', 'timestamp': time.time()})}\n\n"
        
    except Exception as e:
        # 发送错误事件
        error_info = {
            'type': 'error',
            'error_type': type(e).__name__,
            'error_message': str(e),
            'traceback': traceback.format_exc(),
            'stdout': stdout_capture.getvalue(),
            'stderr': stderr_capture.getvalue(),
            'timestamp': time.time()
        }
        yield f"data: {json.dumps(error_info)}\n\n"
    
    # 发送结束事件
    yield f"data: {json.dumps({'type': 'end', 'timestamp': time.time()})}\n\n"


class FastMCPServer(DurableObject):
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

    async def fetch(self, request):
        """处理请求的核心逻辑"""
        try:
            # 解析请求路径
            from urllib.parse import urlparse
            parsed_url = urlparse(request.url) 
            path = parsed_url.path
            status = 200
            
            # 简化的路由处理
            if path == "/" or path == "":
                response_data = {
                    "name": "Python Code Executor MCP Server",
                    "version": "1.0.0",
                    "description": "Execute Python code via MCP protocol with streaming support",
                    "endpoints": {
                        "tools": "/tools",
                        "call_tool": "/tools/call",
                        "stream": "/stream"
                    }
                }
                
            elif path == "/tools":
                response_data = {
                    "tools": [
                        {
                            "name": "execute_python",
                            "description": "Execute Python code and return the result",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code to execute"
                                    }
                                },
                                "required": ["code"]
                            }
                        },
                        {
                            "name": "execute_python_stream",
                            "description": "Execute Python code and return streaming results",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code to execute"
                                    }
                                },
                                "required": ["code"]
                            }
                        }
                    ]
                }
                
            elif path == "/stream" and request.method == "POST":
                # 处理流式工具调用
                body = await request.json()
                code = body.get("code", "")
                
                if not code:
                    return Response(
                        "Error: No code provided",
                        status=400,
                        headers={
                            "Content-Type": "text/plain",
                            "Access-Control-Allow-Origin": "*",
                        }
                    )
                
                # 创建流式响应
                async def stream_generator():
                    async for chunk in execute_python_code_stream(code):
                        yield chunk
                
                return Response(
                    stream_generator(),
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    }
                )
                
            elif path == "/tools/call" and request.method == "POST":
                # 处理工具调用
                body = await request.json()
                tool_name = body.get("name")
                args = body.get("arguments", {})
                
                if tool_name == "execute_python":
                    code = args.get("code", "")
                    
                    if not code:
                        response_data = {
                            "content": [{"type": "text", "text": "Error: No code provided"}]
                        }
                        status = 400
                    else:
                        # 执行 Python 代码
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
                        
                        response_data = {
                            "content": [{"type": "text", "text": response_text}]
                        }
                        status = 200
                elif tool_name == "execute_python_stream":
                    code = args.get("code", "")
                    
                    if not code:
                        response_data = {
                            "content": [{"type": "text", "text": "Error: No code provided. Use /stream endpoint for streaming execution."}]
                        }
                        status = 400
                    else:
                        response_data = {
                            "content": [{"type": "text", "text": f"Use /stream endpoint for streaming execution of code. POST to /stream with {{'code': 'your_code_here'}}"}]
                        }
                        status = 200
                else:
                    response_data = {"error": "Tool not found"}
                    status = 404
            else:
                response_data = {"error": "Not found"}
                status = 404
            
            # 返回响应
            return Response(
                json.dumps(response_data),
                status=status,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }
            )
            
        except Exception as e:
            # 错误处理
            error_response = {
                "error": f"Internal server error: {str(e)}",
                "traceback": traceback.format_exc()
            }
            return Response(
                json.dumps(error_response),
                status=500,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                }
            )


async def on_fetch(request, env):
    """Cloudflare Workers 的入口点"""
    try:
        # 直接处理 OPTIONS 请求
        if request.method == "OPTIONS":
            return Response(
                "",
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }
            )
        
        # 获取 Durable Object 实例
        if hasattr(env, 'FAST_MCP_SERVER'):
            id = env.FAST_MCP_SERVER.idFromName("main")
            obj = env.FAST_MCP_SERVER.get(id)
            return await obj.fetch(request)
        else:
            # 如果没有 Durable Object，直接处理请求
            from urllib.parse import urlparse
            parsed_url = urlparse(request.url) 
            path = parsed_url.path
            status = 200
            
            if path == "/" or path == "":
                response_data = {
                    "name": "Python Code Executor MCP Server",
                    "version": "1.0.0",
                    "description": "Execute Python code via MCP protocol with streaming support",
                    "endpoints": {
                        "tools": "/tools",
                        "call_tool": "/tools/call",
                        "stream": "/stream"
                    }
                }
                
            elif path == "/tools":
                response_data = {
                    "tools": [
                        {
                            "name": "execute_python",
                            "description": "Execute Python code and return the result",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code to execute"
                                    }
                                },
                                "required": ["code"]
                            }
                        },
                        {
                            "name": "execute_python_stream",
                            "description": "Execute Python code and return streaming results",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code to execute"
                                    }
                                },
                                "required": ["code"]
                            }
                        }
                    ]
                }
                
            elif path == "/stream" and request.method == "POST":
                # 处理流式工具调用
                body = await request.json()
                code = body.get("code", "")
                
                if not code:
                    return Response(
                        "Error: No code provided",
                        status=400,
                        headers={
                            "Content-Type": "text/plain",
                            "Access-Control-Allow-Origin": "*",
                        }
                    )
                
                # 创建流式响应
                async def stream_generator():
                    async for chunk in execute_python_code_stream(code):
                        yield chunk
                
                return Response(
                    stream_generator(),
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    }
                )
                
            elif path == "/tools/call" and request.method == "POST":
                body = await request.json()
                tool_name = body.get("name")
                args = body.get("arguments", {})
                
                if tool_name == "execute_python":
                    code = args.get("code", "")
                    
                    if not code:
                        response_data = {
                            "content": [{"type": "text", "text": "Error: No code provided"}]
                        }
                        status = 400
                    else:
                        result = await execute_python_code(code)
                        
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
                        
                        response_data = {
                            "content": [{"type": "text", "text": response_text}]
                        }
                        status = 200
                elif tool_name == "execute_python_stream":
                    code = args.get("code", "")
                    
                    if not code:
                        response_data = {
                            "content": [{"type": "text", "text": "Error: No code provided. Use /stream endpoint for streaming execution."}]
                        }
                        status = 400
                    else:
                        response_data = {
                            "content": [{"type": "text", "text": f"Use /stream endpoint for streaming execution of code. POST to /stream with {{'code': 'your_code_here'}}"}]
                        }
                        status = 200
                else:
                    response_data = {"error": "Tool not found"}
                    status = 404
            else:
                response_data = {"error": "Not found"}
                status = 404
            
            return Response(
                json.dumps(response_data),
                status=status,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }
            )
            
    except Exception as e:
        error_response = {
            "error": f"Internal server error: {str(e)}",
            "traceback": traceback.format_exc()
        }
        return Response(
            json.dumps(error_response),
            status=500,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            }
        )