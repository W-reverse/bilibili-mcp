import asyncio
import importlib
import json
import os
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


def test_subtitle_tool_uses_pagelist_fallback_and_url_page(monkeypatch):
    monkeypatch.setenv("SESSDATA", "test-session")
    server_module = importlib.import_module("bilibili_video_info_mcp.server")
    api = server_module.bilibili_api

    def get(url, params=None, headers=None, timeout=None):
        import requests

        response = requests.Response()
        response.status_code = 200
        payload = {}
        if url in (api.API_GET_VIEW_INFO, api.API_GET_VIEW_INFO_WBI):
            response.status_code = 412
        elif url == api.API_GET_PAGELIST:
            payload = {"code": 0, "data": [{"cid": 100}, {"cid": 200}]}
        elif url == api.API_GET_SUBTITLE:
            assert params["cid"] == 200
            payload = {"code": 0, "data": {
                "aid": 7,
                "subtitle": {"subtitles": [{"lan": "zh", "subtitle_url": "//subtitle.example/test.json"}]},
            }}
        else:
            assert url == "https://subtitle.example/test.json"
            assert "Cookie" not in headers
            payload = {"body": [{"content": "second part subtitle"}]}
        response._content = json.dumps(payload).encode()
        return response

    monkeypatch.setattr(api.requests, "get", get)
    result = asyncio.run(server_module.get_subtitles("https://www.bilibili.com/video/BVTEST?p=2"))
    assert result == [{"lan": "zh", "content": ["second part subtitle"]}]


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
    env = os.environ | {"SESSDATA": "test-session"}

    async def exchange():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "bilibili_video_info_mcp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            responses = []
            for request in requests:
                process.stdin.write((json.dumps(request) + "\n").encode())
                await process.stdin.drain()
                if "id" in request:
                    # Keep stdin open until the asynchronous response arrives.
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
                    assert line, "MCP server exited before responding"
                    responses.append(json.loads(line))
            process.stdin.close()
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            assert process.returncode == 0, stderr.decode()
            return responses
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    responses = asyncio.run(exchange())
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {tool["name"] for tool in responses[1]["result"]["tools"]} == {
        "get_subtitles",
        "get_danmaku",
        "get_comments",
    }
