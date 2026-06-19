import base64
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from urllib.parse import quote, urlencode

import requests

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

BASE_URL = "https://haowallpaper.com"
FILE_BASE = f"{BASE_URL}/link/common/file"
API_BASE = f"{BASE_URL}/link"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

_AES_KEY = b"68zhehao2O776519"
_AES_IV = b"aa176b7519e84710"

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
}

# 种类（与站点下拉一致）
WP_TYPE_OPTIONS = [
    ("", "全部"),
    ("1", "静态壁纸"),
    ("2", "动态壁纸"),
]


class WallpaperSource(Enum):
    PC = "pc"
    MOBILE = "mobile"

    @property
    def label(self):
        return {"pc": "电脑壁纸", "mobile": "手机壁纸"}[self.value]

    @property
    def list_path(self):
        return "/homeView" if self == WallpaperSource.PC else "/mobileView"

    @property
    def look_prefix(self):
        return "/homeViewLook" if self == WallpaperSource.PC else "/mobileViewLook"


class CrawlLevel(Enum):
    """爬取程度：速度、请求量、画质依次递增。"""

    FAST = "fast"
    STANDARD = "standard"
    FULL = "full"

    @property
    def label(self):
        return {
            CrawlLevel.FAST: "快速 — 仅列表缩略图（不访问详情页）",
            CrawlLevel.STANDARD: "标准 — 详情页预览图（静态壁纸）",
            CrawlLevel.FULL: "完整 — 详情页预览图（含动态壁纸 MP4）",
        }[self]

    @property
    def hint(self):
        return {
            CrawlLevel.FAST: "画质较低，速度最快，每页约 12 张",
            CrawlLevel.STANDARD: "无需登录，画质优于缩略图，推荐日常使用",
            CrawlLevel.FULL: "包含动态壁纸视频，体积较大",
        }[self]


@dataclass
class CategoryItem:
    id: str
    name: str
    code: str = ""


@dataclass
class SiteCategories:
    """站点 getTypeAll 返回的三组筛选项。"""

    types: list[CategoryItem] = field(default_factory=list)  # 分类
    ratios: list[CategoryItem] = field(default_factory=list)  # 分辨率
    colors: list[CategoryItem] = field(default_factory=list)  # 色系


@dataclass
class CrawlFilters:
    source: WallpaperSource = WallpaperSource.PC
    wp_type: str = ""  # 种类：1 静态 / 2 动态
    type_id: str = ""  # 分类
    ratio_id: str = ""  # 分辨率档位
    ratio_val: str = ""  # 自定义分辨率
    color_id: str = ""  # 色系
    lb_name: str = ""  # 标签名（如 动漫、风景）
    search: str = ""  # 关键词

    def query_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.wp_type:
            params["wpType"] = self.wp_type
        if self.type_id:
            params["typeId"] = self.type_id
        if self.ratio_id:
            params["ratioId"] = self.ratio_id
        if self.ratio_val:
            params["ratioVal"] = self.ratio_val
        if self.color_id:
            params["colorId"] = self.color_id
        if self.lb_name.strip():
            params["lbName"] = self.lb_name.strip()
        if self.search.strip():
            params["search"] = self.search.strip()
        return params

    def summary(self) -> str:
        parts = [self.source.label]
        wp_names = dict(WP_TYPE_OPTIONS)
        if self.wp_type:
            parts.append(wp_names.get(self.wp_type, self.wp_type))
        if self.type_id:
            parts.append(f"分类已选")
        if self.ratio_id or self.ratio_val:
            parts.append(f"分辨率={self.ratio_id or self.ratio_val}")
        if self.color_id:
            parts.append("色系已选")
        if self.lb_name.strip():
            parts.append(f"标签={self.lb_name.strip()}")
        if self.search.strip():
            parts.append(f"搜索={self.search.strip()}")
        if len(parts) == 1:
            parts.append("全部")
        return " · ".join(parts)


@dataclass
class CrawlConfig:
    level: CrawlLevel = CrawlLevel.STANDARD
    start_page: int = 1
    end_page: int = 3
    save_dir: str = "wallpapers"
    request_delay: float = 0.5
    skip_existing: bool = True
    filters: CrawlFilters = field(default_factory=CrawlFilters)


LogCallback = Callable[[str], None]
StopCheck = Callable[[], bool]


