# Activity Tracker — local input-activity meter

A small, **visible, local** desktop app that counts how often you type and
click, and shows the numbers live. Like a step counter for your hands —
useful for productivity tracking, typing cadence, and RSI / ergonomics
awareness.

## What it does

- Counts **keystrokes** and **mouse clicks** in real time.
- Shows keys/min, clicks/min, an approximate WPM, and session time.
- Draws a per-hour activity chart for the day and a coarse click heatmap
  (where on the screen clicks land).
- Persists lifetime totals locally to `~/.activity_tracker/stats.json`.

## What it deliberately does **not** do

- **No key logging.** The keyboard callback (`_on_key_press`) ignores which
  key was pressed — it only increments a counter. Typed text (passwords,
  messages, URLs) is never read or stored. There is no code path that can.
- **No network.** No HTTP client, socket, or webhook is imported or used.
  Nothing leaves your machine.
- **Nothing hidden.** It opens a normal window, shows a live status, and you
  start and stop it yourself. Closing the window stops tracking and saves.

## Install & run

```bash
pip install pynput
python3 activity_tracker.py
```

Tkinter ships with the standard CPython installers on Windows and macOS. On
Linux, install your distro's Tk package (e.g. `sudo apt install python3-tk`).

> On macOS you'll be asked to grant the terminal/Python **Accessibility** and
> **Input Monitoring** permission so `pynput` can observe input events. This
> is the OS making input observation explicit and consensual — as it should
> be.

## Data & reset

All data lives in `~/.activity_tracker/stats.json`. Delete that file to reset
lifetime totals. "Reset session" in the UI clears only the current session's
counters.
