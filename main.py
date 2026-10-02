# ============================================================
# NirobX VIP Hub - Professional Single-File Edition
# Uses xhamster_api + eaf_base_api (with fallback scraper)
# Admin: /admin  |  user: admin  |  pass: nirobxcodx
# ============================================================

from __future__ import annotations
import os
import re
import json
import secrets
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Query, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
from curl_cffi.requests import AsyncSession
from selectolax.lexbor import LexborHTMLParser
import chompjs

# ---- Optional xhamster_api ----
try:
    from xhamster_api import Client
    from base_api.modules.config import RuntimeConfig
    from base_api import BaseCore
    HAS_API = True
except ImportError:
    HAS_API = False
    print("WARNING: xhamster_api not installed. Using fallback scraper.")

# ============================================================
# STORAGE
# ============================================================
DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
CFG_F = DATA / "config.json"
VIS_F = DATA / "visitors.json"
UPL_F = DATA / "uploads.json"
LIK_F = DATA / "likes.json"
BLK_F = DATA / "blocked.json"

DEFAULT = {
    "site_name": "NirobX VIP Hub",
    "site_tagline": "Premium 4K Adult Streaming",
    "primary": "#e91e63",
    "accent": "#ff5722",
    "maintenance": False,
    "maint_msg": "সাইট সাময়িক বন্ধ। শীঘ্রই ফিরে আসছি।",
    "popup": True,
    "popup_title": "Welcome to NirobX VIP",
    "popup_msg": "18+ Only. Enjoy premium content.",
    "likes_on": True,
    "reacts_on": True,
    "owner": "@NIROB_BBZ",
    "channel": "https://t.me/SPEED_X_OFFICIAL1",
    "views": 0
}

def load(p, d):
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            pass
    return d

def save(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")

cfg = load(CFG_F, DEFAULT)
visitors = load(VIS_F, [])
uploads = load(UPL_F, [])
likes = load(LIK_F, {})
blocked = load(BLK_F, [])

# ============================================================
# FALLBACK SCRAPER
# ============================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://xhamster.com/"
}

async def fetch(url: str) -> str:
    async with AsyncSession(impersonate="chrome120") as s:
        r = await s.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Status {r.status_code}")
        return r.text

def parse_search(html: str) -> List[Dict]:
    parser = LexborHTMLParser(html)
    results, seen = [], set()
    for sel in [
        'div[data-role="video-section-content-role"]',
        'div[data-role="main-search-content"]',
        'div[data-role="video-section-container"]',
        "div.thumb-list",
        "div.mixed-section"
    ]:
        for cont in parser.css(sel):
            for card in cont.css(".video-thumb[data-video-id], div.thumb-list__item, div.video-thumb"):
                a = (
                    card.css_first('a[data-role="thumb-link"]') or
                    card.css_first("a.video-thumb__image-container") or
                    card.css_first("a[href*='/videos/']")
                )
                if not a:
                    continue
                href = a.attributes.get("href", "")
                if not href or "/videos/" not in href:
                    continue
                if not href.startswith("http"):
                    href = "https://xhamster.com" + href
                if href in seen:
                    continue
                seen.add(href)

                title = (
                    a.attributes.get("aria-label") or
                    a.attributes.get("title") or
                    (card.css_first("a.video-thumb-info__name, .video-thumb__title") or a).text(strip=True) or
                    "NirobX"
                )

                img = card.css_first('img[data-role="thumb-preview-img"]') or card.css_first("img")
                thumb = ""
                if img:
                    thumb = (
                        img.attributes.get("src") or
                        img.attributes.get("data-src") or
                        img.attributes.get("data-thumb") or
                        ""
                    )
                    if thumb.startswith("//"):
                        thumb = "https:" + thumb
                    elif thumb and not thumb.startswith("http"):
                        thumb = "https://xhamster.com" + thumb

                dur = card.css_first('[data-role="video-duration"]') or card.css_first(".video-thumb__duration")
                duration = dur.text(strip=True) if dur else "HD"

                views_el = card.css_first(".video-thumb__views, [data-qa='views']")
                views = views_el.text(strip=True) if views_el else "—"

                up = card.css_first("a[href*='/users/'], a[href*='/channels/']")
                uploader = up.text(strip=True) if up else "Creator"

                results.append({
                    "title": title[:120],
                    "url": href,
                    "thumbnail": thumb,
                    "duration": duration,
                    "views": views,
                    "uploader_name": uploader,
                    "uploader_avatar": f"https://api.dicebear.com/7.x/bottts/svg?seed={urllib.parse.quote(uploader)}",
                    "rating": "98%"
                })
    return results

