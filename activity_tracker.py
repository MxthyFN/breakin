#!/usr/bin/env python3
"""
Activity Tracker — a VISIBLE, LOCAL input-activity meter.

What this program does
----------------------
It counts how *often* you press keys and click the mouse, and shows you the
numbers live in a window. Think step counter, but for your hands: useful for
productivity tracking, typing cadence, and RSI / ergonomics awareness.

What this program does NOT do (by design)
-----------------------------------------
- It does NOT record which keys you press. The keyboard callback only does
  `self._keys += 1` — it never inspects or stores the key value, so there is
  physically no place in this code where typed text (passwords, messages,
  URLs) is captured. See `_on_key_press`.
- It does NOT send anything over the network. There is no `requests`, no
  `socket`, no webhook, no HTTP client imported anywhere in this file. All
  data stays on this machine in a local JSON file.
- It does NOT run hidden. It opens a normal window, shows a live status, and
  you start/stop it yourself. Closing the window stops tracking.

Data is stored locally at:  ~/.activity_tracker/stats.json

Dependencies:  pip install pynput
(Tkinter ships with the standard CPython installer on Windows and macOS; on
Linux install your distro's python3-tk package.)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

try:
    from pynput import keyboard, mouse
except ImportError:  # pragma: no cover - friendly message if dep missing
    raise SystemExit(
        "This app needs the 'pynput' package.\n"
        "Install it with:  pip install pynput"
    )

APP_DIR = Path.home() / ".activity_tracker"
STATS_FILE = APP_DIR / "stats.json"

# Mouse-position heatmap is bucketed into a coarse grid. We store WHERE on the
# screen clicks land (for an ergonomics heatmap), never WHAT was clicked.
GRID_COLS = 16
GRID_ROWS = 9


class ActivityModel:
    """Holds counts only. No key content, no click targets, no network."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.session_keys = 0
        self.session_clicks = 0
        self.session_start = time.time()

        # Persisted lifetime/day data.
        self.lifetime_keys = 0
        self.lifetime_clicks = 0
        self.by_hour = defaultdict(lambda: {"keys": 0, "clicks": 0})  # "YYYY-MM-DD HH"
        self.click_grid = defaultdict(int)  # "col,row" -> count
        self._load()

    # --- input callbacks -------------------------------------------------
    def add_key(self) -> None:
        # NOTE: we deliberately take no argument about which key it was.
        with self._lock:
            self.session_keys += 1
            self.lifetime_keys += 1
            self.by_hour[self._hour_key()]["keys"] += 1

    def add_click(self, x: int, y: int, screen_w: int, screen_h: int) -> None:
        with self._lock:
            self.session_clicks += 1
            self.lifetime_clicks += 1
            self.by_hour[self._hour_key()]["clicks"] += 1
            if screen_w and screen_h:
                col = min(GRID_COLS - 1, max(0, int(x / screen_w * GRID_COLS)))
                row = min(GRID_ROWS - 1, max(0, int(y / screen_h * GRID_ROWS)))
                self.click_grid[f"{col},{row}"] += 1

    # --- derived stats ---------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            elapsed = max(1e-6, time.time() - self.session_start)
            minutes = elapsed / 60.0
            kpm = self.session_keys / minutes
            cpm = self.session_clicks / minutes
            # Rough WPM: a common convention is 5 keystrokes per "word".
            wpm = (self.session_keys / 5.0) / minutes
            return {
                "session_keys": self.session_keys,
                "session_clicks": self.session_clicks,
                "elapsed": elapsed,
                "kpm": kpm,
                "cpm": cpm,
                "wpm": wpm,
                "lifetime_keys": self.lifetime_keys,
                "lifetime_clicks": self.lifetime_clicks,
                "by_hour": dict(self.by_hour),
                "click_grid": dict(self.click_grid),
            }

    def reset_session(self) -> None:
        with self._lock:
            self.session_keys = 0
            self.session_clicks = 0
            self.session_start = time.time()

    # --- persistence -----------------------------------------------------
    @staticmethod
    def _hour_key() -> str:
        return datetime.now().strftime("%Y-%m-%d %H")

    def _load(self) -> None:
        try:
            data = json.loads(STATS_FILE.read_text())
        except (FileNotFoundError, ValueError, OSError):
            return
        self.lifetime_keys = int(data.get("lifetime_keys", 0))
        self.lifetime_clicks = int(data.get("lifetime_clicks", 0))
        for k, v in data.get("by_hour", {}).items():
            self.by_hour[k] = {"keys": int(v.get("keys", 0)),
                               "clicks": int(v.get("clicks", 0))}
        for k, v in data.get("click_grid", {}).items():
            self.click_grid[k] = int(v)

    def save(self) -> None:
        with self._lock:
            payload = {
                "lifetime_keys": self.lifetime_keys,
                "lifetime_clicks": self.lifetime_clicks,
                "by_hour": dict(self.by_hour),
                "click_grid": dict(self.click_grid),
            }
        APP_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(STATS_FILE)


