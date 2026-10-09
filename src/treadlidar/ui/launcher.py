"""Open the UI in its own desktop window.

Preference order (first that works):
1. pywebview (BSD-3-Clause) - a native window with the system web view. Optional: ``pip install pywebview``.
   Note for Linux: pywebview needs a GUI backend; prefer GTK (LGPL). Its Qt backend can pull in PyQt (GPL), which
   matters for a commercial product - use PySide6 (LGPL) or the Chromium window below instead.
2. Chromium / Chrome / Edge in ``--app`` mode (a chrome-less window, own profile directory).
3. The default web browser.

The server only listens on 127.0.0.1 and requires a random per-launch token, so nothing is exposed to the network.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from .server import create_server

_CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge", "msedge"]
_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium", "/opt/pw-browsers/chromium",
]


def find_chromium(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if (shutil.which(explicit) or Path(explicit).exists()) else None
    for c in _CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    return next((p for p in _PATHS if Path(p).exists()), None)


def launch(port: int = 0, mode: str = "auto", width: int = 1480, height: int = 920, browser: Optional[str] = None,
           title: str = "TreadLidar") -> int:
    """Start the server and show the UI. ``mode``: auto | pywebview | chromium | browser | none. Blocks until closed."""
    srv = create_server(port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = srv.url
    print(f"TreadLidar UI running at {url}\n(only reachable from this computer; the token in the link is required)")
    try:
        if mode == "none":
            return _wait_forever()
        if mode in ("auto", "pywebview"):
            try:
                import webview  # type: ignore

                webview.create_window(title, url, width=width, height=height, min_size=(1100, 700))
                webview.start()
                return 0
            except ImportError:
                if mode == "pywebview":
                    print("pywebview is not installed: pip install pywebview", file=sys.stderr)
                    return 2
            except Exception as e:  # missing GUI backend etc.
                print(f"pywebview could not open a window ({e}); trying Chromium", file=sys.stderr)
        if mode in ("auto", "pywebview", "chromium"):
            exe = find_chromium(browser)
            if exe:
                prof = tempfile.mkdtemp(prefix="treadlidar_profile_")
                args = [exe, f"--app={url}", f"--window-size={width},{height}", f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check"]
                if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
                    args.append("--no-sandbox")
                proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait()
                shutil.rmtree(prof, ignore_errors=True)
                return 0
            if mode == "chromium":
                print("no Chromium/Chrome/Edge found; pass --browser PATH", file=sys.stderr)
                return 2
        import webbrowser

        webbrowser.open(url)
        print("Opened in your default browser. Press Ctrl+C here to stop the app.")
        return _wait_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        srv.shutdown()


def _wait_forever() -> int:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0