def parse_video(html: str) -> Dict:
    parser = LexborHTMLParser(html)
    script = parser.css_first("script#initials-script")
    title = "NirobX"
    m3u8 = ""
    dl = ""
    thumb = ""
    uploader = "Creator"
    avatar = ""
    views = "—"
    rating = "98%"
    tags = []

    if script and "window.initials=" in (script.text() or ""):
        try:
            js = script.text().split("window.initials=", 1)[-1].strip().rstrip(";")
            data = chompjs.parse_js_object(js)
            vm = data.get("videoModel", {})
            title = vm.get("title") or data.get("pageTitle", title)
            views = f"{vm.get('views', 0):,} views"
            xp = data.get("xplayerSettings", {}).get("sources", {})
            hls = xp.get("standard", {}).get("hls", {})
            if isinstance(hls, dict):
                m3u8 = hls.get("url") or hls.get("fallback") or ""
            mp4 = xp.get("standard", {}).get("mp4", {}) or xp.get("mp4", {})
            if isinstance(mp4, dict) and mp4:
                for q in ["1080p", "720p", "480p"]:
                    if q in mp4:
                        dl = mp4[q]
                        break
                if not dl:
                    dl = next(iter(mp4.values()), "")
            thumb = vm.get("thumbURL", "")
            auth = vm.get("author", {})
            uploader = auth.get("name", uploader)
            avatar = auth.get("thumbURL") or auth.get("avatar", "")
            if avatar.startswith("//"):
                avatar = "https:" + avatar
            rating = f"{vm.get('rating', {}).get('percent', 98)}%"
            tags = [c.get("name") for c in vm.get("categories", []) if isinstance(c, dict)][:12]
        except Exception:
            pass

    if not m3u8:
        m = re.search(r'https?:\\?/\\?/[^"\s]+\.m3u8[^"\s]*', html)
        if m:
            m3u8 = m.group(0).replace("\\/", "/")
    if not dl:
        dl = m3u8
    if not avatar:
        avatar = f"https://api.dicebear.com/7.x/bottts/svg?seed={urllib.parse.quote(uploader)}"

    return {
        "title": title,
        "m3u8_base_url": m3u8,
        "download_url": dl,
        "thumbnail": thumb,
        "uploader_name": uploader,
        "uploader_avatar": avatar,
        "views": views,
        "rating_percentage": rating,
        "tags": tags
    }

# ============================================================
# API CLIENT
# ============================================================
xh_client = None
if HAS_API:
    try:
        conf = RuntimeConfig()
        conf.request_attempts = 3
        core = BaseCore(configuration=conf)
        xh_client = Client(core=core)
    except Exception as e:
        print("API init failed:", e)
        HAS_API = False

# ============================================================
# APP
# ============================================================
app = FastAPI(title="NirobX VIP Hub")
sec = HTTPBasic()

def admin_auth(c: HTTPBasicCredentials = Depends(sec)):
    if not (c.username == "admin" and secrets.compare_digest(c.password, "nirobxcodx")):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return True

@app.middleware("http")
async def track(req: Request, call_next):
    ip = req.client.host if req.client else "0.0.0.0"
    if ip in blocked:
        return HTMLResponse("<h1>IP Blocked</h1>", 403)
    if not req.url.path.startswith(("/admin", "/api/")):
        visitors.append({
            "ip": ip,
            "path": str(req.url.path),
            "time": datetime.now().isoformat()
        })
        if len(visitors) > 4000:
            visitors.pop(0)
        save(VIS_F, visitors)
        cfg["views"] = cfg.get("views", 0) + 1
        save(CFG_F, cfg)
    return await call_next(req)