def _headers_for(source: WallpaperSource) -> dict[str, str]:
    h = dict(HEADERS)
    h["Referer"] = BASE_URL + source.list_path
    return h


def decrypt_api_data(raw: str) -> str:
    if not _HAS_CRYPTO:
        raise RuntimeError("缺少 pycryptodome，请执行: pip install pycryptodome")
    ct = base64.b64decode(raw)
    plain = unpad(AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(ct), AES.block_size)
    return plain.decode("utf-8", errors="ignore").split("\x00", 1)[0]


def fetch_categories(log: LogCallback = print) -> SiteCategories:
    """从 /pc/wallpaper/getTypeAll 拉取站点分类、分辨率、色系。"""
    url = f"{API_BASE}/pc/wallpaper/getTypeAll"
    log("正在获取站点分类…")
    response = requests.get(url, headers=_headers_for(WallpaperSource.PC), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 200:
        raise RuntimeError(payload.get("msg") or "获取分类失败")

    import json

    data = json.loads(decrypt_api_data(payload["data"]))

    def to_items(key: str) -> list[CategoryItem]:
        return [
            CategoryItem(
                id=str(item.get("id", "")),
                name=str(item.get("typeName", "")),
                code=str(item.get("typeCode", "")),
            )
            for item in data.get(key, [])
            if item.get("id") and item.get("typeName")
        ]

    cats = SiteCategories(
        types=to_items("1"),
        ratios=to_items("2"),
        colors=to_items("3"),
    )
    log(
        f"分类 {len(cats.types)} 项，分辨率 {len(cats.ratios)} 项，色系 {len(cats.colors)} 项"
    )
    return cats


def build_list_url(source: WallpaperSource, page: int, filters: CrawlFilters) -> str:
    path = source.list_path
    params = filters.query_params()
    if page > 1:
        params["page"] = str(page)
    if not params:
        return f"{BASE_URL}{path}"
    return f"{BASE_URL}{path}?{urlencode(params, quote_via=quote)}"


def fetch_html(url, source: WallpaperSource = WallpaperSource.PC):
    response = requests.get(url, headers=_headers_for(source), timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_list_page(html, source: WallpaperSource = WallpaperSource.PC):
    prefix = re.escape(source.look_prefix)
    return list(dict.fromkeys(re.findall(rf"{prefix}/([\w]+)", html)))


def parse_list_page_items(html, source: WallpaperSource = WallpaperSource.PC):
    """从列表页解析壁纸 ID、缩略图文件 ID 与标题。"""
    items = []
    look = source.look_prefix
    for wallpaper_id in parse_list_page(html, source):
        pattern = (
            rf"{re.escape(look)}/{wallpaper_id}[\s\S]{{0,2500}}?"
            r"(getCroppingImg|getVideoReduce)/([\w]+)"
        )
        match = re.search(pattern, html)
        if not match:
            continue
        endpoint, file_id = match.group(1), match.group(2)
        alt_match = re.search(
            rf"{endpoint}/{file_id}[^>]*alt=\"([^\"]*)\"",
            html,
        )
        title = alt_match.group(1).strip() if alt_match else wallpaper_id
        items.append(
            {
                "wallpaper_id": wallpaper_id,
                "file_id": file_id,
                "endpoint": endpoint,
                "title": title,
            }
        )
    return items


def parse_detail_page(html):
    preview_ids = re.findall(r"previewFileImg/([\w]+)", html)
    if not preview_ids:
        return None, None

    title_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    title = title_match.group(1).strip() if title_match else preview_ids[0]
    return preview_ids[0], title


def safe_filename(title, file_id, ext):
    name = re.sub(r'[\\/:*?"<>|]', "_", title)
    name = re.sub(r"\s+", " ", name).strip()[:80]
    if not name:
        name = file_id
    return f"{name}_{file_id}{ext}"


def download_file(
    file_id,
    title,
    save_dir,
    endpoint="previewFileImg",
    skip_video=False,
    skip_existing=True,
    log=print,
    source: WallpaperSource = WallpaperSource.PC,
):
    url = f"{FILE_BASE}/{endpoint}/{file_id}"
    try:
        response = requests.get(
            url, headers=_headers_for(source), stream=True, timeout=60
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        ext = CONTENT_TYPE_EXT.get(content_type, ".bin")

        if skip_video and content_type.startswith("video/"):
            log(f"跳过视频: {title}")
            return False

        filename = safe_filename(title, file_id, ext)
        filepath = os.path.join(save_dir, filename)

        if skip_existing and os.path.exists(filepath):
            log(f"已存在，跳过: {filename}")
            return False

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        size_kb = os.path.getsize(filepath) / 1024
        log(f"已下载: {filename} ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        log(f"下载失败 [{title}]: {e}")
        return False


def collect_items_fast(
    page_num,
    filters: CrawlFilters,
    log=print,
    should_stop: StopCheck | None = None,
):
    page_url = build_list_url(filters.source, page_num, filters)
    log(f"正在解析列表第 {page_num} 页: {page_url}")
    html = fetch_html(page_url, filters.source)
    items = parse_list_page_items(html, filters.source)
    log(f"  找到 {len(items)} 条（缩略图模式）")
    return [
        {
            "file_id": it["file_id"],
            "title": it["title"],
            "endpoint": it["endpoint"],
        }
        for it in items
        if not (should_stop and should_stop())
    ]


def collect_items_detail(
    page_num,
    filters: CrawlFilters,
    log=print,
    should_stop: StopCheck | None = None,
):
    page_url = build_list_url(filters.source, page_num, filters)
    log(f"正在爬取列表第 {page_num} 页: {page_url}")
    html = fetch_html(page_url, filters.source)
    wallpaper_ids = parse_list_page(html, filters.source)
    log(f"  找到 {len(wallpaper_ids)} 个条目，正在访问详情页…")

    look = filters.source.look_prefix
    results = []
    for idx, wallpaper_id in enumerate(wallpaper_ids, 1):
        if should_stop and should_stop():
            break
        detail_url = f"{BASE_URL}{look}/{wallpaper_id}"
        try:
            detail_html = fetch_html(detail_url, filters.source)
            file_id, title = parse_detail_page(detail_html)
            if not file_id:
                log(f"  [{idx}] 未找到预览资源: {wallpaper_id}")
                continue
            results.append(
                {"file_id": file_id, "title": title, "endpoint": "previewFileImg"}
            )
            log(f"  [{idx}] {title}")
        except Exception as e:
            log(f"  [{idx}] 详情页失败: {e}")
    return results


def run_crawl(
    config: CrawlConfig,
    log: LogCallback = print,
    should_stop: StopCheck | None = None,
):
    """
    按配置执行爬取，返回 (成功下载数, 是否被用户中止)。
    """
    os.makedirs(config.save_dir, exist_ok=True)
    skip_video = config.level != CrawlLevel.FULL
    use_fast = config.level == CrawlLevel.FAST
    filters = config.filters

    log(f"数据源: {filters.summary()}")
    log(f"爬取程度: {config.level.label}")
    log(f"页码范围: {config.start_page} — {config.end_page}")
    log(f"保存目录: {os.path.abspath(config.save_dir)}")
    log("说明: 网站原图下载需登录；当前最高为 previewFileImg / 列表缩略图。")
    log("-" * 48)

    downloaded = 0
    seen_ids = set()
    stopped = False

    for page in range(config.start_page, config.end_page + 1):
        if should_stop and should_stop():
            stopped = True
            log("用户已停止爬取。")
            break

        collect_fn = collect_items_fast if use_fast else collect_items_detail
        try:
            items = collect_fn(page, filters, log=log, should_stop=should_stop)
        except Exception as e:
            log(f"列表第 {page} 页失败: {e}")
            continue

        if should_stop and should_stop():
            stopped = True
            log("用户已停止爬取。")
            break

        for item in items:
            if should_stop and should_stop():
                stopped = True
                log("用户已停止爬取。")
                break

            file_id = item["file_id"]
            if file_id in seen_ids:
                continue
            seen_ids.add(file_id)

            if download_file(
                file_id,
                item["title"],
                config.save_dir,
                endpoint=item["endpoint"],
                skip_video=skip_video,
                skip_existing=config.skip_existing,
                log=log,
                source=filters.source,
            ):
                downloaded += 1

            if config.request_delay > 0:
                time.sleep(config.request_delay)

        if stopped:
            break

    if not stopped:
        log("-" * 48)
        log(f"爬取完成，共下载 {downloaded} 个文件。")
    return downloaded, stopped


def main_cli():
    config = CrawlConfig(
        level=CrawlLevel.STANDARD,
        start_page=1,
        end_page=3,
    )
    run_crawl(config)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        main_cli()

    else:
        from 爬虫_gui import launch_gui

        launch_gui()
