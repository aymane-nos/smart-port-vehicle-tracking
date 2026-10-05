"""
Job ETL batch : Extract-Transform-Load des `detections` brutes vers la table
de faits agrégée `daily_traffic_summary`.

Pattern d'idempotence utilisé : "full partition reload" — pour une date
donnée, on supprime les lignes déjà agrégées puis on réinsère le résultat
frais. Relancer le job plusieurs fois sur la même date ne duplique jamais
rien et corrige les données si de nouvelles détections sont arrivées entre
deux exécutions.

Utilisation manuelle :
    python -m etl.aggregate_daily_traffic                 # agrège "hier" (UTC)
    python -m etl.aggregate_daily_traffic --date 2026-09-28

Utilisation programmatique (ex: appelée par le scheduler) :
    await run_etl(target_date=date(2026, 9, 28))
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select

from database import AsyncSessionLocal
from models import DailyTrafficSummary, Detection, Direction

logger = logging.getLogger("etl.aggregate_daily_traffic")


async def run_etl(target_date: date | None = None) -> int:
    """
    Exécute le cycle ETL complet pour une journée donnée.
    Retourne le nombre de lignes (partitions gate x vehicle_type) écrites.
    """
    target_date = target_date or (datetime.utcnow().date() - timedelta(days=1))
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        # --- EXTRACT + TRANSFORM (agrégation SQL directement côté BDD,
        # via des agrégats conditionnels FILTER — idiomatique Postgres,
        # évite de rapatrier les lignes brutes côté Python) ---
        query = (
            select(
                Detection.gate_id,
                Detection.vehicle_type,
                func.count().filter(Detection.direction == Direction.IN).label("entries"),
                func.count().filter(Detection.direction == Direction.OUT).label("exits"),
                func.count(func.distinct(Detection.vehicle_id)).label("unique_vehicles"),
                func.avg(Detection.plate_confidence).label("avg_conf"),
            )
            .where(Detection.timestamp >= start, Detection.timestamp < end)
            .group_by(Detection.gate_id, Detection.vehicle_type)
        )
        rows = (await session.execute(query)).all()

        # --- LOAD (rechargement idempotent de la partition = cette date) ---
        await session.execute(
            delete(DailyTrafficSummary).where(DailyTrafficSummary.summary_date == target_date)
        )

        for gate_id, vehicle_type, entries, exits_, unique_vehicles, avg_conf in rows:
            session.add(
                DailyTrafficSummary(
                    summary_date=target_date,
                    gate_id=gate_id,
                    vehicle_type=vehicle_type,
                    entries_count=int(entries or 0),
                    exits_count=int(exits_ or 0),
                    unique_vehicles_count=int(unique_vehicles or 0),
                    avg_plate_confidence=round(float(avg_conf or 0.0), 3),
                )
            )

        await session.commit()
        logger.info(
            "ETL terminé pour %s : %d partitions (gate x type) agrégées.",
            target_date, len(rows),
        )
        return len(rows)


def _parse_args() -> date | None:
    parser = argparse.ArgumentParser(description="ETL: agrégation journalière du trafic portuaire.")
    parser.add_argument("--date", type=str, default=None, help="Date à agréger (YYYY-MM-DD). Défaut : hier.")
    args = parser.parse_args()
    return date.fromisoformat(args.date) if args.date else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_etl(_parse_args()))
