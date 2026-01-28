from __future__ import annotations

from typing import Any, Optional
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

    # ---------- auth ----------

    def sign_up(self, email: str, password: str):
        sb = self.client()
        return sb.auth.sign_up({"email": email, "password": password})

    def sign_in(self, email: str, password: str):
        sb = self.client()
        return sb.auth.sign_in_with_password({"email": email, "password": password})

    def sign_out(self, access_token: str, refresh_token: str) -> None:
        sb = self.client()
        # bind session then sign out
        sb.auth.set_session(access_token, refresh_token)
        sb.auth.sign_out()

    def authed_client(self, access_token: str, refresh_token: str) -> Client:
        """
        Returns a supabase client with the user's session applied
        so RLS policies work.
        """
        sb = self.client()
        sb.auth.set_session(access_token, refresh_token)
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
    
        if res is None:
            raise RuntimeError(
                "Supabase get_config failed: execute() returned None. "
                "This usually indicates a runtime/dependency HTTP issue."
            )
    
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
            res = sb.table("configs").upsert(
                {"user_id": user_id, "config_json": config_json},
                on_conflict="user_id",
            ).execute()
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
        sb.table("tasks").insert(
            {
                "user_id": user_id,
                "generated_id": generated_id,
                "booking_number": booking_number,
                "scenario_json": scenario_json,
                "followup_text": followup_text,
                "review_status": "new",  # ✅ default
            }
        ).execute()
        
    def list_tasks(self, sb: Client, user_id: str, limit: int = 50) -> list[dict]:
        res = (
            sb.table("tasks")
            .select("id, generated_id, booking_number, followup_text, finished_at, scenario_json, review_status")
            .eq("user_id", user_id)
            .order("finished_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def update_task_review_status(self, sb: Client, task_id: str, review_status: str) -> None:
        if review_status not in ("new", "okay", "needs_review"):
            raise ValueError("Invalid review_status.")
        sb.table("tasks").update({"review_status": review_status}).eq("id", task_id).execute()
