"""Temporal client and worker setup.

The Temporal SDK requires:
  - A running Temporal server (development: temporal.io/cli or Docker)
  - Client to start workflows (from the API)
  - Worker(s) to execute activities + workflows

See docs/03 (Temporal choice) and docs/12 (Temporal setup).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from temporalio.client import Client

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
async def get_temporal_client() -> Client:
    """Get or create a Temporal client (cached singleton).

    Requires TEMPORAL_HOST env var or defaults to localhost:7233.
    Fails gracefully if the server is not running (caller catches and falls back).
    """
    try:
        client = await Client.connect("localhost:7233")
        logger.info("Temporal client connected")
        return client
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to connect to Temporal server: %s", exc)
        raise


# TODO: Worker setup (runs in a separate process / Docker sidecar)
# from temporalio.worker import Worker
# async def start_worker():
#     client = await get_temporal_client()
#     worker = Worker(
#         client,
#         task_queue="appointments",
#         workflows=[AppointmentReminderWorkflow],
#         activities=[send_whatsapp_reminder, place_reminder_call, ...],
#     )
#     await worker.run()
