"""
Bilibili视频信息MCP服务器的核心模块
"""

from mcp.server.fastmcp import FastMCP
from . import bilibili_api

# 创建 FastMCP 服务器实例，命名为 BilibiliVideoInfo
mcp = FastMCP("BilibiliVideoInfo", dependencies=["requests"])

@mcp.tool(
    annotations={
        "title": "获取视频字幕",
        "readOnlyHint": True,
        "openWorldHint": False
    }
)
async def get_subtitles(url: str, page: int = 1) -> list:
    """Get subtitles from a Bilibili video

    Args:
        url: Bilibili video URL. IMPORTANT: Must include the complete URL with all query parameters.
             Example: https://www.bilibili.com/video/BV1x341177NN?p=2
        page: Page number for multi-part videos (分P视频). Defaults to 1.
              If the URL contains p= parameter, this argument takes priority.
              For example, if you want to get subtitles for part 2, set page=2.

    Returns:
        List of subtitles grouped by language. Each entry contains subtitle content with timestamps.
    """
    bvid, url_page = bilibili_api.extract_bvid_and_page(url)
    if not bvid:
        return [f"错误: 无法从 URL 提取 BV 号: {url}"]

    # 优先使用显式传入的 page 参数，否则使用从 URL 提取的页码
    final_page = page if page != 1 else url_page

    aid, cid, error = bilibili_api.get_video_basic_info(bvid, final_page)
    if error:
        return [f"获取视频信息失败: {error['error']}"]

    subtitles, error = bilibili_api.get_subtitles(aid, cid)
    if error:
        return [f"获取字幕失败: {error['error']}"]

    if not subtitles:
        return ["该视频没有字幕"]

    return subtitles

@mcp.tool(
    annotations={
        "title": "获取视频弹幕",
        "readOnlyHint": True,
        "openWorldHint": False
    }
)
async def get_danmaku(url: str, page: int = 1) -> list:
    """Get danmaku (bullet comments) from a Bilibili video

    Args:
        url: Bilibili video URL. IMPORTANT: Must include the complete URL with all query parameters.
             Example: https://www.bilibili.com/video/BV1x341177NN?p=2
        page: Page number for multi-part videos (分P视频). Defaults to 1.
              If the URL contains p= parameter, this argument takes priority.
              For example, if you want to get danmaku for part 2, set page=2.

    Returns:
        List of danmaku (bullet comments) with content, timestamp and user information
    """
    bvid, url_page = bilibili_api.extract_bvid_and_page(url)
    if not bvid:
        return [f"错误: 无法从 URL 提取 BV 号: {url}"]

    # 优先使用显式传入的 page 参数，否则使用从 URL 提取的页码
    final_page = page if page != 1 else url_page

    aid, cid, error = bilibili_api.get_video_basic_info(bvid, final_page)
    if error:
        return [f"获取视频信息失败: {error['error']}"]

    danmaku, error = bilibili_api.get_danmaku(cid)
    if error:
        return [f"获取弹幕失败: {error['error']}"]

    if not danmaku:
        return ["该视频没有弹幕"]

    return danmaku

@mcp.tool(
    annotations={
        "title": "获取视频评论",
        "readOnlyHint": True,
        "openWorldHint": False
    }
)
async def get_comments(url: str, page: int = 1) -> list:
    """Get popular comments from a Bilibili video

    Args:
        url: Bilibili video URL. IMPORTANT: Must include the complete URL with all query parameters.
             Example: https://www.bilibili.com/video/BV1x341177NN?p=2
        page: Page number for multi-part videos (分P视频). Defaults to 1.
              Note: Comments are typically shared across all parts of a video.

    Returns:
        List of popular comments including comment content, user information, and metadata such as like counts
    """
    bvid, url_page = bilibili_api.extract_bvid_and_page(url)
    if not bvid:
        return [f"错误: 无法从 URL 提取 BV 号: {url}"]

    # 优先使用显式传入的 page 参数，否则使用从 URL 提取的页码
    final_page = page if page != 1 else url_page

    aid, cid, error = bilibili_api.get_video_basic_info(bvid, final_page)
    if error:
        return [f"获取视频信息失败: {error['error']}"]

    comments, error = bilibili_api.get_comments(aid)
    if error:
        return [f"获取评论失败: {error['error']}"]

    if not comments:
        return ["该视频没有热门评论"]

    return comments

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bilibili Video Info MCP Server")
    parser.add_argument('transport', nargs='?', default='stdio', choices=['stdio', 'sse', 'streamable-http'],
                        help='Transport type (stdio, sse, or streamable-http)')
    args = parser.parse_args()
    mcp.run(transport=args.transport)