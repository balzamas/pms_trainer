import json
import random
import os
import sys
import re
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk
from typing import Optional

from config_editor import ConfigEditor  # <-- second file


APP_TITLE = "PMS Training Scenario Generator"
CONFIG_FILENAME = "config.json"

# Author: d.berger@dontsniff.co.uk
# Version: 0.1.0

# -------------------- file helpers --------------------

def app_dir() -> str:
    # Works for PyInstaller onefile/onedir and normal python run
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILENAME)


def load_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    """
    Saves config.json with a backup config.json.bak next to it.
    """
    path = config_path()
    bak = path + ".bak"

    if os.path.exists(path):
        try:
            with open(path, "rb") as src, open(bak, "wb") as dst:
                dst.write(src.read())
        except Exception:
            pass

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def ensure_dirs():
    os.makedirs(os.path.join(app_dir(), "tasks"), exist_ok=True)


# -------------------- UI helpers --------------------

def show_popup(parent, title: str, message: str, *, width=860, height=580):
    """
    Robust popup with ALWAYS-visible OK button.
    Uses grid + scrollable read-only Text so the button never gets pushed out.
    """
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.resizable(True, True)
    win.transient(parent)
    win.grab_set()

    win.columnconfigure(0, weight=1)
    win.rowconfigure(1, weight=1)

    header = ttk.Frame(win, padding=(16, 12, 16, 6))
    header.grid(row=0, column=0, sticky="ew")
    ttk.Label(header, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w")

    content = ttk.Frame(win, padding=(16, 6, 16, 6))
    content.grid(row=1, column=0, sticky="nsew")
    content.columnconfigure(0, weight=1)
    content.rowconfigure(0, weight=1)

    scrollbar = ttk.Scrollbar(content, orient="vertical")
    scrollbar.grid(row=0, column=1, sticky="ns")

    text = tk.Text(
        content,
        wrap="word",
        font=("Segoe UI", 10),
        yscrollcommand=scrollbar.set,
        borderwidth=1,
        relief="solid",
    )
    text.grid(row=0, column=0, sticky="nsew")
    scrollbar.config(command=text.yview)

    text.insert("1.0", message)
    text.config(state="disabled")

    buttons = ttk.Frame(win, padding=(16, 6, 16, 12))
    buttons.grid(row=2, column=0, sticky="ew")
    buttons.columnconfigure(0, weight=1)

    ok_btn = ttk.Button(buttons, text="OK", command=win.destroy)
    ok_btn.grid(row=0, column=1, sticky="e")

    parent.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")

    win.bind("<Return>", lambda _e: win.destroy())
    win.bind("<Escape>", lambda _e: win.destroy())
    ok_btn.focus_set()
    return win


# -------------------- scenario generation --------------------

def choose_compatible_guest_category_and_count(cfg):
    guests = cfg.get("guests", [])
    categories = cfg.get("room_categories", [])

    if not guests:
        raise ValueError("config.json has no guests.")
    if not categories:
        raise ValueError("config.json has no room_categories.")

    valid = []
    for g_raw in guests:
        g = dict(g_raw)
        name = str(g.get("full_name", "")).strip()
        if not name:
            continue

        g.setdefault("comment", "")
        g.setdefault("min_guests", 1)
        g.setdefault("max_guests", 99)

        try:
            gmin = int(g["min_guests"])
            gmax = int(g["max_guests"])
        except Exception:
            continue
        if gmax < gmin:
            continue

        for c in categories:
            try:
                cmin = int(c.get("min_guests", 1))
                cmax = int(c.get("max_guests", 1))
            except Exception:
                continue
            low = max(gmin, cmin)
            high = min(gmax, cmax)
            if low <= high:
                valid.append((g, c, low, high))

    if not valid:
        raise ValueError("No valid guest/category combinations. Check guest/room min/max in config.json.")

    g, c, low, high = random.choice(valid)
    guest_count = random.randint(low, high)
    return g, c, guest_count


def random_dates(cfg):
    bw = cfg.get("booking_window", {})
    earliest_str = bw.get("earliest_arrival")
    latest_str = bw.get("latest_arrival")
    if not earliest_str or not latest_str:
        raise ValueError(
            "config.json missing booking_window.\n\nAdd:\n"
            '"booking_window": {"earliest_arrival":"YYYY-MM-DD","latest_arrival":"YYYY-MM-DD"}'
        )

    earliest = date.fromisoformat(earliest_str)
    latest = date.fromisoformat(latest_str)
    if latest < earliest:
        raise ValueError("booking_window.latest_arrival must be on or after booking_window.earliest_arrival")

    delta_days = (latest - earliest).days
    arrival = earliest + timedelta(days=random.randint(0, delta_days))

    stay = cfg.get("stay_length_nights", {"min": 1, "max": 5})
    nights = random.randint(int(stay["min"]), int(stay["max"]))
    departure = arrival + timedelta(days=nights)
    return arrival, departure, nights


def format_breakfast_counts(selected_types: list[str]) -> str:
    counts = {}
    for t in selected_types:
        counts[t] = counts.get(t, 0) + 1
    parts = [f"{counts[name]}x {name}" for name in sorted(counts.keys())]
    return ", ".join(parts)


def generate_breakfast_service(cfg, guest_count: int) -> Optional[str]:
    policy = cfg.get("breakfast_policy", {})
    if not bool(policy.get("enabled", False)):
        return None

    types = cfg.get("breakfast_types", [])
    if not types or guest_count <= 0:
        return None

    p_any = float(policy.get("probability_any_breakfast", 0.7))
    p_full = float(policy.get("probability_full_group_if_any", 0.7))
    p_any = max(0.0, min(1.0, p_any))
    p_full = max(0.0, min(1.0, p_full))

    if random.random() > p_any:
        return None

    if guest_count == 1:
        breakfast_count = 1
    else:
        breakfast_count = guest_count if random.random() <= p_full else random.randint(1, guest_count - 1)

    chosen = [random.choice(types) for _ in range(breakfast_count)]
    return f"Breakfast: {format_breakfast_counts(chosen)}"


def generate_scenario(cfg):
    guest, category, guests_count = choose_compatible_guest_category_and_count(cfg)
    arrival, departure, nights = random_dates(cfg)

    max_services = int(cfg.get("max_services", 3))
    services_pool = list(cfg.get("extra_services", []))
    num_services = random.randint(0, min(max_services, len(services_pool))) if services_pool else 0
    other_services = random.sample(services_pool, k=num_services) if num_services > 0 else []

    breakfast_service = generate_breakfast_service(cfg, guests_count)
    if breakfast_service:
        other_services = [breakfast_service] + other_services

    extra_services_str = ", ".join(other_services) if other_services else "(none)"

    return {
        "Guest name": guest["full_name"],
        "Guest comment": str(guest.get("comment", "")).strip(),
        "Room category": category["name"],
        "Number of guests": guests_count,
        "Arrival": arrival.isoformat(),
        "Departure": departure.isoformat(),
        "Nights": nights,
        "Extra services": extra_services_str,
    }


def sanitize_for_filename(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^A-Za-z0-9._-]", "", text)
    return text[:40] if text else "UNKNOWN"


def write_task_file(scenario, booking_number: str, generated_id: str):
    ensure_dirs()

    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_bn = sanitize_for_filename(booking_number)
    filename = os.path.join(app_dir(), "tasks", f"PMS_Task_{generated_id}_BN-{safe_bn}.txt")

    guest_comment = scenario.get("Guest comment", "")
    guest_comment_line = f"\nGuest comment:    {guest_comment}" if guest_comment else ""

    content = f"""PMS TRAINING TASK
=================

TASK ID:          {generated_id}
Booking number:   {booking_number}
Finished at:      {finished_at}

SCENARIO
--------
Guest name:       {scenario['Guest name']}{guest_comment_line}
Room category:    {scenario['Room category']}
Guests:           {scenario['Number of guests']}
Arrival:          {scenario['Arrival']}
Departure:        {scenario['Departure']}
Nights:           {scenario['Nights']}
Extra services:   {scenario['Extra services']}

FOLLOW-UPS
----------
"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    return filename, finished_at


def append_followup_to_task(task_file: str, followup_text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(task_file, "a", encoding="utf-8") as f:
        f.write(f"\n- {ts}: {followup_text}\n")


def pick_random_followup(cfg) -> Optional[str]:
    tasks = cfg.get("follow_up_tasks", [])
    tasks = [t.strip() for t in tasks if isinstance(t, str) and t.strip()]
    if not tasks:
        return None
    return random.choice(tasks)


def should_generate_followup(cfg) -> bool:
    p = cfg.get("follow_up_probability", 1.0 / 3.0)
    try:
        p = float(p)
    except Exception:
        p = 1.0 / 3.0
    p = max(0.0, min(1.0, p))
    return random.random() < p


# -------------------- main app --------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.title(APP_TITLE)
        self.geometry("900x900")
        self.resizable(False, False)

        style.configure(".", font=("Segoe UI", 10))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))

        try:
            self.cfg = load_config()
        except Exception as e:
            show_popup(
                self,
                "Config error",
                f"Could not load {CONFIG_FILENAME} next to the app.\n\n{e}",
                width=900,
                height=520,
            )
            self.after(50, self.destroy)
            return

        self.current_scenario = None
        self.generated_id = None
        self.last_task_file = None

        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="PMS training scenario", style="Header.TLabel").pack(anchor="w", pady=(0, 10))

        self.output = tk.Text(main, height=22, wrap="word", font=("Consolas", 9))
        self.output.pack(fill="both", expand=True)

        btn_row = ttk.Frame(main)
        btn_row.pack(fill="x", pady=(10, 0))

        ttk.Button(btn_row, text="New task", command=self.on_new_task).pack(side="left")
        ttk.Button(btn_row, text="Copy scenario", command=self.on_copy).pack(side="left", padx=(8, 0))
        ttk.Button(btn_row, text="Edit config", command=self.on_edit_config).pack(side="left", padx=(8, 0))

        completion = ttk.LabelFrame(main, text="Completion", padding=10)
        completion.pack(fill="x", pady=(10, 0))

        ttk.Label(completion, text="Booking number:").pack(side="left")
        self.booking_var = tk.StringVar()
        ttk.Entry(completion, textvariable=self.booking_var, width=26).pack(side="left", padx=(8, 8))

        ttk.Button(completion, text="Mark finished", command=self.on_finish).pack(side="left")
        self.status_lbl = ttk.Label(completion, text="")
        self.status_lbl.pack(side="right")

        self.on_new_task()

    def on_edit_config(self):
        def on_save(new_cfg: dict):
            self.cfg = new_cfg
            try:
                save_config(self.cfg)
                show_popup(self, "Saved", "Config saved successfully.", width=700, height=380)
            except Exception as e:
                show_popup(self, "Save error", f"Could not save config.\n\n{e}", width=900, height=520)

        ConfigEditor(self, self.cfg, on_save_callback=on_save)

    def on_new_task(self):
        try:
            self.current_scenario = generate_scenario(self.cfg)
        except Exception as e:
            show_popup(self, "Scenario error", str(e), width=900, height=520)
            return

        self.generated_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.last_task_file = None

        self.booking_var.set("")
        self.status_lbl.config(text="")

        s = self.current_scenario
        guest_comment = s.get("Guest comment", "")
        guest_comment_line = f"\nGuest comment:    {guest_comment}" if guest_comment else ""

        lines = [
            f"Task ID:          {self.generated_id}",
            "",
            f"Guest name:       {s['Guest name']}{guest_comment_line}",
            f"Room category:    {s['Room category']}",
            f"Guests:           {s['Number of guests']}",
            f"Arrival:          {s['Arrival']}",
            f"Departure:        {s['Departure']}",
            f"Nights:           {s['Nights']}",
            f"Extra services:   {s['Extra services']}",
            "",
            "No file is saved yet.",
            "When finished in the PMS, enter the booking number and click 'Mark finished'.",
        ]

        self.output.delete("1.0", "end")
        self.output.insert("1.0", "\n".join(lines))

    def on_copy(self):
        txt = self.output.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()
        show_popup(self, "Copied", "Scenario copied to clipboard.", width=700, height=380)

    def on_finish(self):
        if not self.current_scenario or not self.generated_id:
            show_popup(self, "No task", "Click 'New task' first.", width=700, height=380)
            return

        booking_number = self.booking_var.get().strip()
        if not booking_number:
            show_popup(self, "Missing booking number", "Please enter the PMS booking number.", width=760, height=420)
            return
        if len(booking_number) < 3:
            show_popup(self, "Booking number too short", "Please enter a valid booking number.", width=760, height=420)
            return

        try:
            task_file, finished_at = write_task_file(self.current_scenario, booking_number, self.generated_id)
        except Exception as e:
            show_popup(self, "Save error", f"Could not save task file.\n\n{e}", width=900, height=520)
            return

        self.last_task_file = task_file

        followup: Optional[str] = None
        if should_generate_followup(self.cfg):
            followup = pick_random_followup(self.cfg)
            if followup:
                try:
                    append_followup_to_task(task_file, followup)
                except Exception as e:
                    show_popup(self, "Follow-up error", f"Could not append follow-up.\n\n{e}", width=900, height=520)
                    followup = None

        self.status_lbl.config(text=f"Saved ✓ {finished_at}")

        # Update main text (no "no follow-up" line)
        extra_lines = [f"\nSaved file: {os.path.relpath(task_file, app_dir())}"]
        if followup:
            extra_lines.append(f"Random follow-up: {followup}")

        current_txt = self.output.get("1.0", "end").strip()
        self.output.delete("1.0", "end")
        self.output.insert("1.0", current_txt + "\n\n" + "\n".join(extra_lines))

        # Popup (no "no follow-up" if none)
        msg = (
            f"Saved task file.\n\n"
            f"Booking number: {booking_number}\n"
            f"File: {os.path.basename(task_file)}"
        )
        if followup:
            msg += f"\n\nRandom follow-up:\n{followup}"

        show_popup(self, "Task finished", msg, width=900, height=560)


if __name__ == "__main__":
    App().mainloop()