# ============================================================
# FRONTEND
# ============================================================
def ui():
    c = cfg
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{c['site_name']} | VIP</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
tailwind.config = {{
  darkMode: 'class',
  theme: {{
    extend: {{
      colors: {{
        nx: {{
          bg: '#0a0a0c',
          card: '#141418',
          border: '#25252b',
          p: '{c["primary"]}',
          a: '{c["accent"]}'
        }}
      }}
    }}
  }}
}}
</script>
<style>
body {{ background: #0a0a0c; }}
.glass {{ background: rgba(20,20,24,.94); backdrop-filter: blur(14px); }}
.thumb {{ aspect-ratio: 16/9; object-fit: cover; }}
.clamp {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
::-webkit-scrollbar {{ width: 5px; height: 5px; }}
::-webkit-scrollbar-thumb {{ background: {c['primary']}; border-radius: 10px; }}
</style>
</head>
<body class="bg-nx-bg text-gray-100 min-h-screen flex flex-col font-sans">

<!-- AGE GATE -->
<div id="age" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/95 p-4">
  <div class="bg-nx-card border border-nx-border rounded-2xl max-w-md w-full p-6 text-center">
    <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-nx-p to-nx-a flex items-center justify-center text-2xl font-black">18+</div>
    <h2 class="text-xl font-bold mb-2">Age Verification</h2>
    <p class="text-sm text-zinc-400 mb-6">Adult content. You must be 18+.</p>
    <div class="flex gap-3">
      <button onclick="age(true)" class="flex-1 py-3 rounded-xl bg-nx-p font-bold">I am 18+</button>
      <button onclick="age(false)" class="flex-1 py-3 rounded-xl bg-zinc-800 font-bold">Exit</button>
    </div>
  </div>
</div>

<!-- POPUP -->
<div id="pop" class="hidden fixed inset-0 z-[90] flex items-center justify-center bg-black/80 p-4">
  <div class="bg-nx-card border border-nx-p/40 rounded-2xl max-w-md w-full p-6 relative">
    <button onclick="document.getElementById('pop').classList.add('hidden')" class="absolute top-3 right-3 text-zinc-400">
      <i class="fa-solid fa-xmark"></i>
    </button>
    <h3 id="pt" class="text-lg font-bold mb-2"></h3>
    <p id="pm" class="text-sm text-zinc-400 mb-4"></p>
    <button onclick="document.getElementById('pop').classList.add('hidden')" class="w-full py-2.5 rounded-xl bg-nx-p font-bold">OK</button>
  </div>
</div>

<!-- HEADER -->
<header class="sticky top-0 z-50 glass border-b border-nx-border">
  <div class="container mx-auto px-3 md:px-5 py-3 flex items-center gap-3">
    <button onclick="menu()" class="md:hidden p-2"><i class="fa-solid fa-bars text-xl"></i></button>
    <a href="/" class="flex items-center gap-2 shrink-0">
      <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-nx-p to-nx-a flex items-center justify-center font-black text-white text-sm">NX</div>
      <div class="hidden sm:block leading-tight">
        <div class="font-bold">{c['site_name']}</div>
        <div class="text-[10px] text-zinc-500">{c['site_tagline']}</div>
      </div>
    </a>
    <div class="flex-1 max-w-xl">
      <div class="relative">
        <input id="q" type="text" placeholder="Search 4K, creators..." 
               class="w-full bg-zinc-900/80 border border-nx-border rounded-full py-2.5 pl-4 pr-12 text-sm focus:outline-none focus:border-nx-p">
        <button onclick="search(1)" class="absolute right-1.5 top-1.5 bottom-1.5 px-3 rounded-full bg-nx-p text-white text-sm">
          <i class="fa-solid fa-magnifying-glass"></i>
        </button>
      </div>
    </div>
    <button onclick="hist()" class="p-2.5 rounded-full hover:bg-zinc-800" title="History"><i class="fa-solid fa-clock-rotate-left"></i></button>
    <button onclick="marks()" class="p-2.5 rounded-full hover:bg-zinc-800" title="Bookmarks"><i class="fa-solid fa-bookmark"></i></button>
  </div>
</header>

<!-- SIDE MENU -->
<div id="side" class="fixed inset-y-0 left-0 z-50 w-72 bg-nx-card border-r border-nx-border -translate-x-full transition-transform duration-300 flex flex-col">
  <div class="p-4 border-b border-nx-border flex justify-between items-center">
    <span class="font-bold">{c['site_name']}</span>
    <button onclick="menu()"><i class="fa-solid fa-xmark text-xl"></i></button>
  </div>
  <div class="flex-1 overflow-y-auto p-3 space-y-1 text-sm">
    <button onclick="go('trending');menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-fire text-nx-p w-5"></i>Trending
    </button>
    <button onclick="go('newest');menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-bolt text-nx-a w-5"></i>Newest
    </button>
    <button onclick="go('best');menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-thumbs-up text-green-400 w-5"></i>Best
    </button>
    <button onclick="go('hd');menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-hd text-blue-400 w-5"></i>HD
    </button>
    <button onclick="go('4k');menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-tv text-purple-400 w-5"></i>4K
    </button>
    <button onclick="viral();menu()" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-solid fa-virus text-red-400 w-5"></i>Viral
    </button>
    <hr class="border-nx-border my-2">
    <a href="{c['channel']}" target="_blank" class="w-full text-left px-4 py-3 rounded-xl hover:bg-zinc-800 flex gap-3">
      <i class="fa-brands fa-telegram text-sky-400 w-5"></i>Support
    </a>
  </div>
</div>

<!-- QUICK FILTERS -->
<section class="container mx-auto px-3 md:px-5 mt-4">
  <div class="flex gap-2 overflow-x-auto pb-2 text-xs font-medium">
    <button onclick="go('trending')" class="shrink-0 px-4 py-2 rounded-full bg-nx-p text-white font-bold">
      <i class="fa-solid fa-fire mr-1"></i>Trending
    </button>
    <button onclick="go('newest')" class="shrink-0 px-4 py-2 rounded-full bg-zinc-800 border border-nx-border">Newest</button>
    <button onclick="go('best')" class="shrink-0 px-4 py-2 rounded-full bg-zinc-800 border border-nx-border">Best</button>
    <button onclick="go('hd')" class="shrink-0 px-4 py-2 rounded-full bg-zinc-800 border border-nx-border">HD</button>
    <button onclick="go('4k')" class="shrink-0 px-4 py-2 rounded-full bg-zinc-800 border border-nx-border">4K</button>
    <button onclick="viral()" class="shrink-0 px-4 py-2 rounded-full bg-zinc-800 border border-nx-border text-red-400">Viral</button>
  </div>
</section>

<main class="flex-1 container mx-auto px-3 md:px-5 py-5">
  <div id="load" class="hidden flex-col items-center justify-center py-20">
    <div class="w-12 h-12 border-4 border-nx-p border-t-transparent rounded-full animate-spin"></div>
    <p class="mt-4 text-sm text-zinc-500">Loading VIP feed...</p>
  </div>
  <div id="grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5"></div>
  <div class="text-center my-10">
    <button id="more" onclick="more()" class="hidden px-8 py-3 rounded-full bg-zinc-800 hover:bg-nx-p border border-nx-border font-medium">
      Load More
    </button>
  </div>
</main>

<!-- PLAYER MODAL -->
<div id="player" class="hidden fixed inset-0 z-[80] bg-black/95 flex items-center justify-center p-2 md:p-6">
  <div class="bg-nx-card rounded-2xl overflow-hidden max-w-5xl w-full max-h-[95vh] flex flex-col relative border border-nx-border">
    <button onclick="closeP()" class="absolute top-3 right-3 z-20 w-9 h-9 rounded-full bg-black/70 hover:bg-nx-p flex items-center justify-center">
      <i class="fa-solid fa-xmark"></i>
    </button>
    <div class="aspect-video bg-black">
      <video id="vid" controls class="w-full h-full" playsinline></video>
    </div>
    <div class="p-4 md:p-5 overflow-y-auto space-y-4">
      <h2 id="mt" class="text-lg font-bold"></h2>
      <div class="flex flex-wrap gap-3">
        <button onclick="dl()" class="flex-1 min-w-[150px] py-3 rounded-xl bg-nx-p font-bold text-sm flex items-center justify-center gap-2">
          <i class="fa-solid fa-download"></i> Download
        </button>
        <button onclick="copyS()" class="flex-1 min-w-[150px] py-3 rounded-xl bg-zinc-800 font-bold text-sm flex items-center justify-center gap-2">
          <i class="fa-solid fa-copy"></i> Copy Stream
        </button>
      </div>
      <div class="flex items-center justify-between text-sm">
        <div class="flex items-center gap-3">
          <img id="ma" class="w-10 h-10 rounded-full object-cover border border-nx-border">
          <div>
            <div id="mu" class="font-semibold"></div>
            <div id="mv" class="text-xs text-zinc-500"></div>
          </div>
        </div>
        <div id="mr" class="text-green-400 text-sm"></div>
      </div>
      <div id="reacts" class="flex flex-wrap gap-2 items-center">
        <button onclick="like()" class="px-4 py-2 rounded-full bg-zinc-800 hover:bg-nx-p text-sm">
          <i class="fa-solid fa-heart mr-1"></i><span id="lc">0</span>
        </button>
        <button onclick="react('🔥')" class="px-3 py-2 rounded-full bg-zinc-800 text-sm">🔥</button>
        <button onclick="react('😍')" class="px-3 py-2 rounded-full bg-zinc-800 text-sm">😍</button>
        <button onclick="react('👍')" class="px-3 py-2 rounded-full bg-zinc-800 text-sm">👍</button>
        <span id="rl" class="text-sm text-zinc-500 ml-2"></span>
      </div>
      <div id="tags" class="flex flex-wrap gap-1.5"></div>
    </div>
  </div>
</div>

<footer class="border-t border-nx-border py-6 text-center text-xs text-zinc-500">
  <p>© {datetime.now().year} <span class="text-nx-p font-semibold">{c['site_name']}</span> • Owner {c['owner']}</p>
  <a href="{c['channel']}" target="_blank" class="text-sky-400 hover:underline">
    <i class="fa-brands fa-telegram"></i> Support Channel
  </a>
  <p class="mt-1 text-[10px]">Views: <span id="tv">{c.get('views',0)}</span></p>
</footer>

<script>
const LIKES = {str(c.get('likes_on', True)).lower()};
const REACTS = {str(c.get('reacts_on', True)).lower()};
const POP = {str(c.get('popup', True)).lower()};
const PT = `{c.get('popup_title', '')}`;
const PM = `{c.get('popup_msg', '')}`;
const MAINT = {str(c.get('maintenance', False)).lower()};

let hls = null, stream = "", down = "", title = "", curUrl = "", page = 1, query = "trending";

function age(ok) {{
  if (ok) {{
    document.getElementById('age').classList.add('hidden');
    if (POP) {{
      document.getElementById('pt').innerText = PT;
      document.getElementById('pm').innerText = PM;
      document.getElementById('pop').classList.remove('hidden');
    }}
    search(1);
  }} else {{
    location = 'https://google.com';
  }}
}}

function menu() {{
  document.getElementById('side').classList.toggle('-translate-x-full');
}}

function go(q) {{
  document.getElementById('q').value = q;
  search(1);
}}

async function search(reset = 1) {{
  if (reset) {{
    page = 1;
    query = document.getElementById('q').value.trim() || 'trending';
  }}
  const g = document.getElementById('grid');
  const l = document.getElementById('load');
  const m = document.getElementById('more');
  if (reset) {{
    g.innerHTML = '';
    m.classList.add('hidden');
  }}
  l.classList.remove('hidden');
  l.classList.add('flex');
  try {{
    const r = await fetch(`/api/search?q=${{encodeURIComponent(query)}}&page=${{page}}`);
    const d = await r.json();
    l.classList.add('hidden');
    l.classList.remove('flex');
    if (!d || !d.length) {{
      if (reset) g.innerHTML = `<div class="col-span-full text-center py-16 text-zinc-500"><i class="fa-solid fa-face-frown text-4xl mb-3"></i><p>No results</p></div>`;
      return;
    }}
    render(d, !reset);
    m.classList.remove('hidden');
  }} catch (e) {{
    l.classList.add('hidden');
    if (reset) g.innerHTML = `<div class="col-span-full text-center py-10 text-red-400">Error loading</div>`;
  }}
}}

function more() {{
  page++;
  search(0);
}}

function render(items, app = 0) {{
  const g = document.getElementById('grid');
  if (!app) g.innerHTML = '';
  items.forEach(i => {{
    const c = document.createElement('div');
    c.className = 'bg-nx-card rounded-xl overflow-hidden border border-nx-border hover:border-nx-p/50 transition group cursor-pointer';
    const t = i.thumbnail || 'https://via.placeholder.com/320x180/141418/e91e63?text=NirobX';
    c.innerHTML = `
      <div class="relative" onclick="openP('${{i.url}}')">
        <img src="${{t}}" loading="lazy" onerror="this.src='https://via.placeholder.com/320x180/141418/e91e63?text=NirobX'" class="w-full thumb group-hover:scale-105 transition duration-500">
        <span class="absolute bottom-2 right-2 bg-black/80 text-[10px] px-1.5 py-0.5 rounded font-mono">${{i.duration || 'HD'}}</span>
        <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 flex items-center justify-center transition">
          <div class="w-12 h-12 rounded-full bg-nx-p/90 flex items-center justify-center"><i class="fa-solid fa-play text-white"></i></div>
        </div>
      </div>
      <div class="p-3">
        <h3 onclick="openP('${{i.url}}')" class="text-sm font-semibold clamp group-hover:text-nx-p transition">${{i.title}}</h3>
        <div class="mt-2 flex items-center justify-between text-xs text-zinc-500">
          <div class="flex items-center gap-1.5 truncate max-w-[60%]">
            <img src="${{i.uploader_avatar}}" class="w-5 h-5 rounded-full object-cover">
            <span class="truncate">${{i.uploader_name}}</span>
          </div>
          <span>${{i.views}}</span>
        </div>
      </div>`;
    g.appendChild(c);
  }});
}}

async function openP(url) {{
  curUrl = url;
  document.getElementById('player').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  const d = await (await fetch(`/api/video?url=${{encodeURIComponent(url)}}`)).json();
  if (!d || !d.m3u8_base_url) {{
    alert('Stream not found');
    closeP();
    return;
  }}
  stream = d.m3u8_base_url;
  down = d.download_url || d.m3u8_base_url;
  title = d.title;
  document.getElementById('mt').innerText = d.title;
  document.getElementById('ma').src = d.uploader_avatar;
  document.getElementById('mu').innerText = d.uploader_name;
  document.getElementById('mv').innerText = d.views;
  document.getElementById('mr').innerHTML = `<i class="fa-solid fa-thumbs-up mr-1"></i>${{d.rating_percentage}}`;
  document.getElementById('tags').innerHTML = (d.tags || []).map(t => `<span class="text-[11px] px-2 py-1 rounded bg-zinc-800 border border-nx-border">${{t}}</span>`).join('');
  
  let h = JSON.parse(localStorage.getItem('nx_h') || '[]');
  h = h.filter(x => x.url !== url);
  h.unshift({{ title: d.title, url, thumb: d.thumbnail }});
  if (h.length > 40) h.pop();
  localStorage.setItem('nx_h', JSON.stringify(h));
  
  loadL(url);
  const v = document.getElementById('vid');
  if (Hls.isSupported()) {{
    if (hls) hls.destroy();
    hls = new Hls();
    hls.loadSource(d.m3u8_base_url);
    hls.attachMedia(v);
    hls.on(Hls.Events.MANIFEST_PARSED, () => v.play());
  }} else if (v.canPlayType('application/vnd.apple.mpegurl')) {{
    v.src = d.m3u8_base_url;
    v.play();
  }}
}}

function closeP() {{
  document.getElementById('player').classList.add('hidden');
  document.body.style.overflow = 'auto';
  document.getElementById('vid').pause();
  if (hls) {{ hls.destroy(); hls = null; }}
}}

function dl() {{
  if (!down) return alert('No link');
  location = `/api/download?url=${{encodeURIComponent(down)}}&title=${{encodeURIComponent(title)}}`;
}}

function copyS() {{
  if (stream) {{
    navigator.clipboard.writeText(stream);
    alert('Copied!');
  }}
}}

async function loadL(u) {{
  if (!LIKES) {{
    document.getElementById('reacts').style.display = 'none';
    return;
  }}
  const d = await (await fetch(`/api/likes?url=${{encodeURIComponent(u)}}`)).json();
  document.getElementById('lc').innerText = d.likes || 0;
  document.getElementById('rl').innerText = (d.reacts || []).join(' ');
}}

async function like() {{
  await fetch('/api/like', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ url: curUrl }})
  }});
  loadL(curUrl);
}}

