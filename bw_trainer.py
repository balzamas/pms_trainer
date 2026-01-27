import json
import random
import os
import csv
import sys
import re
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox


def app_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config(filename="config.json"):
    cfg_path = os.path.join(app_dir(), filename)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    os.makedirs(os.path.join(app_dir(), "tasks"), exist_ok=True)


def pick_guest(cfg) -> dict:
    guests = cfg.get("guests", [])
    if not guests:
        raise ValueError("config.json has no 'guests' list.")

    guest = random.choice(guests)

    name = str(guest.get("full_name", "")).strip()
    if not name:
        raise ValueError("Each guest must have a non-empty 'full_name'.")

    # Defaults
    guest.setdefault("comment", "")
    guest.setdefault("min_guests", 1)
    guest.setdefault("max_guests", 99)

    # Validate
    try:
        guest["min_guests"] = int(guest["min_guests"])
        guest["max_guests"] = int(guest["max_guests"])
    except Exception as e:
        raise ValueError(f"Guest '{name}' has invalid min_guests/max_guests: {e}")

    if guest["max_guests"] < guest["min_guests"]:
        raise ValueError(f"Guest '{name}' has max_guests < min_guests.")

    return guest


def random_dates(cfg):
    """
    Arrival between earliest_arrival and latest_arrival (inclusive) in config.json booking_window.
    """
    bw = cfg.get("booking_window", {})
    earliest_str = bw.get("earliest_arrival")
    latest_str = bw.get("latest_arrival")
    if not earliest_str or not latest_str:
        raise ValueError(
            "config.json missing booking_window. Add:\n"
            '"booking_window": {"earliest_arrival":"YYYY-MM-DD","latest_arrival":"YYYY-MM-DD"}'
        )

    earliest = date.fromisoformat(earliest_str)
    latest = date.fromisoformat(latest_str)
    if latest < earliest:
        raise ValueError("booking_window.latest_arrival must be on or after booking_window.earliest_arrival")

    delta_days = (latest - earliest).days
    arrival = earliest + timedelta(days=random.randint(0, delta_days))

    nights = random.randint(cfg["stay_length_nights"]["min"], cfg["stay_length_nights"]["max"])
    departure = arrival + timedelta(days=nights)
    return arrival, departure, nights


def format_breakfast_counts(selected_types: list[str]) -> str:
    # Aggregate to "2x Normal-Frühstück, 1x Budget-Frühstück"
    counts = {}
    for t in selected_types:
        counts[t] = counts.get(t, 0) + 1
    parts = [f"{counts[name]}x {name}" for name in sorted(counts.keys())]
    return ", ".join(parts)


def generate_breakfast_service(cfg, guest_count: int):
    """
    Rules:
    - probability_any_breakfast (default 0.7): booking has breakfast at all.
    - If breakfast exists: probability_full_group_if_any (default 0.7) => breakfast_count == guest_count.
      Otherwise breakfast_count is random and NOT necessarily for everyone.
    Breakfast types can be mixed across breakfasts.
    """
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

    # 1) Any breakfast at all?
    if random.random() > p_any:
        return None

    # 2) If yes: full group in 70% of breakfast bookings, else partial
    if guest_count == 1:
        breakfast_count = 1
    else:
        if random.random() <= p_full:
            breakfast_count = guest_count
        else:
            breakfast_count = random.randint(1, guest_count - 1)

    chosen = [random.choice(types) for _ in range(breakfast_count)]
    return f"Breakfast: {format_breakfast_counts(chosen)}"


def generate_scenario(cfg):
    guest, category, guests_count = choose_compatible_guest_category_and_count(cfg)

    arrival, departure, nights = random_dates(cfg)

    # --- your existing "other services" logic stays ---
    max_services = int(cfg.get("max_services", 3))
    services_pool = list(cfg.get("extra_services", []))
    num_services = random.randint(0, min(max_services, len(services_pool))) if services_pool else 0
    other_services = random.sample(services_pool, k=num_services) if num_services > 0 else []

    # --- keep breakfast random exactly as before ---
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
        "Extra services": extra_services_str
    }

