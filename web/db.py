# db.py
from __future__ import annotations

from typing import Optional, Any

from supabase import create_client, Client


class DB:
    """
    Thin wrapper around Supabase for:
      - Auth (sign up, sign in, sign out)
      - Per-user config CRUD
      - Tasks CRUD
    """

    def __init__(self, url: str, anon_key: str):
        self.url = url
        self.anon_key = anon_key

    def client(self) -> Client:
        return create_client(self.url, self.anon_key)

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

        IMPORTANT:
        Supabase may rotate refresh tokens. If that happens and Streamlit's session_state
        keeps the old refresh token, you can get: "Invalid Refresh Token: Already Used".

        This function detects rotation and updates st.session_state if available.

        CRITICAL CHANGE:
        If session cannot be applied/refreshed, we RAISE instead of returning an unauthed client.
        Returning an unauthed client causes silent write failures after idle.
        """
        sb = self.client()

        # set_session may return an AuthResponse (object) or dict-like response
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

            # If tokens changed, update Streamlit session_state (if running inside Streamlit)
            if new_access and new_refresh and (new_access != access_token or new_refresh != refresh_token):
                try:
                    import streamlit as st  # type: ignore

                    st.session_state["access_token"] = new_access
                    st.session_state["refresh_token"] = new_refresh
                except Exception:
                    pass

        return sb

    # ---------- configs ----------

    def get_config(self, sb: Client, user_id: str) -> Optional[dict]:
        try:
            res = (
                sb.table("configs")
                .select("config_json")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase get_config failed: {repr(e)}")

        # Treat None as "no config yet"
        if res is None:
            return None

        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase get_config error: {err}")

        data = getattr(res, "data", None)
        if not data:
            return None

        # maybe_single() returns dict
        if isinstance(data, dict):
            return data.get("config_json")

        return None

    def upsert_config(self, sb: Client, user_id: str, config_json: dict) -> None:
        try:
            res = (
                sb.table("configs")
                .upsert({"user_id": user_id, "config_json": config_json}, on_conflict="user_id")
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Supabase upsert_config failed: {repr(e)}")

        if res is None:
            raise RuntimeError("Supabase upsert_config failed: execute() returned None.")
        err = getattr(res, "error", None)
        if err:
            raise RuntimeError(f"Supabase upsert_config error: {err}")

    # ---------- tasks ----------

    def insert_task(
        self,
        sb: Client,
        user_id: str,
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
                        "user_id": user_id,
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

    def list_tasks(self, sb: Client, user_id: str, limit: int = 50) -> list[dict]:
        try:
            res = (
                sb.table("tasks")
                .select("id, generated_id, booking_number, followup_text, finished_at, scenario_json, review_status")
                .eq("user_id", user_id)
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