async function react(e) {{
  if (!REACTS) return;
  await fetch('/api/react', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ url: curUrl, emoji: e }})
  }});
  loadL(curUrl);
}}

function marks() {{
  const b = JSON.parse(localStorage.getItem('nx_b') || '[]');
  document.getElementById('grid').innerHTML = '';
  document.getElementById('more').classList.add('hidden');
  if (!b.length) {{
    document.getElementById('grid').innerHTML = `<div class="col-span-full text-center py-16 text-zinc-500">No bookmarks</div>`;
    return;
  }}
  render(b);
}}

function hist() {{
  const h = JSON.parse(localStorage.getItem('nx_h') || '[]');
  document.getElementById('grid').innerHTML = '';
  document.getElementById('more').classList.add('hidden');
  if (!h.length) {{
    document.getElementById('grid').innerHTML = `<div class="col-span-full text-center py-16 text-zinc-500">No history</div>`;
    return;
  }}
  render(h.map(x => ({{
    ...x,
    duration: '',
    views: '',
    uploader_name: '',
    uploader_avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=h'
  }})));
}}

async function viral() {{
  const d = await (await fetch('/api/uploads')).json();
  document.getElementById('grid').innerHTML = '';
  document.getElementById('more').classList.add('hidden');
  if (!d.length) {{
    document.getElementById('grid').innerHTML = `<div class="col-span-full text-center py-16 text-zinc-500">No viral uploads</div>`;
    return;
  }}
  render(d);
}}

