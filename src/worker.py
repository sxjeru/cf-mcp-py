import sys
import json
import asyncio
import traceback
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
                    "description": "Execute Python code via MCP protocol",
                    "endpoints": {
                        "tools": "/tools",
                        "call_tool": "/tools/call"
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
                        }
                    ]
                }
                
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
                    "description": "Execute Python code via MCP protocol",
                    "endpoints": {
                        "tools": "/tools",
                        "call_tool": "/tools/call"
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
                        }
                    ]
                }
                
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