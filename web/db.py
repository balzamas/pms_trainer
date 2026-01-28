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
        res = (
            sb.table("configs")
            .select("config_json")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not res.data:
            return None
        return res.data["config_json"]

    def upsert_config(self, sb: Client, user_id: str, config_json: dict) -> None:
        sb.table("configs").upsert(
            {"user_id": user_id, "config_json": config_json},
            on_conflict="user_id",
        ).execute()

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
            }
        ).execute()

    def list_tasks(self, sb: Client, user_id: str, limit: int = 50) -> list[dict]:
        res = (
            sb.table("tasks")
            .select("id, generated_id, booking_number, followup_text, finished_at, scenario_json")
            .eq("user_id", user_id)
            .order("finished_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
