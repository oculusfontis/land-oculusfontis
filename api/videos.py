import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
CHANNEL = 'UCP8yN6wju8i4lCoADuyZmYw'
SOURCES = [('頻道長片', 'https://www.youtube.com/@OF.Property/videos', False, ''), ('頻道短片', 'https://www.youtube.com/@OF.Property/shorts', True, ''), ('房產防詐', 'https://www.youtube.com/playlist?list=PLDol80VC2x_g', False, '房產防詐'), ('簽約停看聽', 'https://www.youtube.com/playlist?list=PLVE8g3zKOTN0', True, '簽約停看聽')]

def request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'zh-TW,zh;q=0.9'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(6000000).decode('utf-8')

def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)

def text(value):
    if not isinstance(value, dict):
        return ''
    return value.get('simpleText') or ''.join((x.get('text', '') for x in value.get('runs', []))) or value.get('content', '')

def page(source):
    label, url, short, topic = source
    raw = request(url)
    match = re.search('(?:var\\s+)?ytInitialData\\s*=\\s*', raw)
    if not match:
        raise ValueError('YouTube page data absent')
    data, _ = json.JSONDecoder().raw_decode(raw[match.end():])
    rows = []
    for node in walk(data):
        for key in ('videoRenderer', 'playlistVideoRenderer', 'reelItemRenderer', 'shortsLockupViewModel', 'lockupViewModel'):
            v = node.get(key)
            if not isinstance(v, dict):
                continue
            if v.get('isPlayable') is False or v.get('upcomingEventData'):
                continue
            badges = json.dumps(v.get('badges', [])) + json.dumps(v.get('thumbnailOverlays', [])) + json.dumps(v.get('contentImage', {}))
            if any((x in badges for x in ('UPCOMING', 'LIVE_NOW', 'LIVE'))):
                continue
            vid = v.get('videoId') or (v.get('contentId') if v.get('contentType') == 'LOCKUP_CONTENT_TYPE_VIDEO' else None)
            if not vid and key == 'shortsLockupViewModel':
                endpoints = [x.get('reelWatchEndpoint', {}).get('videoId') for x in walk(v)]
                vid = next((x for x in endpoints if x), None)
            title = text(v.get('title', {})) or text(v.get('headline', {}))
            if not title:
                title = text(v.get('overlayMetadata', {}).get('primaryText', {}))
            if not title:
                title = text(v.get('metadata', {}).get('lockupMetadataViewModel', {}).get('title', {}))
            if not vid or not re.fullmatch('[\\w-]{11}', vid) or (not title):
                continue
            if title in ('Private video', 'Deleted video', '私人影片', '已刪除的影片'):
                continue
            is_short = short if not topic else any(('reelWatchEndpoint' in n for n in walk(v)))
            duration = text(v.get('lengthText', {}))
            if not duration:
                duration = next((n['thumbnailBadgeViewModel'].get('text','') for n in walk(v.get('contentImage', {})) if 'thumbnailBadgeViewModel' in n), '')
            rows.append({'id': vid, 'title': title, 'short': is_short, 'topic': topic, 'duration': duration})
    return rows

def feed():
    raw = request('https://www.youtube.com/feeds/videos.xml?channel_id=' + CHANNEL)
    root = ET.fromstring(raw)
    ns = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
    cid = root.findtext('yt:channelId', namespaces=ns)
    if cid not in (CHANNEL, CHANNEL[2:]):
        raise ValueError('Unexpected channel')
    return [{'id': e.findtext('yt:videoId', namespaces=ns), 'title': e.findtext('a:title', namespaces=ns), 'short': False, 'topic': '', 'duration': ''} for e in root.findall('a:entry', ns)]

from http.server import BaseHTTPRequestHandler
import time
_cache = None
_cached_at = 0

def get_payload():
    global _cache, _cached_at
    if _cache is not None and time.time() - _cached_at < 300:
        return _cache
    seed_path = Path(__file__).resolve().parent / 'videos_seed.json'
    seed = json.loads(seed_path.read_text(encoding='utf-8'))
    videos = {v['id']:dict(v) for v in seed}
    failures=[]; successful=[]; discovered={}
    def fetch_source(src):
        try:return src[0],page(src),None
        except Exception:return src[0],[], 'source unavailable'
    with ThreadPoolExecutor(max_workers=4) as pool:
        for label,rows,error in pool.map(fetch_source,SOURCES):
            if error:failures.append(label);continue
            # An empty playlist is valid; an empty channel may indicate a changed page.
            if label.startswith('頻道') and not rows:
                failures.append(label);continue
            successful.append(label)
            for row in rows:
                vid=row['id']
                previous=discovered.get(vid,{})
                row['short']=row['short'] or previous.get('short',False)
                row['topic']=row['topic'] or previous.get('topic','')
                discovered[vid]=row
    for vid,row in discovered.items():
        if vid in videos:
            if row.get('topic'):videos[vid]['topic']=row['topic']
            videos[vid]['short']=row['short'] or videos[vid].get('short',False)
            continue
        category='產權'
        if '繼承' in row['title'] or '遺產' in row['title']:category='繼承'
        elif '都更' in row['title'] or '都市更新' in row['title']:category='都更'
        videos[vid]={**row,'category':category,'description':'','status':'public'}
    payload={'videos':list(videos.values()),'checkedAt':datetime.now(timezone.utc).isoformat(),'sources':successful,'partial':bool(failures),'fallback':not successful}
    # Retain last known successful discovery if all upstream reads fail.
    if not successful and _cache is not None:
        return {**_cache,'fallback':True}
    if successful:
        _cache=payload;_cached_at=time.time()
    return payload

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload=get_payload()
            body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','public, max-age=30, s-maxage=300, stale-while-revalidate=60' if not payload['fallback'] else 'public, max-age=15, s-maxage=30')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(body)
        except Exception:
            self.send_response(503);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b'{"error":"temporarily unavailable"}')
