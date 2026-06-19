import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from 爬虫 import (
    CrawlConfig,
    CrawlFilters,
    CrawlLevel,
    SiteCategories,
    WP_TYPE_OPTIONS,
    WallpaperSource,
    fetch_categories,
    run_crawl,
)

SITE_URL = "https://haowallpaper.com"


class CrawlerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("哲风壁纸爬虫 — haowallpaper.com")
        self.geometry("680x720")
        self.minsize(560, 640)

        self._stop_event = threading.Event()
        self._worker = None
        self._categories: SiteCategories | None = None
        self._cat_map: dict[str, dict[str, str]] = {
            "type": {},
            "ratio": {},
            "color": {},
        }

        self._build_ui()
        self.after(200, self._load_categories)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        header = ttk.Label(
            self,
            text="哲风壁纸 · 按分类自选爬取",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        header.pack(anchor="w", **pad)
        ttk.Label(
            self,
            text=f"数据源: {SITE_URL}（与官网筛选一致：种类 / 分类 / 分辨率 / 色系 / 标签）",
            foreground="#555",
            wraplength=640,
        ).pack(anchor="w", padx=10)

        src_frame = ttk.LabelFrame(self, text="壁纸类型")
        src_frame.pack(fill="x", padx=10, pady=6)
        self.source_var = tk.StringVar(value=WallpaperSource.PC.value)
        src_row = ttk.Frame(src_frame)
        src_row.pack(fill="x", padx=12, pady=8)
        for src in WallpaperSource:
            ttk.Radiobutton(
                src_row,
                text=src.label,
                variable=self.source_var,
                value=src.value,
            ).pack(side="left", padx=(0, 16))

        filter_frame = ttk.LabelFrame(self, text="分类筛选（与官网顶部下拉一致，可组合）")
        filter_frame.pack(fill="x", padx=10, pady=4)

        row1 = ttk.Frame(filter_frame)
        row1.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Label(row1, text="种类:", width=8).pack(side="left")
        self.wp_type_var = tk.StringVar(value="")
        self.wp_type_combo = ttk.Combobox(
            row1,
            textvariable=self.wp_type_var,
            state="readonly",
            width=14,
            values=[label for _, label in WP_TYPE_OPTIONS],
        )
        self.wp_type_combo.current(0)
        self.wp_type_combo.pack(side="left", padx=(0, 12))

        ttk.Label(row1, text="分类:", width=8).pack(side="left")
        self.type_var = tk.StringVar(value="全部")
        self.type_combo = ttk.Combobox(
            row1,
            textvariable=self.type_var,
            state="readonly",
            width=18,
            values=["全部"],
        )
        self.type_combo.current(0)
        self.type_combo.pack(side="left")

        row2 = ttk.Frame(filter_frame)
        row2.pack(fill="x", padx=12, pady=4)
        ttk.Label(row2, text="分辨率:", width=8).pack(side="left")
        self.ratio_var = tk.StringVar(value="全部")
        self.ratio_combo = ttk.Combobox(
            row2,
            textvariable=self.ratio_var,
            state="readonly",
            width=14,
            values=["全部"],
        )
        self.ratio_combo.current(0)
        self.ratio_combo.pack(side="left", padx=(0, 12))

        ttk.Label(row2, text="色系:", width=8).pack(side="left")
        self.color_var = tk.StringVar(value="全部")
        self.color_combo = ttk.Combobox(
            row2,
            textvariable=self.color_var,
            state="readonly",
            width=14,
            values=["全部"],
        )
        self.color_combo.current(0)
        self.color_combo.pack(side="left")

        row3 = ttk.Frame(filter_frame)
        row3.pack(fill="x", padx=12, pady=(4, 8))
        ttk.Label(row3, text="标签:", width=8).pack(side="left")
        self.lb_name_var = tk.StringVar()
        ttk.Entry(row3, textvariable=self.lb_name_var, width=16).pack(
            side="left", padx=(0, 4)
        )
        ttk.Label(row3, text="如 动漫、风景", foreground="#888").pack(side="left")

        row4 = ttk.Frame(filter_frame)
        row4.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(row4, text="关键词:", width=8).pack(side="left")
        self.search_var = tk.StringVar()
        ttk.Entry(row4, textvariable=self.search_var, width=28).pack(side="left")
        ttk.Label(row4, text="全文搜索", foreground="#888").pack(side="left", padx=6)

        self.cat_status = ttk.Label(
            filter_frame, text="正在加载官网分类…", foreground="#0066aa"
        )
        self.cat_status.pack(anchor="w", padx=12, pady=(0, 6))

        level_frame = ttk.LabelFrame(self, text="爬取程度")
        level_frame.pack(fill="x", padx=10, pady=4)

        self.level_var = tk.StringVar(value=CrawlLevel.STANDARD.value)
        for level in CrawlLevel:
            rb = ttk.Radiobutton(
                level_frame,
                text=level.label,
                variable=self.level_var,
                value=level.value,
                command=self._on_level_change,
            )
            rb.pack(anchor="w", padx=12, pady=2)

        self.hint_label = ttk.Label(
            level_frame, text="", foreground="#0066aa", wraplength=620
        )
        self.hint_label.pack(anchor="w", padx=12, pady=(0, 8))
        self._on_level_change()

        page_frame = ttk.LabelFrame(self, text="页码范围")
        page_frame.pack(fill="x", padx=10, pady=4)

        row = ttk.Frame(page_frame)
        row.pack(fill="x", padx=12, pady=8)
        ttk.Label(row, text="从第").pack(side="left")
        self.start_page_var = tk.StringVar(value="1")
        ttk.Spinbox(
            row, from_=1, to=9999, width=6, textvariable=self.start_page_var
        ).pack(side="left", padx=4)
        ttk.Label(row, text="页  到第").pack(side="left")
        self.end_page_var = tk.StringVar(value="3")
        ttk.Spinbox(row, from_=1, to=9999, width=6, textvariable=self.end_page_var).pack(
            side="left", padx=4
        )
        ttk.Label(row, text="页").pack(side="left")

        opt_frame = ttk.LabelFrame(self, text="其他选项")
        opt_frame.pack(fill="x", padx=10, pady=4)

        dir_row = ttk.Frame(opt_frame)
        dir_row.pack(fill="x", padx=12, pady=6)
        ttk.Label(dir_row, text="保存目录:").pack(side="left")
        self.save_dir_var = tk.StringVar(value=os.path.abspath("wallpapers"))
        ttk.Entry(dir_row, textvariable=self.save_dir_var, width=42).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(dir_row, text="浏览…", command=self._browse_dir).pack(side="left")

        delay_row = ttk.Frame(opt_frame)
        delay_row.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(delay_row, text="请求间隔(秒):").pack(side="left")
        self.delay_var = tk.StringVar(value="0.5")
        ttk.Spinbox(
            delay_row, from_=0, to=10, increment=0.5, width=6, textvariable=self.delay_var
        ).pack(side="left", padx=6)
        self.skip_existing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text="跳过已下载文件",
            variable=self.skip_existing_var,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=8)
        self.start_btn = ttk.Button(btn_row, text="开始爬取", command=self._on_start)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(
            btn_row, text="停止", command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left")
        ttk.Button(btn_row, text="刷新分类", command=self._load_categories).pack(
            side="right"
        )

        log_frame = ttk.LabelFrame(self, text="运行日志")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _populate_combo(
        self, combo: ttk.Combobox, items: list, id_map: dict[str, str]
    ):
        names = ["全部"] + [it.name for it in items]
        id_map.clear()
        for it in items:
            id_map[it.name] = it.id
        combo["values"] = names
        combo.current(0)

    def _load_categories(self):
        def worker():
            try:
                cats = fetch_categories(log=lambda _msg: None)
            except Exception as e:
                self.after(0, lambda: self._on_categories_failed(str(e)))
                return
            self.after(0, lambda: self._on_categories_loaded(cats))

        threading.Thread(target=worker, daemon=True).start()

    def _on_categories_loaded(self, cats: SiteCategories):
        self._categories = cats
        self._populate_combo(self.type_combo, cats.types, self._cat_map["type"])
        self._populate_combo(self.ratio_combo, cats.ratios, self._cat_map["ratio"])
        self._populate_combo(self.color_combo, cats.colors, self._cat_map["color"])
        self.cat_status.config(
            text=f"已同步官网分类：{len(cats.types)} 类 · {len(cats.ratios)} 档分辨率 · {len(cats.colors)} 色系",
            foreground="#22863a",
        )

    def _on_categories_failed(self, err: str):
        self.cat_status.config(
            text=f"分类加载失败（仍可爬全站）: {err}",
            foreground="#cc0000",
        )

    def _on_level_change(self):
        level = CrawlLevel(self.level_var.get())
        self.hint_label.config(text=f"提示: {level.hint}")

    def _browse_dir(self):
        path = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if path:
            self.save_dir_var.set(path)

    def _log(self, message: str):
        def append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        self.after(0, append)

    def _set_running(self, running: bool):
        state_run = "disabled" if running else "normal"
        state_stop = "normal" if running else "disabled"
        self.start_btn.config(state=state_run)
        self.stop_btn.config(state=state_stop)

    def _combo_id(self, var: tk.StringVar, id_map: dict[str, str]) -> str:
        name = var.get().strip()
        if not name or name == "全部":
            return ""
        return id_map.get(name, "")

    def _wp_type_id(self) -> str:
        label = self.wp_type_var.get()
        for val, name in WP_TYPE_OPTIONS:
            if name == label:
                return val
        return ""

    def _build_filters(self) -> CrawlFilters:
        return CrawlFilters(
            source=WallpaperSource(self.source_var.get()),
            wp_type=self._wp_type_id(),
            type_id=self._combo_id(self.type_var, self._cat_map["type"]),
            ratio_id=self._combo_id(self.ratio_var, self._cat_map["ratio"]),
            color_id=self._combo_id(self.color_var, self._cat_map["color"]),
            lb_name=self.lb_name_var.get().strip(),
            search=self.search_var.get().strip(),
        )

    def _parse_config(self) -> CrawlConfig | None:
        try:
            start_page = int(self.start_page_var.get())
            end_page = int(self.end_page_var.get())
            delay = float(self.delay_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "页码与请求间隔必须为数字。")
            return None

        if start_page < 1 or end_page < 1:
            messagebox.showerror("参数错误", "页码必须大于等于 1。")
            return None
        if start_page > end_page:
            messagebox.showerror("参数错误", "起始页不能大于结束页。")
            return None
        if delay < 0:
            messagebox.showerror("参数错误", "请求间隔不能为负数。")
            return None

        save_dir = self.save_dir_var.get().strip()
        if not save_dir:
            messagebox.showerror("参数错误", "请指定保存目录。")
            return None

        filters = self._build_filters()
        if not any(
            [
                filters.wp_type,
                filters.type_id,
                filters.ratio_id,
                filters.color_id,
                filters.lb_name,
                filters.search,
            ]
        ):
            if not messagebox.askyesno(
                "未选分类",
                "当前未选择任何分类筛选，将爬取该类型下的全部壁纸（数据量可能很大）。\n\n是否继续？",
            ):
                return None

        return CrawlConfig(
            level=CrawlLevel(self.level_var.get()),
            start_page=start_page,
            end_page=end_page,
            save_dir=save_dir,
            request_delay=delay,
            skip_existing=self.skip_existing_var.get(),
            filters=filters,
        )

    def _on_start(self):
        if self._worker and self._worker.is_alive():
            return

        config = self._parse_config()
        if not config:
            return

        self._stop_event.clear()
        self._set_running(True)
        self._log("=" * 48)
        self._log("任务开始…")

        def worker():
            try:
                run_crawl(
                    config,
                    log=self._log,
                    should_stop=self._stop_event.is_set,
                )
            except Exception as e:
                self._log(f"运行异常: {e}")
            finally:
                self.after(0, lambda: self._set_running(False))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _on_stop(self):
        self._stop_event.set()
        self._log("正在停止，请等待当前请求结束…")


def launch_gui():
    app = CrawlerApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