class InputWatcher:
    """Wraps pynput listeners. Counting only."""

    def __init__(self, model: ActivityModel) -> None:
        self.model = model
        self._kb = None
        self._ms = None
        self.running = False
        # Best-effort screen size for the heatmap bucketing.
        self._screen_w, self._screen_h = self._detect_screen()

    @staticmethod
    def _detect_screen() -> tuple[int, int]:
        try:
            root = tk._default_root
            if root is not None:
                return root.winfo_screenwidth(), root.winfo_screenheight()
        except Exception:
            pass
        return 1920, 1080

    def _on_key_press(self, key) -> None:
        # We accept `key` because pynput passes it, but we intentionally
        # ignore its value. Only the count matters.
        self.model.add_key()

    def _on_click(self, x, y, button, pressed) -> None:
        if pressed:
            self.model.add_click(int(x), int(y), self._screen_w, self._screen_h)

    def start(self) -> None:
        if self.running:
            return
        self._kb = keyboard.Listener(on_press=self._on_key_press)
        self._ms = mouse.Listener(on_click=self._on_click)
        self._kb.start()
        self._ms.start()
        self.running = True

    def stop(self) -> None:
        for lst in (self._kb, self._ms):
            if lst is not None:
                lst.stop()
        self._kb = self._ms = None
        self.running = False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Activity Tracker — local input meter")
        self.geometry("520x620")
        self.minsize(480, 560)

        self.model = ActivityModel()
        self.watcher = InputWatcher(self.model)

        self._build_ui()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        banner = tk.Label(
            self,
            text=("This tool counts keystrokes and clicks only.\n"
                  "It does not record what you type and sends nothing "
                  "over the network."),
            fg="#0b2545", justify="center", font=("Segoe UI", 9, "italic"),
        )
        banner.pack(fill="x", **pad)

        self.status_var = tk.StringVar(value="Stopped")
        status = tk.Label(self, textvariable=self.status_var,
                          font=("Segoe UI", 11, "bold"))
        status.pack(**pad)

        btns = tk.Frame(self)
        btns.pack(**pad)
        self.toggle_btn = ttk.Button(btns, text="Start tracking",
                                     command=self._toggle)
        self.toggle_btn.grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Reset session",
                   command=self._reset).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Save now",
                   command=self._save).grid(row=0, column=2, padx=4)

        # Live numbers.
        grid = tk.Frame(self)
        grid.pack(fill="x", **pad)
        self._stat_labels = {}
        rows = [
            ("session_keys", "Keys this session"),
            ("session_clicks", "Clicks this session"),
            ("kpm", "Keys / min"),
            ("cpm", "Clicks / min"),
            ("wpm", "Approx. WPM"),
            ("elapsed", "Session time"),
            ("lifetime_keys", "Lifetime keys"),
            ("lifetime_clicks", "Lifetime clicks"),
        ]
        for i, (key, label) in enumerate(rows):
            tk.Label(grid, text=label + ":", anchor="w",
                     font=("Segoe UI", 10)).grid(row=i, column=0,
                                                 sticky="w", pady=2)
            v = tk.StringVar(value="0")
            tk.Label(grid, textvariable=v, anchor="e",
                     font=("Consolas", 11, "bold")).grid(row=i, column=1,
                                                         sticky="e", pady=2)
            grid.columnconfigure(1, weight=1)
            self._stat_labels[key] = v

        tk.Label(self, text="Today's activity (keys per hour)",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12,
                                                     pady=(10, 0))
        self.hour_canvas = tk.Canvas(self, height=120, bg="#f4f7fa",
                                     highlightthickness=1,
                                     highlightbackground="#d6dee6")
        self.hour_canvas.pack(fill="x", padx=12, pady=6)

        tk.Label(self, text="Click heatmap (where on screen you click)",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12,
                                                     pady=(10, 0))
        self.heat_canvas = tk.Canvas(self, height=150, bg="#f4f7fa",
                                     highlightthickness=1,
                                     highlightbackground="#d6dee6")
        self.heat_canvas.pack(fill="both", expand=True, padx=12, pady=6)

    # --- actions ---------------------------------------------------------
    def _toggle(self) -> None:
        if self.watcher.running:
            self.watcher.stop()
            self.status_var.set("Stopped")
            self.toggle_btn.config(text="Start tracking")
        else:
            self.watcher.start()
            self.status_var.set("Tracking — counting keys & clicks")
            self.toggle_btn.config(text="Stop tracking")

    def _reset(self) -> None:
        self.model.reset_session()

    def _save(self) -> None:
        self.model.save()
        messagebox.showinfo("Saved", f"Stats saved to:\n{STATS_FILE}")

    def _on_close(self) -> None:
        self.watcher.stop()
        self.model.save()
        self.destroy()

    # --- rendering loop --------------------------------------------------
    def _tick(self) -> None:
        snap = self.model.snapshot()
        self._stat_labels["session_keys"].set(str(snap["session_keys"]))
        self._stat_labels["session_clicks"].set(str(snap["session_clicks"]))
        self._stat_labels["kpm"].set(f"{snap['kpm']:.1f}")
        self._stat_labels["cpm"].set(f"{snap['cpm']:.1f}")
        self._stat_labels["wpm"].set(f"{snap['wpm']:.1f}")
        self._stat_labels["elapsed"].set(self._fmt_time(snap["elapsed"]))
        self._stat_labels["lifetime_keys"].set(str(snap["lifetime_keys"]))
        self._stat_labels["lifetime_clicks"].set(str(snap["lifetime_clicks"]))

        self._draw_hours(snap["by_hour"])
        self._draw_heatmap(snap["click_grid"])
        self.after(500, self._tick)

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        s = int(seconds)
        h, rem = divmod(s, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def _draw_hours(self, by_hour: dict) -> None:
        c = self.hour_canvas
        c.delete("all")
        today = datetime.now().strftime("%Y-%m-%d")
        counts = [by_hour.get(f"{today} {h:02d}", {}).get("keys", 0)
                  for h in range(24)]
        peak = max(counts) or 1
        w = c.winfo_width() or 480
        h = c.winfo_height() or 120
        bar_w = w / 24.0
        for i, val in enumerate(counts):
            bh = (val / peak) * (h - 20)
            x0 = i * bar_w + 2
            x1 = (i + 1) * bar_w - 2
            c.create_rectangle(x0, h - bh - 14, x1, h - 14,
                               fill="#2aa17a", outline="")
            if i % 3 == 0:
                c.create_text((x0 + x1) / 2, h - 6, text=f"{i:02d}",
                              font=("Segoe UI", 7), fill="#5b6b7c")

    def _draw_heatmap(self, grid: dict) -> None:
        c = self.heat_canvas
        c.delete("all")
        w = c.winfo_width() or 480
        h = c.winfo_height() or 150
        cell_w = w / GRID_COLS
        cell_h = h / GRID_ROWS
        peak = max(grid.values(), default=0) or 1
        for key, val in grid.items():
            col, row = (int(p) for p in key.split(","))
            intensity = val / peak
            shade = int(255 - intensity * 180)
            color = f"#{shade:02x}{min(255, shade + 40):02x}ff"
            c.create_rectangle(col * cell_w, row * cell_h,
                               (col + 1) * cell_w, (row + 1) * cell_h,
                               fill=color, outline="#e3e9ef")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
