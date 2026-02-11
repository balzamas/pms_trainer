# scenario.py
from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta
from typing import Optional


# -------------------- helpers --------------------

def parse_category_extras(value) -> list[str]:
    """
    Accepts either:
      - a string like "Baby bed; Extra bed; 2x Children"
      - a list like ["Baby bed", "Extra bed"]
    Returns a clean list of strings.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(";") if x.strip()]
    return []


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for s in items:
        s = str(s).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


# -------------------- scenario generation (from main.py) --------------------

def choose_compatible_guest_category_and_count(cfg: dict):
    guests = cfg.get("guests", [])
    categories = cfg.get("room_categories", [])

    if not guests:
        raise ValueError("Config has no guests.")
    if not categories:
        raise ValueError("Config has no room_categories.")

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

        for c_raw in categories:
            c = dict(c_raw)
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
        raise ValueError(
            "No valid guest/category combinations. "
            "Check guest/room min/max in config."
        )

    g, c, low, high = random.choice(valid)
    guest_count = random.randint(low, high)
    return g, c, guest_count


def random_dates(cfg: dict):
    bw = cfg.get("booking_window", {})
    earliest_str = bw.get("earliest_arrival")
    latest_str = bw.get("latest_arrival")
    if not earliest_str or not latest_str:
        raise ValueError(
            "Config missing booking_window. Add:\n"
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
    counts: dict[str, int] = {}
    for t in selected_types:
        counts[t] = counts.get(t, 0) + 1
    parts = [f"{counts[name]}x {name}" for name in sorted(counts.keys())]
    return ", ".join(parts)


def generate_breakfast_service(cfg: dict, guest_count: int) -> Optional[str]:
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
    return f"{format_breakfast_counts(chosen)}"


def generate_scenario(cfg: dict) -> dict:
    guest, category, guests_count = choose_compatible_guest_category_and_count(cfg)
    arrival, departure, nights = random_dates(cfg)

    max_services = int(cfg.get("max_services", 3))
    
    global_pool = list(cfg.get("extra_services", []))
    category_pool = parse_category_extras(category.get("category_extras", ""))
    
    # Combined pool: globals + room-specific for this room type
    pool = unique_keep_order(global_pool + category_pool)
    
    max_possible = min(max_services, len(pool))
    num_services = random.randint(0, max_possible) if max_possible > 0 else 0
    
    other_services: list[str] = random.sample(pool, k=num_services) if num_services > 0 else []


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


# -------------------- follow-up helpers (from main.py) --------------------

def pick_random_followup(cfg: dict) -> Optional[str]:
    tasks = cfg.get("follow_up_tasks", [])
    tasks = [t.strip() for t in tasks if isinstance(t, str) and t.strip()]
    if not tasks:
        return None
    return random.choice(tasks)


def should_generate_followup(cfg: dict) -> bool:
    p = cfg.get("follow_up_probability", 1.0 / 3.0)
    try:
        p = float(p)
    except Exception:
        p = 1.0 / 3.0
    p = max(0.0, min(1.0, p))
    return random.random() < p


# -------------------- rendering (web/download) --------------------

def sanitize_for_filename(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^A-Za-z0-9._-]", "", text)
    return text[:40] if text else "UNKNOWN"

def render_task_text(
    scenario: dict,
    booking_number: str,
    generated_id: str,
    followup: Optional[str],
) -> str:
    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    guest_comment = scenario.get("Guest comment", "")
    guest_comment_part = f" | Comment: {guest_comment}" if guest_comment else ""

    lines = [
        f"PMS TRAINING TASK | ID: {generated_id} | Booking: {booking_number} | Finished: {finished_at}",
        "",
        f"Guest: {scenario.get('Guest name','')}{guest_comment_part}",
        f"Room: {scenario.get('Room category','')}",
        f"Guests: {scenario.get('Number of guests','')}",
        f"Arrival: {scenario.get('Arrival','')} | Departure: {scenario.get('Departure','')} | Nights: {scenario.get('Nights','')}",
        f"Extras: {scenario.get('Extra services','')}",
    ]

    if followup:
        lines.append(f"Follow-up: {followup}")

    return "\n".join(lines)


