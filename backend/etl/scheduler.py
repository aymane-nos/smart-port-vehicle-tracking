"""
Orchestration minimale du job ETL : APScheduler exécute
`aggregate_daily_traffic.run_etl()` une fois par jour, dans le processus
backend lui-même (pas besoin d'un Airflow complet pour ce volume de données).

Démarré/arrêté depuis les événements startup/shutdown de FastAPI (main.py).
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from etl.aggregate_daily_traffic import run_etl

logger = logging.getLogger("etl.scheduler")

scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_etl_job() -> None:
    try:
        rows_written = await run_etl()
        logger.info("Job ETL planifié exécuté avec succès (%d lignes).", rows_written)
    except Exception:
        logger.exception("Échec du job ETL planifié.")


def start_scheduler(hour: int = 1, minute: int = 0) -> None:
    """Planifie le job ETL chaque jour à `hour`:`minute` UTC (défaut 01:00)."""
    scheduler.add_job(
        _scheduled_etl_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_traffic_etl",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler ETL démarré (exécution quotidienne à %02d:%02d UTC).", hour, minute)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