document.getElementById('q').addEventListener('keypress', e => {{
  if (e.key === 'Enter') search(1);
}});
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeP();
}});

if (MAINT) {{
  document.body.innerHTML = `<div class="min-h-screen flex items-center justify-center bg-black text-white text-center p-6"><div><h1 class="text-2xl font-bold mb-4">Maintenance</h1><p>{c.get('maint_msg', '')}</p></div></div>`;
}}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return ui()

@app.get("/api/search")
async def api_search(q: str = Query("trending"), page: int = Query(1)):
    ql = q.lower().strip()
    if ql in ["trending", "best", "popular"]:
        url = f"https://xhamster.com/best/{page}"
    elif ql in ["newest", "new"]:
        url = f"https://xhamster.com/newest/{page}"
    elif ql == "hd":
        url = f"https://xhamster.com/hd/{page}"
    elif ql in ["4k", "4k ultra"]:
        url = f"https://xhamster.com/4k/{page}"
    else:
        url = f"https://xhamster.com/search/{urllib.parse.quote(q)}?page={page}"
    html = await fetch(url)
    return parse_search(html)

@app.get("/api/video")
async def api_video(url: str = Query(...)):
    if HAS_API and xh_client:
        try:
            v = await xh_client.get_video(url)
            return {
                "title": v.title or "NirobX",
                "m3u8_base_url": v.m3u8_base_url,
                "download_url": v.m3u8_base_url,
                "thumbnail": v.thumbnail,
                "uploader_name": v.uploader_name or "Creator",
                "uploader_avatar": f"https://api.dicebear.com/7.x/bottts/svg?seed={urllib.parse.quote(v.uploader_name or 'c')}",
                "views": f"{getattr(v, 'likes', 0)} likes",
                "rating_percentage": f"{v.rating_percentage}%",
                "tags": (v.categories or []) + (v.tags or [])
            }
        except Exception as e:
            print("API video error:", e)
    html = await fetch(url)
    return parse_video(html)

