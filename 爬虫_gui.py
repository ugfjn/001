import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from 爬虫 import CrawlConfig, CrawlLevel, run_crawl

SITE_URL = "https://haowallpaper.com/homeView"


class CrawlerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("哲风壁纸爬虫 — haowallpaper.com")
        self.geometry("640x560")
        self.minsize(520, 480)

        self._stop_event = threading.Event()
        self._worker = None

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        header = ttk.Label(
            self,
            text="电脑壁纸列表 · homeView",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        header.pack(anchor="w", **pad)
        ttk.Label(
            self,
            text=f"数据源: {SITE_URL}（每页约 12 条，站点共 3000+ 页）",
            foreground="#555",
        ).pack(anchor="w", padx=10)

        level_frame = ttk.LabelFrame(self, text="爬取程度")
        level_frame.pack(fill="x", padx=10, pady=8)

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

        self.hint_label = ttk.Label(level_frame, text="", foreground="#0066aa", wraplength=580)
        self.hint_label.pack(anchor="w", padx=12, pady=(0, 8))
        self._on_level_change()

        page_frame = ttk.LabelFrame(self, text="页码范围")
        page_frame.pack(fill="x", padx=10, pady=4)

        row = ttk.Frame(page_frame)
        row.pack(fill="x", padx=12, pady=8)
        ttk.Label(row, text="从第").pack(side="left")
        self.start_page_var = tk.StringVar(value="1")
        ttk.Spinbox(row, from_=1, to=9999, width=6, textvariable=self.start_page_var).pack(
            side="left", padx=4
        )
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

        log_frame = ttk.LabelFrame(self, text="运行日志")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

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

        return CrawlConfig(
            level=CrawlLevel(self.level_var.get()),
            start_page=start_page,
            end_page=end_page,
            save_dir=save_dir,
            request_delay=delay,
            skip_existing=self.skip_existing_var.get(),
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
