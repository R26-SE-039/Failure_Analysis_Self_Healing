"""
Gateway client — wraps calls to all 4 microservices.
"""
import httpx
import os
from typing import Optional

ML_URL            = os.getenv("ML_SERVICE_URL",           "http://localhost:8001")
HEALING_URL       = os.getenv("HEALING_SERVICE_URL",      "http://localhost:8002")
ANALYTICS_URL     = os.getenv("ANALYTICS_SERVICE_URL",    "http://localhost:8003")
NOTIFICATION_URL  = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8004")

TIMEOUT = httpx.Timeout(30.0)


async def classify(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{ML_URL}/classify", json=payload)
        r.raise_for_status()
        return r.json()


async def heal(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{HEALING_URL}/heal", json=payload)
        r.raise_for_status()
        return r.json()


async def check_flaky(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{ANALYTICS_URL}/check-flaky", json=payload)
        r.raise_for_status()
        return r.json()


async def notify(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{NOTIFICATION_URL}/notify", json=payload)
        r.raise_for_status()
        return r.json()


async def get_ml_metrics() -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{ML_URL}/metrics")
        r.raise_for_status()
        return r.json()


async def trigger_retrain() -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{ML_URL}/retrain")
        r.raise_for_status()
        return r.json()


async def get_retrain_status() -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{ML_URL}/retrain/status")
        r.raise_for_status()
        return r.json()


async def services_health() -> dict:
    results = {}
    for name, url in [
        ("ml-service",           ML_URL),
        ("healing-service",      HEALING_URL),
        ("analytics-service",    ANALYTICS_URL),
        ("notification-service", NOTIFICATION_URL),
    ]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                r = await client.get(f"{url}/health")
                results[name] = r.json()
        except Exception as e:
            results[name] = {"status": "unreachable", "error": str(e)}
    return results
