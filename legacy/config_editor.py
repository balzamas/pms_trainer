import json
import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta
from typing import Optional, List, Tuple


# -------------------- small UI helpers --------------------

def show_popup(parent, title: str, message: str, *, width=860, height=580):
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


def ask_confirm(parent, title: str, message: str) -> bool:
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("560x280")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    win.columnconfigure(0, weight=1)

    ttk.Label(
        win, text=title, font=("Segoe UI", 12, "bold")
    ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))

    body = ttk.Frame(win, padding=(16, 8, 16, 8))
    body.grid(row=1, column=0, sticky="nsew")
    ttk.Label(body, text=message, wraplength=520, justify="left").pack(anchor="w")

    btns = ttk.Frame(win, padding=(16, 8, 16, 12))
    btns.grid(row=2, column=0, sticky="ew")
    btns.columnconfigure(0, weight=1)

    result = {"ok": False}

    def yes():
        result["ok"] = True
        win.destroy()

    def no():
        win.destroy()

    ttk.Button(btns, text="Cancel", command=no).grid(row=0, column=0, sticky="e", padx=(0, 8))
    ttk.Button(btns, text="Yes", command=yes).grid(row=0, column=1, sticky="e")

    win.bind("<Escape>", lambda _e: no())
    win.bind("<Return>", lambda _e: yes())

    parent.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (560 // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (280 // 2)
    win.geometry(f"560x280+{x}+{y}")

    win.wait_window()
    return bool(result["ok"])


def ask_text(parent, title: str, label: str, initial: str = "", *, width=600, height=260) -> Optional[str]:
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    frm = ttk.Frame(win, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w")
    var = tk.StringVar(value=initial)
    ent = ttk.Entry(frm, textvariable=var)
    ent.pack(fill="x", pady=(8, 12))
    ent.focus_set()
    ent.selection_range(0, "end")

    res = {"val": None}

    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    btns.columnconfigure(0, weight=1)

    def ok():
        res["val"] = var.get().strip()
        win.destroy()

    def cancel():
        win.destroy()

    ttk.Button(btns, text="Cancel", command=cancel).grid(row=0, column=0, sticky="e", padx=(0, 8))
    ttk.Button(btns, text="OK", command=ok).grid(row=0, column=1, sticky="e")

    win.bind("<Return>", lambda _e: ok())
    win.bind("<Escape>", lambda _e: cancel())

    parent.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")

    win.wait_window()
    return res["val"]


def edit_item_dialog(parent, title: str, fields: List[Tuple[str, str]], initial: Optional[dict] = None,
                     *, width=760, height=420) -> Optional[dict]:
    """
    fields: list of (key, label)
    Returns dict with keys filled. Cancel -> None.
    """
    initial = initial or {}
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    frm = ttk.Frame(win, padding=16)
    frm.pack(fill="both", expand=True)

    vars_: dict[str, tk.StringVar] = {}

    for key, label in fields:
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text=label, width=18).pack(side="left")
        v = tk.StringVar(value=str(initial.get(key, "") if initial.get(key, "") is not None else ""))
        vars_[key] = v
        ttk.Entry(row, textvariable=v).pack(side="left", fill="x", expand=True)

    res = {"val": None}

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))
    btns.columnconfigure(0, weight=1)

    def ok():
        res["val"] = {k: v.get().strip() for k, v in vars_.items()}
        win.destroy()

    def cancel():
        win.destroy()

    ttk.Button(btns, text="Cancel", command=cancel).grid(row=0, column=0, sticky="e", padx=(0, 8))
    ttk.Button(btns, text="Save", command=ok).grid(row=0, column=1, sticky="e")

    win.bind("<Escape>", lambda _e: cancel())
    win.bind("<Return>", lambda _e: ok())

    parent.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")

    win.wait_window()
    return res["val"]


# -------------------- config helpers --------------------

def ensure_defaults(cfg: dict) -> dict:
    cfg = dict(cfg)

    cfg.setdefault(
        "booking_window",
        {
            "earliest_arrival": date.today().isoformat(),
            "latest_arrival": (date.today() + timedelta(days=90)).isoformat(),
        },
    )
    cfg.setdefault("stay_length_nights", {"min": 1, "max": 5})
    cfg.setdefault("max_services", 3)
    cfg.setdefault("follow_up_probability", 0.33)

    cfg.setdefault("guests", [])
    cfg.setdefault("room_categories", [])
    cfg.setdefault("extra_services", [])
    cfg.setdefault("follow_up_tasks", [])

    # breakfast stays json-only
    cfg.setdefault("breakfast_types", [])
    cfg.setdefault(
        "breakfast_policy",
        {"enabled": False, "probability_any_breakfast": 0.7, "probability_full_group_if_any": 0.7},
    )

    return cfg


