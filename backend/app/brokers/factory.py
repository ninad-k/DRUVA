from __future__ import annotations

import httpx

from app.brokers.base import BrokerAdapter, BrokerCredentials
from app.brokers.dhan import DhanAdapter
from app.brokers.five_paisa import FivePaisaAdapter
from app.brokers.fyers import FyersAdapter
from app.brokers.latency_wrapper import LatencyRecorder, LatencyRecordingAdapter
from app.brokers.paper import PaperBroker
from app.brokers.upstox import UpstoxAdapter
from app.brokers.zerodha import ZerodhaAdapter
from app.cache.client import CacheClient
from app.config import Settings
from app.db.models.account import Account
from app.db.session import SessionLocal
from app.infrastructure.encryption import EncryptedBlob, decrypt


class BrokerFactory:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, cache: CacheClient):
        self._http = http
        self._settings = settings
        self._cache = cache
        self._registry: dict[str, type[BrokerAdapter]] = {
            "zerodha": ZerodhaAdapter,
            "upstox": UpstoxAdapter,
            "dhan": DhanAdapter,
            "fyers": FyersAdapter,
            "five_paisa": FivePaisaAdapter,
            "paper": PaperBroker,
        }

    async def create(self, account: Account) -> BrokerAdapter:
        if account.is_paper:
            return LatencyRecordingAdapter(PaperBroker(cache=self._cache), LatencyRecorder(SessionLocal))

        adapter_cls = self._registry.get(account.broker_id)
        if adapter_cls is None:
            raise ValueError(f"Unsupported broker '{account.broker_id}'")

        adapter: BrokerAdapter
        if adapter_cls is PaperBroker:
            adapter = adapter_cls(cache=self._cache)
        else:
            adapter = adapter_cls(http=self._http)  # type: ignore[call-arg]

        api_key = decrypt(
            EncryptedBlob(ciphertext_b64=account.api_key_encrypted, nonce_b64=account.api_key_nonce),
            master_key_b64=self._settings.master_key,
        )
        api_secret = decrypt(
            EncryptedBlob(ciphertext_b64=account.api_secret_encrypted, nonce_b64=account.api_secret_nonce),
            master_key_b64=self._settings.master_key,
        )
        await adapter.authenticate(BrokerCredentials(api_key=api_key, api_secret=api_secret))

        return LatencyRecordingAdapter(adapter, LatencyRecorder(SessionLocal))