@app.get("/api/download")
async def api_dl(url: str = Query(...), title: str = Query("video")):
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:60]
    fn = f"{clean}.mp4"
    if ".m3u8" in url:
        fn = f"{clean}.m3u8"
    headers = {"Content-Disposition": f'attachment; filename="{fn}"'}
    try:
        async with AsyncSession(impersonate="chrome120") as s:
            r = await s.get(url, headers=HEADERS, stream=True)
            return StreamingResponse(r.aiter_bytes(), media_type="video/mp4", headers=headers)
    except Exception:
        return RedirectResponse(url)

@app.get("/api/uploads")
async def api_up():
    return uploads

@app.get("/api/likes")
async def get_likes(url: str = Query(...)):
    return likes.get(url, {"likes": 0, "reacts": []})

@app.post("/api/like")
async def post_like(req: Request):
    b = await req.json()
    u = b.get("url")
    if not u:
        return {"ok": False}
    if u not in likes:
        likes[u] = {"likes": 0, "reacts": []}
    likes[u]["likes"] += 1
    save(LIK_F, likes)
    return {"ok": True}

@app.post("/api/react")
async def post_react(req: Request):
    b = await req.json()
    u = b.get("url")
    e = b.get("emoji", "🔥")
    if not u:
        return {"ok": False}
    if u not in likes:
        likes[u] = {"likes": 0, "reacts": []}
    likes[u]["reacts"].append(e)
    if len(likes[u]["reacts"]) > 25:
        likes[u]["reacts"] = likes[u]["reacts"][-25:]
    save(LIK_F, likes)
    return {"ok": True}

