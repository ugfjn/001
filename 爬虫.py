import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import requests

BASE_URL = "https://haowallpaper.com"
LIST_URL = f"{BASE_URL}/homeView"
FILE_BASE = f"{BASE_URL}/link/common/file"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": LIST_URL,
}

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
}


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
class CrawlConfig:
    level: CrawlLevel = CrawlLevel.STANDARD
    start_page: int = 1
    end_page: int = 3
    save_dir: str = "wallpapers"
    request_delay: float = 0.5
    skip_existing: bool = True


LogCallback = Callable[[str], None]
StopCheck = Callable[[], bool]


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_list_page(html):
    return list(dict.fromkeys(re.findall(r"/homeViewLook/([\w]+)", html)))


def parse_list_page_items(html):
    """从列表页解析壁纸 ID、缩略图文件 ID 与标题。"""
    items = []
    for wallpaper_id in parse_list_page(html):
        pattern = (
            rf"/homeViewLook/{wallpaper_id}[\s\S]{{0,2500}}?"
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
):
    url = f"{FILE_BASE}/{endpoint}/{file_id}"
    try:
        response = requests.get(url, headers=HEADERS, stream=True, timeout=60)
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


def collect_items_fast(page_num, log=print, should_stop: StopCheck | None = None):
    page_url = LIST_URL if page_num == 1 else f"{LIST_URL}?page={page_num}"
    log(f"正在解析列表第 {page_num} 页: {page_url}")
    html = fetch_html(page_url)
    items = parse_list_page_items(html)
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


def collect_items_detail(page_num, log=print, should_stop: StopCheck | None = None):
    page_url = LIST_URL if page_num == 1 else f"{LIST_URL}?page={page_num}"
    log(f"正在爬取列表第 {page_num} 页: {page_url}")
    html = fetch_html(page_url)
    wallpaper_ids = parse_list_page(html)
    log(f"  找到 {len(wallpaper_ids)} 个条目，正在访问详情页…")

    results = []
    for idx, wallpaper_id in enumerate(wallpaper_ids, 1):
        if should_stop and should_stop():
            break
        detail_url = f"{BASE_URL}/homeViewLook/{wallpaper_id}"
        try:
            detail_html = fetch_html(detail_url)
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
    collect_fn = collect_items_fast if use_fast else collect_items_detail

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

        try:
            items = collect_fn(page, log=log, should_stop=should_stop)
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