def validate_iso_date(s: str) -> None:
    date.fromisoformat(s)  # raises if invalid


def validate_int(s: str, field: str) -> int:
    try:
        return int(s)
    except Exception:
        raise ValueError(f"{field} must be an integer.")


# -------------------- Config Editor window --------------------

class ConfigEditor(tk.Toplevel):
    def __init__(self, parent, cfg: dict, on_save_callback):
        super().__init__(parent)
        self.parent = parent
        self.title("Config editor")
        self.geometry("1080x780")          # bigger by default
        self.minsize(980, 720)             # avoids squeezed layout
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.cfg = ensure_defaults(cfg)
        self.on_save_callback = on_save_callback

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # ✅ Fix “squeezed / lines not visible” Treeview on some systems/themes
        style.configure("Treeview", rowheight=30)  # bigger rows
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        try:
            style.configure("Treeview.Heading", padding=(8, 6))  # not supported everywhere, safe to try
        except Exception:
            pass

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        outer = ttk.Frame(self, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self.nb = ttk.Notebook(outer)
        self.nb.grid(row=0, column=0, sticky="nsew")

        self._build_general_tab()
        self._build_guests_tab()
        self._build_categories_tab()
        self._build_services_tab()
        self._build_advanced_tab()

        btns = ttk.Frame(outer)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btns.columnconfigure(0, weight=1)

        ttk.Button(btns, text="Close", command=self.destroy).grid(row=0, column=0, sticky="e", padx=(0, 8))
        ttk.Button(btns, text="Save", command=self._on_save).grid(row=0, column=1, sticky="e")

        self.bind("<Escape>", lambda _e: self.destroy())

        # center
        self.parent.update_idletasks()
        w, h = 1080, 780
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (w // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- tabs ----------

    def _build_general_tab(self):
        tab = ttk.Frame(self.nb, padding=14)
        tab.columnconfigure(1, weight=1)
        self.nb.add(tab, text="General")

        bw = self.cfg.get("booking_window", {})
        stay = self.cfg.get("stay_length_nights", {})

        self.var_earliest = tk.StringVar(value=str(bw.get("earliest_arrival", "")))
        self.var_latest = tk.StringVar(value=str(bw.get("latest_arrival", "")))
        self.var_stay_min = tk.StringVar(value=str(stay.get("min", "")))
        self.var_stay_max = tk.StringVar(value=str(stay.get("max", "")))
        self.var_max_services = tk.StringVar(value=str(self.cfg.get("max_services", 3)))

        p = float(self.cfg.get("follow_up_probability", 0.33) or 0.0)
        p = max(0.0, min(1.0, p))
        self.var_followup_pct = tk.StringVar(value=str(int(round(p * 100))))

        def row(r, label, var, hint=""):
            ttk.Label(tab, text=label).grid(row=r, column=0, sticky="w", pady=6)
            ttk.Entry(tab, textvariable=var).grid(row=r, column=1, sticky="ew", pady=6)
            if hint:
                ttk.Label(tab, text=hint).grid(row=r, column=2, sticky="w", padx=(10, 0))

        row(0, "Earliest arrival", self.var_earliest, "YYYY-MM-DD")
        row(1, "Latest arrival", self.var_latest, "YYYY-MM-DD")
        row(2, "Stay length min nights", self.var_stay_min)
        row(3, "Stay length max nights", self.var_stay_max)
        row(4, "Max extra services", self.var_max_services)
        row(5, "Follow-up chance (%)", self.var_followup_pct, "e.g. 33 = ~every third task")

        ttk.Label(tab, text="Tip: Breakfast settings stay in JSON (Advanced tab).").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(18, 0)
        )

    def _build_guests_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.nb.add(tab, text="Guests")

        cols = ("full_name", "comment", "min_guests", "max_guests")
        self.guest_tree = ttk.Treeview(tab, columns=cols, show="headings")
        self.guest_tree.grid(row=0, column=0, sticky="nsew")

        self.guest_tree.heading("full_name", text="Full name")
        self.guest_tree.heading("comment", text="Comment")
        self.guest_tree.heading("min_guests", text="Min guests")
        self.guest_tree.heading("max_guests", text="Max guests")

        # ✅ Make columns less squeezed + allow stretching
        self.guest_tree.column("full_name", width=280, minwidth=180, stretch=True)
        self.guest_tree.column("comment", width=520, minwidth=260, stretch=True)
        self.guest_tree.column("min_guests", width=120, minwidth=100, anchor="center", stretch=False)
        self.guest_tree.column("max_guests", width=120, minwidth=100, anchor="center", stretch=False)

        y = ttk.Scrollbar(tab, orient="vertical", command=self.guest_tree.yview)
        y.grid(row=0, column=1, sticky="ns")
        self.guest_tree.configure(yscrollcommand=y.set)

        btns = ttk.Frame(tab)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Add", command=self._guest_add).pack(side="left")
        ttk.Button(btns, text="Edit", command=self._guest_edit).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Delete", command=self._guest_delete).pack(side="left", padx=(8, 0))

        self._refresh_guest_tree()

    def _build_categories_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.nb.add(tab, text="Room categories")

        cols = ("name", "min_guests", "max_guests")
        self.cat_tree = ttk.Treeview(tab, columns=cols, show="headings")
        self.cat_tree.grid(row=0, column=0, sticky="nsew")

        self.cat_tree.heading("name", text="Category name")
        self.cat_tree.heading("min_guests", text="Min guests")
        self.cat_tree.heading("max_guests", text="Max guests")

        self.cat_tree.column("name", width=720, minwidth=320, stretch=True)
        self.cat_tree.column("min_guests", width=140, minwidth=110, anchor="center", stretch=False)
        self.cat_tree.column("max_guests", width=140, minwidth=110, anchor="center", stretch=False)

        y = ttk.Scrollbar(tab, orient="vertical", command=self.cat_tree.yview)
        y.grid(row=0, column=1, sticky="ns")
        self.cat_tree.configure(yscrollcommand=y.set)

        btns = ttk.Frame(tab)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Add", command=self._cat_add).pack(side="left")
        ttk.Button(btns, text="Edit", command=self._cat_edit).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Delete", command=self._cat_delete).pack(side="left", padx=(8, 0))

        self._refresh_cat_tree()

    def _build_services_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(2, weight=1)
        tab.rowconfigure(1, weight=1)
        self.nb.add(tab, text="Services & follow-ups")

        ttk.Label(tab, text="Extra services", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(tab, text="Follow-up tasks", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, sticky="w")

        self.services_list = tk.Listbox(tab, height=12)
        self.services_list.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        y1 = ttk.Scrollbar(tab, orient="vertical", command=self.services_list.yview)
        y1.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self.services_list.configure(yscrollcommand=y1.set)

        self.followups_list = tk.Listbox(tab, height=12)
        self.followups_list.grid(row=1, column=2, sticky="nsew", pady=(6, 0))
        y2 = ttk.Scrollbar(tab, orient="vertical", command=self.followups_list.yview)
        y2.grid(row=1, column=3, sticky="ns", pady=(6, 0))
        self.followups_list.configure(yscrollcommand=y2.set)

        s_btns = ttk.Frame(tab)
        s_btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(s_btns, text="Add", command=self._service_add).pack(side="left")
        ttk.Button(s_btns, text="Delete", command=self._service_delete).pack(side="left", padx=(8, 0))

        f_btns = ttk.Frame(tab)
        f_btns.grid(row=2, column=2, sticky="ew", pady=(10, 0))
        ttk.Button(f_btns, text="Add", command=self._followup_add).pack(side="left")
        ttk.Button(f_btns, text="Delete", command=self._followup_delete).pack(side="left", padx=(8, 0))

        ttk.Label(tab, text="Note: Breakfast settings are not edited here (kept in JSON only).").grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(14, 6)
        )

        self._refresh_lists()

    def _build_advanced_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.nb.add(tab, text="Advanced (JSON)")

        ttk.Label(tab, text="Breakfast config (JSON only)", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")

        advanced = {
            "breakfast_policy": self.cfg.get("breakfast_policy", {}),
            "breakfast_types": self.cfg.get("breakfast_types", []),
        }

        txt = tk.Text(tab, wrap="word", font=("Consolas", 10), borderwidth=1, relief="solid")
        txt.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        txt.insert("1.0", json.dumps(advanced, ensure_ascii=False, indent=2))
        txt.config(state="disabled")

        ttk.Label(tab, text="Edit these directly in config.json if needed.").grid(row=2, column=0, sticky="w", pady=(10, 0))

    # ---------- refresh ----------

    def _refresh_guest_tree(self):
        for iid in self.guest_tree.get_children():
            self.guest_tree.delete(iid)
        for idx, g in enumerate(self.cfg.get("guests", [])):
            self.guest_tree.insert("", "end", iid=str(idx), values=(
                g.get("full_name", ""),
                g.get("comment", ""),
                g.get("min_guests", 1),
                g.get("max_guests", 99),
            ))

    def _refresh_cat_tree(self):
        for iid in self.cat_tree.get_children():
            self.cat_tree.delete(iid)
        for idx, c in enumerate(self.cfg.get("room_categories", [])):
            self.cat_tree.insert("", "end", iid=str(idx), values=(
                c.get("name", ""),
                c.get("min_guests", 1),
                c.get("max_guests", 1),
            ))

    def _refresh_lists(self):
        self.services_list.delete(0, "end")
        for s in self.cfg.get("extra_services", []):
            self.services_list.insert("end", s)

        self.followups_list.delete(0, "end")
        for s in self.cfg.get("follow_up_tasks", []):
            self.followups_list.insert("end", s)

    # ---------- guests ----------

    def _guest_selected_index(self) -> Optional[int]:
        sel = self.guest_tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except Exception:
            return None

    def _guest_add(self):
        data = edit_item_dialog(
            self,
            "Add guest",
            [
                ("full_name", "Full name"),
                ("comment", "Comment"),
                ("min_guests", "Min guests"),
                ("max_guests", "Max guests"),
            ],
            initial={"min_guests": "1", "max_guests": "99"},
        )
        if data is None:
            return
        try:
            name = data["full_name"].strip()
            if not name:
                raise ValueError("Full name cannot be empty.")
            gmin = validate_int(data["min_guests"], "Min guests")
            gmax = validate_int(data["max_guests"], "Max guests")
            if gmax < gmin:
                raise ValueError("Max guests must be >= min guests.")
        except Exception as e:
            show_popup(self, "Invalid guest", str(e))
            return

        self.cfg["guests"].append({
            "full_name": name,
            "comment": data.get("comment", "").strip(),
            "min_guests": gmin,
            "max_guests": gmax,
        })
        self._refresh_guest_tree()

    def _guest_edit(self):
        idx = self._guest_selected_index()
        if idx is None:
            show_popup(self, "Select a guest", "Please select a guest to edit.", width=700, height=420)
            return
        g = self.cfg["guests"][idx]
        data = edit_item_dialog(
            self,
            "Edit guest",
            [
                ("full_name", "Full name"),
                ("comment", "Comment"),
                ("min_guests", "Min guests"),
                ("max_guests", "Max guests"),
            ],
            initial={
                "full_name": g.get("full_name", ""),
                "comment": g.get("comment", ""),
                "min_guests": str(g.get("min_guests", 1)),
                "max_guests": str(g.get("max_guests", 99)),
            },
        )
        if data is None:
            return
        try:
            name = data["full_name"].strip()
            if not name:
                raise ValueError("Full name cannot be empty.")
            gmin = validate_int(data["min_guests"], "Min guests")
            gmax = validate_int(data["max_guests"], "Max guests")
            if gmax < gmin:
                raise ValueError("Max guests must be >= min guests.")
        except Exception as e:
            show_popup(self, "Invalid guest", str(e))
            return

        self.cfg["guests"][idx] = {
            "full_name": name,
            "comment": data.get("comment", "").strip(),
            "min_guests": gmin,
            "max_guests": gmax,
        }
        self._refresh_guest_tree()

    def _guest_delete(self):
        idx = self._guest_selected_index()
        if idx is None:
            show_popup(self, "Select a guest", "Please select a guest to delete.", width=700, height=420)
            return
        g = self.cfg["guests"][idx]
        if ask_confirm(self, "Delete guest", f"Delete guest:\n\n{g.get('full_name','')}"):
            del self.cfg["guests"][idx]
            self._refresh_guest_tree()

    # ---------- categories ----------

    def _cat_selected_index(self) -> Optional[int]:
        sel = self.cat_tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except Exception:
            return None

    def _cat_add(self):
        data = edit_item_dialog(
            self,
            "Add room category",
            [
                ("name", "Category name"),
                ("min_guests", "Min guests"),
                ("max_guests", "Max guests"),
            ],
            initial={"min_guests": "1", "max_guests": "1"},
        )
        if data is None:
            return
        try:
            name = data["name"].strip()
            if not name:
                raise ValueError("Category name cannot be empty.")
            cmin = validate_int(data["min_guests"], "Min guests")
            cmax = validate_int(data["max_guests"], "Max guests")
            if cmax < cmin:
                raise ValueError("Max guests must be >= min guests.")
        except Exception as e:
            show_popup(self, "Invalid category", str(e))
            return

        self.cfg["room_categories"].append({
            "name": name,
            "min_guests": cmin,
            "max_guests": cmax,
        })
        self._refresh_cat_tree()

    def _cat_edit(self):
        idx = self._cat_selected_index()
        if idx is None:
            show_popup(self, "Select a category", "Please select a room category to edit.", width=700, height=420)
            return
        c = self.cfg["room_categories"][idx]
        data = edit_item_dialog(
            self,
            "Edit room category",
            [
                ("name", "Category name"),
                ("min_guests", "Min guests"),
                ("max_guests", "Max guests"),
            ],
            initial={
                "name": c.get("name", ""),
                "min_guests": str(c.get("min_guests", 1)),
                "max_guests": str(c.get("max_guests", 1)),
            },
        )
        if data is None:
            return
        try:
            name = data["name"].strip()
            if not name:
                raise ValueError("Category name cannot be empty.")
            cmin = validate_int(data["min_guests"], "Min guests")
            cmax = validate_int(data["max_guests"], "Max guests")
            if cmax < cmin:
                raise ValueError("Max guests must be >= min guests.")
        except Exception as e:
            show_popup(self, "Invalid category", str(e))
            return

        self.cfg["room_categories"][idx] = {
            "name": name,
            "min_guests": cmin,
            "max_guests": cmax,
        }
        self._refresh_cat_tree()

    def _cat_delete(self):
        idx = self._cat_selected_index()
        if idx is None:
            show_popup(self, "Select a category", "Please select a room category to delete.", width=700, height=420)
            return
        c = self.cfg["room_categories"][idx]
        if ask_confirm(self, "Delete category", f"Delete category:\n\n{c.get('name','')}"):
            del self.cfg["room_categories"][idx]
            self._refresh_cat_tree()

    # ---------- services / follow-ups ----------

    def _service_add(self):
        s = ask_text(self, "Add extra service", "Service name:")
        if not s:
            return
        self.cfg["extra_services"].append(s)
        self._refresh_lists()

    def _service_delete(self):
        sel = self.services_list.curselection()
        if not sel:
            show_popup(self, "Select service", "Please select a service to delete.", width=700, height=420)
            return
        idx = int(sel[0])
        val = self.cfg["extra_services"][idx]
        if ask_confirm(self, "Delete service", f"Delete service:\n\n{val}"):
            del self.cfg["extra_services"][idx]
            self._refresh_lists()

    def _followup_add(self):
        s = ask_text(self, "Add follow-up task", "Follow-up task:")
        if not s:
            return
        self.cfg["follow_up_tasks"].append(s)
        self._refresh_lists()

    def _followup_delete(self):
        sel = self.followups_list.curselection()
        if not sel:
            show_popup(self, "Select follow-up", "Please select a follow-up to delete.", width=700, height=420)
            return
        idx = int(sel[0])
        val = self.cfg["follow_up_tasks"][idx]
        if ask_confirm(self, "Delete follow-up", f"Delete follow-up:\n\n{val}"):
            del self.cfg["follow_up_tasks"][idx]
            self._refresh_lists()

    # ---------- save ----------

    def _on_save(self):
        try:
            earliest = self.var_earliest.get().strip()
            latest = self.var_latest.get().strip()
            validate_iso_date(earliest)
            validate_iso_date(latest)
            if date.fromisoformat(latest) < date.fromisoformat(earliest):
                raise ValueError("Latest arrival must be on or after earliest arrival.")

            stay_min = validate_int(self.var_stay_min.get().strip(), "Stay min nights")
            stay_max = validate_int(self.var_stay_max.get().strip(), "Stay max nights")
            if stay_max < stay_min:
                raise ValueError("Stay max nights must be >= stay min nights.")

            max_services = validate_int(self.var_max_services.get().strip(), "Max extra services")
            if max_services < 0:
                raise ValueError("Max extra services must be >= 0.")

            followup_pct = validate_int(self.var_followup_pct.get().strip(), "Follow-up chance (%)")
            if followup_pct < 0 or followup_pct > 100:
                raise ValueError("Follow-up chance (%) must be between 0 and 100.")
            followup_prob = followup_pct / 100.0

        except Exception as e:
            show_popup(self, "Invalid settings", str(e))
            return

        self.cfg["booking_window"] = {"earliest_arrival": earliest, "latest_arrival": latest}
        self.cfg["stay_length_nights"] = {"min": stay_min, "max": stay_max}
        self.cfg["max_services"] = max_services
        self.cfg["follow_up_probability"] = followup_prob

        try:
            self.on_save_callback(self.cfg)
        except Exception as e:
            show_popup(self, "Save error", f"Callback failed:\n\n{e}")
            return

        self.destroy()
