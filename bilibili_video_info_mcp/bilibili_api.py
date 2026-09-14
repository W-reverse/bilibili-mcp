import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import requests


def get_seesdata() -> str:
    """Get the Bilibili SESSDATA from environment variables"""
    seesdata = os.getenv("SESSDATA")
    if not seesdata:
        raise ValueError("SESSDATA environment variable is required")
    return seesdata

SESSDATA = get_seesdata()


# Bilibili API endpoints
API_GET_VIEW_INFO = "https://api.bilibili.com/x/web-interface/view"
# WBI-path variant of the view endpoint. Used only as a fallback when the
# legacy path is rejected by anti-crawl (HTTP 403/412); same response shape.
API_GET_VIEW_INFO_WBI = "https://api.bilibili.com/x/web-interface/wbi/view"
API_GET_SUBTITLE = "https://api.bilibili.com/x/player/wbi/v2"
API_GET_DANMAKU = "https://api.bilibili.com/x/v1/dm/list.so"
API_GET_COMMENTS = "https://api.bilibili.com/x/v2/reply"

# Finite per-request timeout (seconds) for the requests handled by this fix
# (view/subtitle/danmaku). Not applied to the untouched comments call.
DEFAULT_TIMEOUT = 15
# HTTP statuses from the primary view endpoint that trigger the WBI fallback.
VIEW_FALLBACK_STATUS = (403, 412)

# Default Headers for requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Referer': 'https://www.bilibili.com/'
}

def _get_headers():
    headers = DEFAULT_HEADERS.copy()
    if SESSDATA:
        headers['Cookie'] = f'SESSDATA={SESSDATA}'
    return headers

def _http_status_of(error):
    """Return the HTTP status attached to a requests exception, if any."""
    return getattr(getattr(error, 'response', None), 'status_code', None)

def _resolve_subtitle_url(raw_url):
    """Return an absolute https URL for a subtitle file, or None if unsupported.

    Supports both protocol-relative ("//host/path.json") and absolute https
    URLs. Anything else (missing, http://, other schemes) is rejected.
    """
    if not isinstance(raw_url, str) or not raw_url:
        return None
    if raw_url.startswith('//'):
        candidate = 'https:' + raw_url
    elif raw_url.startswith('https://'):
        candidate = raw_url
    else:
        return None
    parts = urlsplit(candidate)
    if parts.scheme != 'https' or not parts.netloc:
        return None
    return candidate

