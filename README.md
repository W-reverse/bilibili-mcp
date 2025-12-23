# MCP Server for Bilibili Video Info

[![English](https://img.shields.io/badge/language-English-blue.svg)](./README.md) [![中文](https://img.shields.io/badge/language-中文-red.svg)](./README.zh.md)

A Bilibili MCP Server that can retrieve subtitles, danmaku (bullet comments), and comments information from videos using the video URL.

> This is a fork of [lesir831/bilibili-video-info-mcp](https://github.com/lesir831/bilibili-video-info-mcp) with added support for multi-part videos (分P视频).

## Usage

This MCP server supports three transport methods:
1. **stdio** 

**Install from GitHub:**
```json
{
    "mcpServers": {
        "bilibili-video-info-mcp": {
            "command": "uvx",
            "args": [
                "--from", "git+https://github.com/W-reverse/bilibili-video-info-mcp.git",
                "bilibili-video-info-mcp"
            ],
            "env": {
                "SESSDATA": "your valid sessdata"
            }
        }
    }
}
```

2. **sse** (Server-Sent Events)
run bilibili-video-info-mcp in sse mode
``` bash
cp .env.example .env
uvx run --env .env bilibili-video-info-mcp sse
```
then config your mcp client
```json
{
    "mcpServers": {
        "bilibili-video-info-mcp": {
            "url": "http://{your.ip.address}:$PORT$/sse"
        }
    }
}
```

3. **streamable-http** (HTTP Streaming)
run bilibili-video-info-mcp in streamable-http mode
``` bash
cp .env.example .env
uvx run --env .env bilibili-video-info-mcp streamable-http
```
then config your mcp client
```json
{
    "mcpServers": {
        "bilibili-video-info-mcp": {
            "url": "http://{your.ip.address}:$PORT$/mcp"
            }
        }
    }
}
```

## MCP Tools List

All tools support a `page` parameter to specify the page number for multi-part videos. This solves the issue where some LLM clients may truncate URLs, causing incorrect retrieval of multi-part video content.

### 1. Get Video Subtitles

```json
{
  "name": "get_subtitles",
  "arguments": {
    "url": "https://www.bilibili.com/video/BV1x341177NN",
    "page": 1
  }
}
```

Get subtitles for part 2 of a multi-part video:
```json
{
  "name": "get_subtitles",
  "arguments": {
    "url": "https://www.bilibili.com/video/BV1x341177NN",
    "page": 2
  }
}
```

### 2. Get Video Danmaku (Bullet Comments)

```json
{
  "name": "get_danmaku",
  "arguments": {
    "url": "https://www.bilibili.com/video/BV1x341177NN",
    "page": 1
  }
}
```

### 3. Get Video Comments

```json
{
  "name": "get_comments",
  "arguments": {
    "url": "https://www.bilibili.com/video/BV1x341177NN",
    "page": 1
  }
}
```

### Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| url | string | Yes | - | Bilibili video URL |
| page | int | No | 1 | Page number for multi-part videos. Takes priority over URL's p parameter |

## FAQ

### 1. How to find SESSDATA?

1. Log in to the Bilibili website
2. Open browser developer tools (F12)
3. Go to Application/Storage -> Cookies
4. Find the value corresponding to SESSDATA

### 2. Error "SESSDATA environment variable is required"

Make sure you have set the environment variable:

```bash
export SESSDATA="your SESSDATA value"
```

### 3. What video link formats are supported?

Standard Bilibili video links are supported, such as:
- https://www.bilibili.com/video/BV1x341177NN
- https://www.bilibili.com/video/BV1x341177NN?p=2 (multi-part videos)
- https://b23.tv/xxxxx (short links)
- Any link containing a BV number
