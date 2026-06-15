"""PyInstaller 打包入口（英文文件名，避免打包工具识别问题）。"""
from 爬虫_gui import launch_gui

if __name__ == "__main__":
    launch_gui()
