"""Expo Push API istemcisi (https://docs.expo.dev/push-notifications/sending-notifications/).

  send(messages)  → POST /push/send, en fazla 100 mesaj/istek → her mesaj için bir "ticket"
  receipts(ids)   → POST /push/getReceipts, en fazla 1000 id/istek → teslim sonucu

Ticket/receipt hatası "DeviceNotRegistered" ise token geçersizdir (uygulama silinmiş) ve silinmelidir.
Testler bu sınıfın yerine aynı arayüzde sahte bir istemci kullanır.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import Protocol

import httpx

SEND_URL = "https://exp.host/--/api/v2/push/send"
RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
SEND_BATCH = 100
RECEIPT_BATCH = 1000


class PushClient(Protocol):
    def send(self, messages: list[dict]) -> list[dict]: ...
    def receipts(self, ids: list[str]) -> dict[str, dict]: ...


def chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def is_expo_token(token: str) -> bool:
    return token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


class ExpoClient:
    def __init__(self, access_token: str | None = None, timeout: float = 15.0):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        token = access_token or os.environ.get("EXPO_ACCESS_TOKEN")
        if token:  # Expo hesabında "enhanced push security" açıksa gerekir
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(headers=headers, timeout=timeout)

    def send(self, messages: list[dict]) -> list[dict]:
        tickets: list[dict] = []
        for batch in chunks(messages, SEND_BATCH):
            r = self._http.post(SEND_URL, json=batch)
            r.raise_for_status()
            tickets.extend(r.json().get("data", []))
        return tickets

    def receipts(self, ids: Iterable[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for batch in chunks(list(ids), RECEIPT_BATCH):
            r = self._http.post(RECEIPTS_URL, json={"ids": batch})
            r.raise_for_status()
            out.update(r.json().get("data", {}))
        return out