def extract_bvid_and_page(url):
    """Extract BV number and page number from URL.
    
    Returns:
        tuple: (bvid, page_number) where page_number defaults to 1
    """
    final_url = url
    
    # 如果是短链接（如b23.tv），则跟踪重定向获取完整URL
    if 'b23.tv' in url:
        try:
            response = requests.head(url, headers=_get_headers(), allow_redirects=True, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                final_url = response.url
        except requests.RequestException as e:
            print(f"Error resolving short URL: {e}")
    
    # 提取 BV 号
    bvid_match = re.search(r'BV[a-zA-Z0-9_]+', final_url)
    bvid = bvid_match.group(0) if bvid_match else None
    
    # 提取 p 参数（分P页码），默认为 1
    # 支持 &p=, ?p=, &amp;p= (HTML编码) 等格式
    page_match = re.search(r'[?&]p=(\d+)|&amp;p=(\d+)', final_url)
    if page_match:
        page = int(page_match.group(1) or page_match.group(2))
    else:
        page = 1
    
    return bvid, page


def extract_bvid(url):
    """Extract BV number from URL (backward compatible)."""
    bvid, _ = extract_bvid_and_page(url)
    return bvid

def get_video_basic_info(bvid, page=1):
    """Gets aid and cid for a given bvid and page number.

    The primary ``/x/web-interface/view`` endpoint is tried first. When it is
    rejected by anti-crawl with HTTP 403/412, the same request is retried once
    against the WBI-path variant, which returns an identical response shape
    (so aid/cid/pages are read the same way).
    
    Args:
        bvid: The BV number of the video
        page: The page number (1-indexed), defaults to 1
        
    Returns:
        tuple: (aid, cid, error)
    """
    headers = _get_headers()
    params_view = {'bvid': bvid}
    used_view_url = API_GET_VIEW_INFO
    try:
        response_view = requests.get(API_GET_VIEW_INFO, params=params_view, headers=headers, timeout=DEFAULT_TIMEOUT)
        if response_view.status_code in VIEW_FALLBACK_STATUS:
            used_view_url = API_GET_VIEW_INFO_WBI
            response_view = requests.get(API_GET_VIEW_INFO_WBI, params=params_view, headers=headers, timeout=DEFAULT_TIMEOUT)
        response_view.raise_for_status()
        data_view = response_view.json()
    except requests.RequestException as e:
        status = _http_status_of(e)
        detail = f'HTTP {status}' if status is not None else type(e).__name__
        return None, None, {'error': f'Failed to fetch video details from {used_view_url}: {detail}'}
    except ValueError:
        return None, None, {'error': f'Failed to parse video info from {used_view_url}'}

    if not isinstance(data_view, dict):
        return None, None, {'error': f'Unexpected video info response from {used_view_url}'}
    if data_view.get('code') != 0:
        return None, None, {'error': 'Failed to get video info', 'details': data_view}

    video_data = data_view.get('data')
    if not isinstance(video_data, dict):
        return None, None, {'error': f'Unexpected video info data from {used_view_url}'}

    aid = video_data.get('aid')

    # 获取分P列表，找到对应页码的 cid
    pages = video_data.get('pages')
    cid = None
    if pages is None:
        # 没有分P信息，使用默认 cid
        cid = video_data.get('cid')
    elif not isinstance(pages, list):
        return None, None, {'error': f'Unexpected pages format from {used_view_url}'}
    elif 1 <= page <= len(pages):
        entry = pages[page - 1]
        if not isinstance(entry, dict):
            return None, None, {'error': f'Unexpected page entry from {used_view_url}'}
        cid = entry.get('cid')
    else:
        # 页码超出范围，使用默认 cid
        cid = video_data.get('cid')

    if aid is None or cid is None:
        return None, None, {'error': f'Missing aid/cid in response from {used_view_url}'}

    return aid, cid, None

def get_subtitles(aid, cid):
    """Fetches subtitles for a given aid and cid."""
    headers = _get_headers()
    try:
        params_subtitle = {'aid': aid, 'cid': cid}
        response_subtitle = requests.get(API_GET_SUBTITLE, params=params_subtitle, headers=headers, timeout=DEFAULT_TIMEOUT)
        response_subtitle.raise_for_status()
        subtitle_data = response_subtitle.json()
    except requests.RequestException as e:
        status = _http_status_of(e)
        detail = f'HTTP {status}' if status is not None else type(e).__name__
        return [], {'error': f'Could not fetch subtitles from {API_GET_SUBTITLE}: {detail}'}
    except ValueError:
        return [], {'error': f'Failed to parse subtitle metadata from {API_GET_SUBTITLE}'}

    if not isinstance(subtitle_data, dict) or subtitle_data.get('code') != 0:
        # 业务错误与"没有字幕"必须区分
        return [], {'error': f'Failed to get subtitle info from {API_GET_SUBTITLE}'}

    data = subtitle_data.get('data')
    if data is None:
        return [], None
    if not isinstance(data, dict):
        return [], {'error': f'Unexpected subtitle data from {API_GET_SUBTITLE}'}

    subtitle = data.get('subtitle')
    if subtitle is None:
        return [], None
    if not isinstance(subtitle, dict):
        return [], {'error': f'Unexpected subtitle metadata from {API_GET_SUBTITLE}'}

    subtitle_meta = subtitle.get('subtitles')
    if subtitle_meta is None or subtitle_meta == []:
        return [], None
    if not isinstance(subtitle_meta, list):
        return [], {'error': f'Unexpected subtitle metadata from {API_GET_SUBTITLE}'}

    subtitles = []
    for sub_meta in subtitle_meta:
        if not isinstance(sub_meta, dict):
            return [], {'error': f'Unexpected subtitle metadata from {API_GET_SUBTITLE}'}
        subtitle_json_url = _resolve_subtitle_url(sub_meta.get('subtitle_url'))
        if subtitle_json_url is None:
            # 有字幕条目但 URL 缺失/不受支持：明确报错，绝不静默当作"无字幕"。
            return [], {'error': f'Unsupported subtitle URL from {API_GET_SUBTITLE}'}
        try:
            # 绝不把账号 Cookie(SESSDATA) 发送给（可能第三方的）字幕主机。
            response_sub_content = requests.get(
                subtitle_json_url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            response_sub_content.raise_for_status()
            sub_content = response_sub_content.json()
        except requests.RequestException:
            # 不回显带签名的 URL，也不输出响应内容。
            return [], {'error': 'Failed to fetch subtitle content'}
        except ValueError:
            return [], {'error': 'Failed to parse subtitle content'}

        if not isinstance(sub_content, dict) or not isinstance(sub_content.get('body'), list):
            return [], {'error': 'Unexpected subtitle content format'}
        content_list = []
        for item in sub_content['body']:
            if not isinstance(item, dict):
                return [], {'error': 'Unexpected subtitle content format'}
            content_list.append(item.get('content', ''))
        subtitles.append({
            'lan': sub_meta.get('lan', 'unknown'),
            'content': content_list
        })

    return subtitles, None

def get_danmaku(cid):
    """Fetches danmaku for a given cid."""
    headers = _get_headers()
    danmaku_list = []
    try:
        params_danmaku = {'oid': cid}
        response_danmaku = requests.get(API_GET_DANMAKU, params=params_danmaku, headers=headers, timeout=DEFAULT_TIMEOUT)
        # 风控/错误响应（如 412 HTML 页）必须暴露为错误，
        # 绝不能因为解析失败而被当成"该视频没有弹幕"。
        response_danmaku.raise_for_status()
        danmaku_content = response_danmaku.content.decode('utf-8', errors='ignore')
        root = ET.fromstring(danmaku_content)
        if root.tag != 'i':
            return [], {'error': f'Unexpected danmaku response from {API_GET_DANMAKU}'}
        for d in root.findall('d'):
            danmaku_list.append(d.text)
        return danmaku_list, None
    except requests.RequestException as e:
        status = _http_status_of(e)
        detail = f'HTTP {status}' if status is not None else type(e).__name__
        return [], {'error': f'Failed to get danmaku from {API_GET_DANMAKU}: {detail}'}
    except ET.ParseError:
        return [], {'error': f'Failed to parse danmaku response from {API_GET_DANMAKU}'}

def get_comments(aid):
    """Fetches comments for a given aid."""
    headers = _get_headers()
    comments_list = []
    try:
        params_comments = {'type': 1, 'oid': aid, 'sort': 2}  # sort=2 fetches hot comments
        response_comments = requests.get(API_GET_COMMENTS, params=params_comments, headers=headers)
        response_comments.raise_for_status()
        comments_data = response_comments.json()
        
        if comments_data.get('code') == 0 and comments_data.get('data', {}).get('replies'):
            for comment in comments_data['data']['replies']:
                if comment.get('content', {}).get('message'):
                    comments_list.append({
                        'user': comment.get('member', {}).get('uname', 'Unknown User'),
                        'content': comment['content']['message'],
                        'likes': comment.get('like', 0)
                    })
        return comments_list, None
    except requests.RequestException as e:
        return [], {'error': f'Failed to get comments: {e}'}
