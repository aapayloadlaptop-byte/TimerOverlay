import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import subprocess
import threading
import re
import shutil

APP_TITLE = "FPV Millisecond Timer Overlay"

def parse_time(value):
    """Accept seconds, M:SS.mmm, or H:MM:SS.mmm."""
    s = value.strip()
    if not s:
        raise ValueError("Enter a zero-point timestamp.")
    if re.fullmatch(r"\d+(\.\d{1,3})?", s):
        return float(s)
    parts = s.split(":")
    if len(parts) == 2:
        m, sec = parts
        result = int(m) * 60 + float(sec)
    elif len(parts) == 3:
        h, m, sec = parts
        result = int(h) * 3600 + int(m) * 60 + float(sec)
    else:
        raise ValueError("Use seconds, M:SS.mmm, or H:MM:SS.mmm.")
    if result < 0:
        raise ValueError("Timestamp cannot be negative.")
    return result

def ffmpeg_path():
    local = Path(__file__).resolve().parent / "ffmpeg.exe"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    return found

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("660x390")
        self.minsize(600, 360)
        self.video = tk.StringVar()
        self.zero = tk.StringVar(value="0:12.321")
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="Choose a video, then set the video timestamp where the timer should read 00:00.000.")
        self._build()

    def _build(self):
        pad = {"padx": 12, "pady": 7}
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="FPV Millisecond Timer Overlay", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))

        ttk.Label(root, text="Input video").pack(anchor="w")
        row = ttk.Frame(root); row.pack(fill="x", **pad)
        ttk.Entry(row, textvariable=self.video).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.pick_video).pack(side="left", padx=(8, 0))

        ttk.Label(root, text="Video timestamp where the timer should start at 00:00.000").pack(anchor="w")
        ttk.Entry(root, textvariable=self.zero, width=22).pack(anchor="w", padx=12, pady=(2, 8))
        ttk.Label(root, text="Examples: 12.321   |   0:12.321   |   1:02:12.321", foreground="#555").pack(anchor="w", padx=12)

        ttk.Label(root, text="Output video").pack(anchor="w", pady=(10, 0))
        row2 = ttk.Frame(root); row2.pack(fill="x", **pad)
        ttk.Entry(row2, textvariable=self.output).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Save as…", command=self.pick_output).pack(side="left", padx=(8, 0))

        opts = ttk.Frame(root); opts.pack(fill="x", padx=12, pady=5)
        ttk.Label(opts, text="Timer: HH:MM:SS.mmm  •  Top-left  •  White text / translucent black box").pack(anchor="w")
        ttk.Label(opts, text="The timer stays hidden before the selected zero point.", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

        self.run_btn = ttk.Button(root, text="Create video with timer", command=self.start)
        self.run_btn.pack(anchor="w", padx=12, pady=12)
        ttk.Label(root, textvariable=self.status, wraplength=610).pack(anchor="w", padx=12, pady=(2, 0))

    def pick_video(self):
        p = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.m4v"), ("All files", "*.*")])
        if p:
            self.video.set(p)
            src = Path(p)
            self.output.set(str(src.with_name(src.stem + "_timer.mp4")))

    def pick_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 video", "*.mp4")])
        if p:
            self.output.set(p)

    def start(self):
        src = Path(self.video.get())
        dst = Path(self.output.get())
        if not src.is_file():
            messagebox.showerror("Missing video", "Choose a valid input video.")
            return
        if not str(dst):
            messagebox.showerror("Missing output", "Choose an output filename.")
            return
        try:
            offset = parse_time(self.zero.get())
        except Exception as e:
            messagebox.showerror("Invalid timestamp", str(e))
            return
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            messagebox.showerror("FFmpeg not found", "Place ffmpeg.exe in the same folder as this app, or install FFmpeg and add it to PATH.")
            return
        if src.resolve() == dst.resolve():
            messagebox.showerror("Invalid output", "Choose a different output filename so the original is preserved.")
            return

        self.run_btn.config(state="disabled")
        self.status.set("Processing… Large videos may take a while.")
        threading.Thread(target=self.render, args=(ffmpeg, src, dst, offset), daemon=True).start()

    def render(self, ffmpeg, src, dst, offset):
        # Shift video presentation timestamps so the chosen source point becomes t=0.
        # drawtext is enabled only for t >= 0, so no negative/pre-start timer is shown.
        off = f"{offset:.3f}"
        vf = (
            f"setpts=PTS-STARTPTS-{off}/TB,"
            "drawtext=font='Arial':"
            "text='%{pts\\:hms}':"
            "fontsize=42:fontcolor=white:"
            "box=1:boxcolor=black@0.60:boxborderw=12:"
            "x=24:y=24:enable='gte(t,0)'"
        )
        cmd = [
            ffmpeg, "-hide_banner", "-y", "-i", str(src),
            "-vf", vf, "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", str(dst)
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout)[-3500:]
                self.after(0, lambda: self.finish_error(tail))
            else:
                self.after(0, lambda: self.finish_ok(dst))
        except Exception as e:
            self.after(0, lambda: self.finish_error(str(e)))

    def finish_ok(self, dst):
        self.run_btn.config(state="normal")
        self.status.set(f"Finished: {dst}")
        messagebox.showinfo("Complete", f"Timer video created:\n{dst}")

    def finish_error(self, detail):
        self.run_btn.config(state="normal")
        self.status.set("Export failed. See error details.")
        messagebox.showerror("FFmpeg export failed", detail)

if __name__ == "__main__":
    App().mainloop()