# ================= ADMIN =================
ADMIN_TPL = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NirobX Admin</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
</head>
<body class="bg-zinc-950 text-gray-100 min-h-screen">
<div class="container mx-auto px-4 py-8 max-w-5xl">
  <h1 class="text-2xl font-bold mb-6 flex items-center gap-3">
    <i class="fa-solid fa-shield-halved text-pink-500"></i> NirobX VIP Admin
  </h1>
  <div class="grid md:grid-cols-2 gap-6">
    <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <h2 class="font-bold text-lg border-b border-zinc-700 pb-2">Settings</h2>
      <form method="post" action="/admin/save" class="space-y-3 text-sm">
        <div>
          <label class="block text-zinc-400 mb-1">Site Name</label>
          <input name="site_name" value="{{site_name}}" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        </div>
        <div>
          <label class="block text-zinc-400 mb-1">Tagline</label>
          <input name="site_tagline" value="{{site_tagline}}" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-zinc-400 mb-1">Primary</label>
            <input name="primary" type="color" value="{{primary}}" class="w-full h-10 bg-zinc-800 rounded">
          </div>
          <div>
            <label class="block text-zinc-400 mb-1">Accent</label>
            <input name="accent" type="color" value="{{accent}}" class="w-full h-10 bg-zinc-800 rounded">
          </div>
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" name="maintenance" id="m" {{'checked' if maintenance else ''}}>
          <label for="m">Maintenance</label>
        </div>
        <div>
          <label class="block text-zinc-400 mb-1">Maint Message</label>
          <textarea name="maint_msg" rows="2" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">{{maint_msg}}</textarea>
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" name="popup" id="p" {{'checked' if popup else ''}}>
          <label for="p">Popup</label>
        </div>
        <div>
          <label class="block text-zinc-400 mb-1">Popup Title</label>
          <input name="popup_title" value="{{popup_title}}" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        </div>
        <div>
          <label class="block text-zinc-400 mb-1">Popup Msg</label>
          <textarea name="popup_msg" rows="2" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">{{popup_msg}}</textarea>
        </div>
        <div class="flex gap-4">
          <label class="flex items-center gap-2">
            <input type="checkbox" name="likes_on" {{'checked' if likes_on else ''}}> Likes
          </label>
          <label class="flex items-center gap-2">
            <input type="checkbox" name="reacts_on" {{'checked' if reacts_on else ''}}> Reacts
          </label>
        </div>
        <button class="w-full py-2.5 bg-pink-600 hover:bg-pink-500 rounded-lg font-bold">Save</button>
      </form>
    </div>

    <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <h2 class="font-bold text-lg border-b border-zinc-700 pb-2">Stats & Visitors</h2>
      <p class="text-3xl font-black text-pink-500">{{views}} <span class="text-sm text-zinc-400 font-normal">views</span></p>
      <p class="text-sm text-zinc-400">Unique IPs: {{unique}}</p>
      <div class="max-h-64 overflow-y-auto text-xs space-y-1 border border-zinc-800 rounded-lg p-2">
        {% for v in recent %}
        <div class="flex justify-between gap-2 py-1 border-b border-zinc-800/50">
          <span class="font-mono text-pink-400">{{v.ip}}</span>
          <span class="text-zinc-500 truncate">{{v.path}}</span>
          <span class="text-zinc-600">{{v.time[11:19]}}</span>
        </div>
        {% endfor %}
      </div>
      <form method="post" action="/admin/block" class="flex gap-2 mt-2">
        <input name="ip" placeholder="IP to block" class="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
        <button class="px-4 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-bold">Block</button>
      </form>
      <div class="text-xs text-zinc-500">Blocked: {{blocked}}</div>
    </div>

    <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4 md:col-span-2">
      <h2 class="font-bold text-lg border-b border-zinc-700 pb-2">Viral Upload</h2>
      <form method="post" action="/admin/upload" class="grid md:grid-cols-2 gap-3 text-sm">
        <input name="title" placeholder="Title" required class="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        <input name="url" placeholder="xhamster video URL" required class="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        <input name="thumbnail" placeholder="Thumbnail URL (optional)" class="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        <input name="duration" placeholder="12:34" class="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
        <button class="md:col-span-2 py-2.5 bg-green-600 hover:bg-green-500 rounded-lg font-bold">Add Viral</button>
      </form>
      <div class="mt-4">
        <h3 class="font-semibold mb-2">Uploads ({{count}})</h3>
        <div class="space-y-2 max-h-48 overflow-y-auto text-sm">
          {% for u in uploads %}
          <div class="flex items-center justify-between bg-zinc-800/50 rounded-lg px-3 py-2">
            <span class="truncate">{{u.title}}</span>
            <form method="post" action="/admin/del" class="inline">
              <input type="hidden" name="url" value="{{u.url}}">
              <button class="text-red-400 hover:text-red-300 text-xs">Delete</button>
            </form>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>
  </div>
  <p class="mt-8 text-center text-xs text-zinc-600">NirobX VIP Admin • password protected</p>
