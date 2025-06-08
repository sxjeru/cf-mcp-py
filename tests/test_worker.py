import os
import signal
import socket
import subprocess
import time
import json

import pytest
import requests


def get_free_port():
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


class WorkerFixture:
    def __init__(self):
        self.process = None
        self.port = None
        self.base_url = None

    def start(self):
        """Start the worker in a subprocess."""
        self.port = get_free_port()
        self.base_url = f"http://localhost:{self.port}"

        # Start the worker as a subprocess
        cmd = f"npx wrangler@latest dev --port {self.port}"
        self.process = subprocess.Popen(
            cmd,
            shell=True,
            preexec_fn=os.setsid,  # So we can kill the process group later
        )

        # Wait for server to start
        self._wait_for_server()
        return self

    def _wait_for_server(self, max_retries=10, retry_interval=1):
        """Wait until the server is responding to requests."""
        for _ in range(max_retries):
            try:
                response = requests.get(self.base_url, timeout=20)
                if response.status_code < 500:
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(retry_interval)

        self.stop()
        raise Exception(f"worker failed to start on port {self.port}")

    def stop(self):
        """Stop the worker."""
        if self.process:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process = None


@pytest.fixture(scope="session")
def web_server():
    """Pytest fixture that starts the worker for the entire test session."""
    server = WorkerFixture()
    server.start()
    yield server
    server.stop()


def test_root_endpoint(web_server):
    """Test that the root endpoint returns server info."""
    response = requests.get(web_server.base_url)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Python Code Executor MCP Server"
    assert "streaming_formats" in data


def test_list_tools(web_server):
    """Test that we can list available tools."""
    response = requests.get(f"{web_server.base_url}/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 1
    assert data["tools"][0]["name"] == "execute_python"


def test_execute_python_simple(web_server):
    """Test executing simple Python code."""
    payload = {
        "name": "execute_python",
        "arguments": {
            "code": "print('Hello, World!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')"
        }
    }
    
    response = requests.post(f"{web_server.base_url}/tools/call", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) == 1
    assert "Hello, World!" in data["content"][0]["text"]
    assert "2 + 2 = 4" in data["content"][0]["text"]


def test_execute_python_streaming(web_server):
    """Test executing Python code with streaming enabled."""
    payload = {
        "name": "execute_python",
        "arguments": {
            "code": "print('Hello, Streaming World!')\nfor i in range(3):\n    print(f'Count: {i}')",
            "stream": True
        }
    }
    
    response = requests.post(f"{web_server.base_url}/tools/call", json=payload, stream=True)
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/x-ndjson"
    
    # 解析流式响应
    lines = []
    for line in response.iter_lines():
        if line:
            lines.append(json.loads(line.decode('utf-8')))
    
    # 验证流式响应结构
    assert len(lines) >= 2  # 至少有开始和完成信号
    assert lines[0]["type"] == "execution_start"
    assert lines[-1]["type"] == "execution_complete"
    assert lines[-1]["success"] is True


def test_stream_execute_endpoint(web_server):
    """Test the dedicated streaming execution endpoint."""
    payload = {
        "code": "print('Direct streaming test')\nprint('Line 2')"
    }
    
    response = requests.post(f"{web_server.base_url}/stream/execute", json=payload, stream=True)
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/x-ndjson"
    
    lines = []
    for line in response.iter_lines():
        if line:
            lines.append(json.loads(line.decode('utf-8')))
    
    # 查找输出内容
    stdout_found = False
    for line in lines:
        if line.get("type") == "stdout":
            assert "Direct streaming test" in line["content"]
            stdout_found = True
            break
    
    assert stdout_found


def test_execute_python_with_error_streaming(web_server):
    """Test executing Python code that raises an error with streaming."""
    payload = {
        "name": "execute_python",
        "arguments": {
            "code": "print('Before error')\nraise ValueError('Test streaming error')",
            "stream": True
        }
    }
    
    response = requests.post(f"{web_server.base_url}/tools/call", json=payload, stream=True)
    assert response.status_code == 200
    
    lines = []
    for line in response.iter_lines():
        if line:
            lines.append(json.loads(line.decode('utf-8')))
    
    # 验证错误处理
    assert lines[-1]["type"] == "execution_complete"
    assert lines[-1]["success"] is False
    
    # 查找错误信息
    error_found = False
    for line in lines:
        if line.get("type") == "error":
            assert "ValueError" in line["error_type"]
            assert "Test streaming error" in line["error_message"]
            error_found = True
            break
    
    assert error_found


def test_persistent_stream_endpoint(web_server):
    """Test the persistent streaming endpoint."""
    response = requests.get(f"{web_server.base_url}/stream/persistent", stream=True, timeout=3)
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/x-ndjson"
    
    lines = []
    try:
        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode('utf-8'))
                lines.append(data)
                if len(lines) >= 2:  # 获取连接建立和至少一个心跳
                    break
    except requests.exceptions.ReadTimeout:
        pass  # 预期的超时
    
    assert len(lines) >= 1
    assert lines[0]["type"] == "connection_established"