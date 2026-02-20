# db.py
from __future__ import annotations

from typing import Optional, Any

from supabase import create_client, Client


class DB:
    """
    Thin wrapper around Supabase for:
      - Auth (sign up, sign in, sign out)
      - Admin-auth actions (create users) using SERVICE ROLE KEY
      - Accommodation + membership
      - Per-accommodation config CRUD
      - Tasks CRUD
    """

    def __init__(self, url: str, anon_key: str, service_role_key: str = ""):
        self.url = url
        self.anon_key = anon_key
        self.service_role_key = service_role_key or ""

    def client(self) -> Client:
        return create_client(self.url, self.anon_key)

    def admin_client(self) -> Client:
        if not self.service_role_key:
            raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in secrets.")
        return create_client(self.url, self.service_role_key)

    # ---------- small helpers ----------

    @staticmethod
    def _pick(obj: Any, attr: str):
        """Get attribute from object or key from dict."""
        if obj is None:
            return None
        v = getattr(obj, attr, None)
        if v is not None:
            return v
        if isinstance(obj, dict):
            return obj.get(attr)
        return None

    @classmethod
    def _extract_session(cls, auth_res: Any):
        """Extract session from supabase AuthResponse or dict-like response."""
        session = cls._pick(auth_res, "session")
        if session is not None:
            return session
        data = cls._pick(auth_res, "data")
        return cls._pick(data, "session")

    # ---------- auth ----------

    def sign_up(self, email: str, password: str):
        sb = self.client()
        return sb.auth.sign_up({"email": email, "password": password})

    def sign_in(self, email: str, password: str):
        sb = self.client()
        return sb.auth.sign_in_with_password({"email": email, "password": password})

    def sign_out(self, access_token: str, refresh_token: str) -> None:
        sb = self.client()
        sb.auth.set_session(access_token, refresh_token)
        sb.auth.sign_out()

    def authed_client(self, access_token: str, refresh_token: str) -> Client:
        """
        Returns a supabase client with the user's session applied so RLS policies work.

        CRITICAL:
        If session cannot be applied/refreshed, we RAISE instead of returning an unauthed client.
        Returning an unauthed client causes silent write failures after idle.
        """
        sb = self.client()

        try:
            auth_res = sb.auth.set_session(access_token, refresh_token)
        except Exception as e:
            raise RuntimeError(
                "Session expired or refresh failed. User must log in again. "
                f"Details: {repr(e)}"
            )

        session = self._extract_session(auth_res)
        if session is not None:
            new_access = getattr(session, "access_token", None)
            new_refresh = getattr(session, "refresh_token", None)

            if new_access and new_refresh and (new_access != access_token or new_refresh != refresh_token):
                try:
                    import streamlit as st  # type: ignore
                    st.session_state["access_token"] = new_access
                    st.session_state["refresh_token"] = new_refresh
                except Exception:
                    pass

        return sb

    # ---------- admin: create user ----------

    def admin_create_user(self, email: str, password: str) -> str:
        """
        Creates a new Supabase Auth user using service role key.
        Returns the new user's UUID.
        """
        sb = self.admin_client()

        # supabase-py v2 style
        res = sb.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,  # admin-set password; skip confirmation friction
            }
        )

        # tolerate object/dict shapes
        user = getattr(res, "user", None)
        if user is None and isinstance(res, dict):
            user = res.get("user")

        if user is None:
            data = getattr(res, "data", None)
            user = getattr(data, "user", None) if data is not None else None
            if user is None and isinstance(data, dict):
                user = data.get("user")

        user_id = getattr(user, "id", None) if user is not None else None
        if not user_id:
            raise RuntimeError(f"Could not read created user id from admin create_user response: {res}")

        return str(user_id)

    # ---------- accommodation + membership ----------

    def create_accommodation(self, sb: Client, name: str) -> str:
        try:
            res = sb.table("accommodations").insert({"name": name}).execute()
        except Exception as e:
            raise RuntimeError(f"Supabase create_accommodation failed: {repr(e)}")

        if res is None or getattr(res, "error", None):
            raise RuntimeError(f"Supabase create_accommodation error: {getattr(res, 'error', None)}")

        # insert returns list of rows
        row = (res.data or [None])[0]
        if not row or "id" not in row:
            raise RuntimeError("Supabase create_accommodation returned no id.")
        return row["id"]

    def add_membership(self, sb: Client, accommodation_id: str, user_id: str, role: str) -> None:
        if role not in ("admin", "user"):
            raise ValueError("Invalid role.")
        try:
            res = (
                sb.table("memberships")
                .insert({"accommodation_id": accommodation_id, "user_id": user_id, "role": role})
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase add_membership failed: {repr(e)}")

        if res is None:
            raise RuntimeError("Supabase add_membership failed: execute() returned None.")
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase add_membership error: {err}")

    def get_my_membership(self, sb: Client, user_id: str) -> Optional[dict]:
        """
        Returns: {accommodation_id, role} or None if no membership found.
        """
        try:
            res = (
                sb.table("memberships")
                .select("accommodation_id, role")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase get_my_membership failed: {repr(e)}")

        if res is None:
            return None
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase get_my_membership error: {err}")

        data = getattr(res, "data", None)
        return data if isinstance(data, dict) and data else None

    def list_members(self, sb: Client, accommodation_id: str) -> list[dict]:
        try:
            res = (
                sb.table("memberships")
                .select("user_id, role, created_at")
                .eq("accommodation_id", accommodation_id)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase list_members failed: {repr(e)}")

        if res is None:
            return []
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase list_members error: {err}")

        return res.data or []

    # ---------- configs (per accommodation) ----------

    def get_config(self, sb: Client, accommodation_id: str) -> Optional[dict]:
        try:
            res = (
                sb.table("configs")
                .select("config_json")
                .eq("accommodation_id", accommodation_id)
                .maybe_single()
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase get_config failed: {repr(e)}")

        if res is None:
            return None

        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase get_config error: {err}")

        data = getattr(res, "data", None)
        if not data:
            return None

        if isinstance(data, dict):
            return data.get("config_json")

        return None

    def upsert_config(self, sb: Client, accommodation_id: str, config_json: dict) -> None:
        try:
            res = (
                sb.table("configs")
                .upsert({"accommodation_id": accommodation_id, "config_json": config_json}, on_conflict="accommodation_id")
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase upsert_config failed: {repr(e)}")

        if res is None:
            raise RuntimeError("Supabase upsert_config failed: execute() returned None.")
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase upsert_config error: {err}")

    # ---------- tasks (per accommodation) ----------

    def insert_task(
        self,
        sb: Client,
        accommodation_id: str,
        created_by: str,
        generated_id: str,
        booking_number: str,
        scenario_json: dict,
        followup_text: Optional[str],
    ) -> None:
        try:
            res = (
                sb.table("tasks")
                .insert(
                    {
                        "accommodation_id": accommodation_id,
                        "created_by": created_by,
                        "generated_id": generated_id,
                        "booking_number": booking_number,
                        "scenario_json": scenario_json,
                        "followup_text": followup_text,
                        "review_status": "new",
                    }
                )
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase insert_task failed: {repr(e)}")

        if res is None:
            raise RuntimeError("Supabase insert_task failed: execute() returned None.")
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase insert_task error: {err}")

    def list_tasks(self, sb: Client, accommodation_id: str, limit: int = 50) -> list[dict]:
        try:
            res = (
                sb.table("tasks")
                .select("id, generated_id, booking_number, followup_text, finished_at, scenario_json, review_status, created_by")
                .eq("accommodation_id", accommodation_id)
                .order("finished_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase list_tasks failed: {repr(e)}")

        if res is None:
            return []
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase list_tasks error: {err}")

        return res.data or []

    def update_task_review_status(self, sb: Client, task_id: str, review_status: str) -> None:
        if review_status not in ("new", "okay", "needs_review"):
            raise ValueError("Invalid review_status.")

        try:
            res = sb.table("tasks").update({"review_status": review_status}).eq("id", task_id).execute()
        except Exception as e:
            raise RuntimeError(f"Supabase update_task_review_status failed: {repr(e)}")

        if res is None:
            raise RuntimeError("Supabase update_task_review_status failed: execute() returned None.")
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase update_task_review_status error: {err}")