def choose_compatible_guest_category_and_count(cfg):
    """
    Returns (guest, category, guest_count) such that:
    - guest_count is valid for BOTH guest and room category constraints.
    """
    guests = cfg.get("guests", [])
    categories = cfg.get("room_categories", [])

    if not guests:
        raise ValueError("config.json has no guests.")
    if not categories:
        raise ValueError("config.json has no room_categories.")

    # Build all valid combinations
    valid = []
    for g_raw in guests:
        g = dict(g_raw)  # shallow copy so we can safely set defaults
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
            cmin = int(c["min_guests"])
            cmax = int(c["max_guests"])

            low = max(gmin, cmin)
            high = min(gmax, cmax)

            if low <= high:
                valid.append((g, c, low, high))

    if not valid:
        raise ValueError(
            "No valid guest/category combinations. Check guest min/max and room_categories min/max in config.json."
        )

    g, c, low, high = random.choice(valid)
    guest_count = random.randint(low, high)
    return g, c, guest_count


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
"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    return filename, finished_at


def append_completion_log(task_file, scenario, booking_number, finished_at, generated_id):
    log_file = os.path.join(app_dir(), "completions.csv")
    file_exists = os.path.exists(log_file)

    headers = [
        "finished_at",
        "task_id",
        "booking_number",
        "task_file",
        "guest_name",
        "guest_comment",
        "room_category",
        "guests",
        "arrival",
        "departure",
        "extra_services"
    ]

    row = {
        "finished_at": finished_at,
        "task_id": generated_id,
        "booking_number": booking_number,
        "task_file": os.path.basename(task_file),
        "guest_name": scenario.get("Guest name", ""),
        "guest_comment": scenario.get("Guest comment", ""),
        "room_category": scenario["Room category"],
        "guests": scenario["Number of guests"],
        "arrival": scenario["Arrival"],
        "departure": scenario["Departure"],
        "extra_services": scenario["Extra services"]
    }

    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PMS Training Scenario Generator")
        self.geometry("900x900")
        self.resizable(False, False)

        try:
            self.cfg = load_config("config.json")
        except Exception as e:
            messagebox.showerror("Config error", f"Could not load config.json next to the app:\n\n{e}")
            self.destroy()
            return

        self.current_scenario = None
        self.generated_id = None

        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="PMS training scenario", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

        self.output = tk.Text(main, height=18, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)

        btn_row = ttk.Frame(main)
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="New task", command=self.on_new_task).pack(side="left")
        ttk.Button(btn_row, text="Copy scenario", command=self.on_copy).pack(side="left", padx=(8, 0))

        completion = ttk.LabelFrame(main, text="Completion", padding=10)
        completion.pack(fill="x", pady=(10, 0))

        ttk.Label(completion, text="Booking number:").pack(side="left")
        self.booking_var = tk.StringVar()
        ttk.Entry(completion, textvariable=self.booking_var, width=26).pack(side="left", padx=(8, 8))

        ttk.Button(completion, text="Mark finished", command=self.on_finish).pack(side="left")
        self.status_lbl = ttk.Label(completion, text="")
        self.status_lbl.pack(side="right")

        self.on_new_task()

    def on_new_task(self):
        self.current_scenario = generate_scenario(self.cfg)
        self.generated_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

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
            "When finished in the PMS, enter the booking number and click 'Mark finished'."
        ]

        self.output.delete("1.0", "end")
        self.output.insert("1.0", "\n".join(lines))

    def on_copy(self):
        txt = self.output.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()
        messagebox.showinfo("Copied", "Scenario copied to clipboard.")

    def on_finish(self):
        if not self.current_scenario or not self.generated_id:
            messagebox.showerror("No task", "Click 'New task' first.")
            return

        booking_number = self.booking_var.get().strip()
        if not booking_number:
            messagebox.showwarning("Missing booking number", "Please enter the PMS booking number.")
            return
        if len(booking_number) < 3:
            messagebox.showwarning("Booking number too short", "Please enter a valid booking number.")
            return

        task_file, finished_at = write_task_file(self.current_scenario, booking_number, self.generated_id)
        append_completion_log(task_file, self.current_scenario, booking_number, finished_at, self.generated_id)

        self.status_lbl.config(text=f"Saved ✓ {finished_at}")

        current_txt = self.output.get("1.0", "end").strip()
        self.output.delete("1.0", "end")
        self.output.insert("1.0", current_txt + f"\n\nSaved file: {os.path.relpath(task_file, app_dir())}")

        messagebox.showinfo(
            "Finished",
            f"Saved task file and log.\n\nBooking number: {booking_number}\nFile: {os.path.basename(task_file)}"
        )


if __name__ == "__main__":
    App().mainloop()
