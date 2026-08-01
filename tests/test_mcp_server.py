import asyncio
import importlib
import json
import os
import subprocess
import sys


def test_main_module_import_does_not_start_server(monkeypatch):
    monkeypatch.setenv("SESSDATA", "test-session")

    module = importlib.import_module("bilibili_video_info_mcp.__main__")

    assert callable(module.main)


def test_server_registers_expected_tools(monkeypatch):
    monkeypatch.setenv("SESSDATA", "test-session")
    server_module = importlib.import_module("bilibili_video_info_mcp.server")

    tools = asyncio.run(server_module.mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "get_subtitles",
        "get_danmaku",
        "get_comments",
    }


def test_stdio_supports_mcphub_protocol_version():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "compatibility-test", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    input_data = "".join(f"{json.dumps(request)}\n" for request in requests)
    env = os.environ | {"SESSDATA": "test-session"}

    result = subprocess.run(
        [sys.executable, "-m", "bilibili_video_info_mcp"],
        input=input_data,
        text=True,
        capture_output=True,
        timeout=10,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {tool["name"] for tool in responses[1]["result"]["tools"]} == {
        "get_subtitles",
        "get_danmaku",
        "get_comments",
    }
