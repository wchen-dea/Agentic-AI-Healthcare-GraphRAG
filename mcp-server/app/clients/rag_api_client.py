from __future__ import annotations

import httpx


class RagApiClient:
    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def query(self, question: str, patient_id: str | None = None) -> dict:
        payload = {"question": question, "patient_id": patient_id}
        response = httpx.post(
            f"{self.base_url}/query",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
