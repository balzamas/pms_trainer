# config_model.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List

def default_config() -> dict:
    return {
        "booking_window": {
            "earliest_arrival": "2027-01-01",
            "latest_arrival": "2027-03-01",
        },
        "stay_length_nights": {
            "min": 1,
            "max": 5,
        },
        "max_services": 3,
        "follow_up_probability": 0.33,

        # ✅ DEFAULT GUEST
        "guests": [
            {
                "full_name": "John Doe",
                "comment": "",
                "min_guests": 1,
                "max_guests": 99,
            }
        ],

        # ✅ DEFAULT ROOM CATEGORY
        "room_categories": [
            {
                "name": "Double room",
                "min_guests": 1,
                "max_guests": 2,
                # optional, new field
                "category_extras": "baby bed;balcony",
            }
        ],

        # Global extras
        "extra_services": [
            "Late check-in",
            "Parking",
            "Pet",
        ],

        "follow_up_tasks": [
            "Extend booking by one night",
            "Add another room or bed",
            "Move booking to another room category"
        ],

        "breakfast_policy": {
            "enabled": False,
            "probability_any_breakfast": 0.7,
            "probability_full_group_if_any": 0.7,
        },

        "breakfast_types": [
            "Continental",
            "Vegan",
        ],
    }

def normalize_config(cfg: dict) -> dict:
    # ensures keys exist; mirrors your ensure_defaults()
    base = default_config()

    # shallow merge:
    for k, v in cfg.items():
        base[k] = v

    base.setdefault("guests", [])
    base.setdefault("room_categories", [])
    base.setdefault("extra_services", [])
    base.setdefault("follow_up_tasks", [])

    base.setdefault("booking_window", default_config()["booking_window"])
    base.setdefault("stay_length_nights", default_config()["stay_length_nights"])
    base.setdefault("breakfast_types", default_config()["breakfast_types"])
    base.setdefault("breakfast_policy", default_config()["breakfast_policy"])

    return base

def validate_config(cfg: dict) -> list[str]:
    errors: list[str] = []

    # booking window
    try:
        ea = date.fromisoformat(cfg["booking_window"]["earliest_arrival"])
        la = date.fromisoformat(cfg["booking_window"]["latest_arrival"])
        if la < ea:
            errors.append("Latest arrival must be on or after earliest arrival.")
    except Exception:
        errors.append("Booking window dates must be valid ISO dates (YYYY-MM-DD).")

    # stay length
    try:
        mn = int(cfg["stay_length_nights"]["min"])
        mx = int(cfg["stay_length_nights"]["max"])
        if mx < mn:
            errors.append("Stay max nights must be >= stay min nights.")
        if mn < 1:
            errors.append("Stay min nights must be >= 1.")
    except Exception:
        errors.append("Stay length min/max must be integers.")

    # max services
    try:
        ms = int(cfg.get("max_services", 3))
        if ms < 0:
            errors.append("Max extra services must be >= 0.")
    except Exception:
        errors.append("Max extra services must be an integer.")

    # follow-up probability
    try:
        p = float(cfg.get("follow_up_probability", 0.33))
        if p < 0 or p > 1:
            errors.append("Follow-up probability must be between 0 and 1.")
    except Exception:
        errors.append("Follow-up probability must be a number.")

    # guests
    for i, g in enumerate(cfg.get("guests", [])):
        name = str(g.get("full_name", "")).strip()
        if not name:
            errors.append(f"Guests[{i}].full_name is empty.")
        try:
            gmin = int(g.get("min_guests", 1))
            gmax = int(g.get("max_guests", 99))
            if gmax < gmin:
                errors.append(f"Guests[{i}] max_guests must be >= min_guests.")
        except Exception:
            errors.append(f"Guests[{i}] min_guests/max_guests must be integers.")

    # categories
    for i, c in enumerate(cfg.get("room_categories", [])):
        name = str(c.get("name", "")).strip()
        if not name:
            errors.append(f"RoomCategories[{i}].name is empty.")
        try:
            cmin = int(c.get("min_guests", 1))
            cmax = int(c.get("max_guests", 1))
            if cmax < cmin:
                errors.append(f"RoomCategories[{i}] max_guests must be >= min_guests.")
        except Exception:
            errors.append(f"RoomCategories[{i}] min_guests/max_guests must be integers.")

    return errors