</div>
</body>
</html>"""

@app.get("/admin", response_class=HTMLResponse)
async def admin(auth=Depends(admin_auth)):
    from jinja2 import Template
    recent = list(reversed(visitors[-25:]))
    unique = len(set(v["ip"] for v in visitors))
    return Template(ADMIN_TPL).render(
        site_name=cfg.get("site_name"),
        site_tagline=cfg.get("site_tagline"),
        primary=cfg.get("primary"),
        accent=cfg.get("accent"),
        maintenance=cfg.get("maintenance"),
        maint_msg=cfg.get("maint_msg"),
        popup=cfg.get("popup"),
        popup_title=cfg.get("popup_title"),
        popup_msg=cfg.get("popup_msg"),
        likes_on=cfg.get("likes_on"),
        reacts_on=cfg.get("reacts_on"),
        views=cfg.get("views", 0),
        unique=unique,
        recent=recent,
        blocked=", ".join(blocked) or "None",
        uploads=uploads,
        count=len(uploads)
    )

@app.post("/admin/save")
async def save_cfg(
    site_name: str = Form(...),
    site_tagline: str = Form(...),
    primary: str = Form(...),
    accent: str = Form(...),
    maint_msg: str = Form(""),
    popup_title: str = Form(""),
    popup_msg: str = Form(""),
    maintenance: Optional[str] = Form(None),
    popup: Optional[str] = Form(None),
    likes_on: Optional[str] = Form(None),
    reacts_on: Optional[str] = Form(None),
    auth=Depends(admin_auth)
):
    cfg.update({
        "site_name": site_name,
        "site_tagline": site_tagline,
        "primary": primary,
        "accent": accent,
        "maintenance": maintenance == "on",
        "maint_msg": maint_msg,
        "popup": popup == "on",
        "popup_title": popup_title,
        "popup_msg": popup_msg,
        "likes_on": likes_on == "on",
        "reacts_on": reacts_on == "on"
    })
    save(CFG_F, cfg)
    return RedirectResponse("/admin", 303)

@app.post("/admin/block")
async def block_ip(ip: str = Form(...), auth=Depends(admin_auth)):
    if ip and ip not in blocked:
        blocked.append(ip.strip())
        save(BLK_F, blocked)
    return RedirectResponse("/admin", 303)

@app.post("/admin/upload")
async def up_vid(
    title: str = Form(...),
    url: str = Form(...),
    thumbnail: str = Form(""),
    duration: str = Form("HD"),
    auth=Depends(admin_auth)
):
    uploads.insert(0, {
        "title": title,
        "url": url,
        "thumbnail": thumbnail or "https://via.placeholder.com/320x180/141418/e91e63?text=Viral",
        "duration": duration,
        "views": "Viral",
        "uploader_name": "NirobX",
        "uploader_avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=NirobX"
    })
    save(UPL_F, uploads)
    return RedirectResponse("/admin", 303)

@app.post("/admin/del")
async def del_up(url: str = Form(...), auth=Depends(admin_auth)):
    global uploads
    uploads = [u for u in uploads if u["url"] != url]
    save(UPL_F, uploads)
    return RedirectResponse("/admin", 303)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 25595))
    print(f"NirobX VIP Hub → http://0.0.0.0:{port}")
    print(f"Admin → http://0.0.0.0:{port}/admin  (admin / nirobxcodx)")
    uvicorn.run(app, host="0.0.0.0", port=port)
