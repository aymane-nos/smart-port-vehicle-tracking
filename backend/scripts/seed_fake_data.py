"""
Génère des semaines de trafic portuaire synthétique directement en base,
pour avoir une démo/dashboard qui semble "vécue" sans devoir rejouer des
vidéos de test à chaque fois.

Réutilise `crud.create_detection()` — exactement la même logique métier que
l'API réelle (upsert véhicule, mise à jour du statut IN_PORT/OUT) — donc les
données générées sont garanties cohérentes avec ce que produirait le vrai
pipeline ai_service -> backend. Puis rejoue le job ETL sur toute la période
pour peupler aussi la table de faits `daily_traffic_summary`.

Utilisation (depuis le conteneur backend) :
    python -m scripts.seed_fake_data                       # 30 jours, défauts
    python -m scripts.seed_fake_data --days 60 --events-per-day 40
    python -m scripts.seed_fake_data --reset                # vide d'abord la BDD
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import string
from datetime import datetime, timedelta

from sqlalchemy import delete, select

import crud
from database import AsyncSessionLocal
from etl.aggregate_daily_traffic import run_etl
from models import Detection, Direction, Vehicle, VehicleType
from schemas import DetectionCreate

logger = logging.getLogger("scripts.seed_fake_data")

GATES = ["GATE_A_ENTRY", "GATE_B_ENTRY", "GATE_C_EXIT"]

VEHICLE_TYPE_WEIGHTS = {
    VehicleType.TRUCK: 0.35,
    VehicleType.CONTAINER_TRUCK: 0.30,
    VehicleType.CAR: 0.25,
    VehicleType.BUS: 0.07,
    VehicleType.MOTORCYCLE: 0.03,
}


def random_plate() -> str:
    digits = "".join(random.choices(string.digits, k=4))
    letter = random.choice(string.ascii_uppercase)
    digits2 = "".join(random.choices(string.digits, k=2))
    return f"{digits}{letter}{digits2}"


def weighted_vehicle_type() -> VehicleType:
    types, weights = zip(*VEHICLE_TYPE_WEIGHTS.items())
    return random.choices(types, weights=weights, k=1)[0]


def business_hour_timestamp(day: datetime) -> datetime:
    """Favorise les pics 7h-10h / 14h-17h, avec un peu de trafic creux/nuit."""
    bucket = random.choices(
        ["morning_peak", "afternoon_peak", "offpeak", "night"],
        weights=[0.35, 0.30, 0.25, 0.10],
        k=1,
    )[0]
    if bucket == "morning_peak":
        hour = random.randint(7, 10)
    elif bucket == "afternoon_peak":
        hour = random.randint(14, 17)
    elif bucket == "offpeak":
        hour = random.randint(10, 14)
    else:
        hour = random.choice(list(range(0, 6)) + [22, 23])
    return day.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))


async def _reset_data() -> None:
    logger.warning("--reset : suppression des détections et véhicules existants...")
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Detection))
        await session.execute(delete(Vehicle))
        await session.commit()


async def seed(days: int, events_per_day: int, fleet_size: int, unauthorized_ratio: float, reset: bool) -> None:
    if reset:
        await _reset_data()

    fleet = [random_plate() for _ in range(fleet_size)]
    today = datetime.utcnow().date()
    total_events = 0

    for day_offset in range(days, 0, -1):
        day = datetime.combine(today - timedelta(days=day_offset), datetime.min.time())
        n_events = max(1, int(random.gauss(events_per_day, events_per_day * 0.2)))

        for _ in range(n_events):
            # 60% de chances que ce soit un véhicule "habitué" du port (camions réguliers...)
            plate = random.choice(fleet) if fleet and random.random() < 0.6 else random_plate()

            payload = DetectionCreate(
                plate_raw=plate,
                plate_confidence=round(random.uniform(0.55, 0.98), 3),
                detection_confidence=round(random.uniform(0.6, 0.95), 3),
                gate_id=random.choice(GATES),
                direction=random.choice([Direction.IN, Direction.OUT]),
                vehicle_type=weighted_vehicle_type(),
                track_id=random.randint(1, 9999),
                image_path=None,
                timestamp=business_hour_timestamp(day),
            )

            async with AsyncSessionLocal() as session:
                await crud.create_detection(session, payload)
            total_events += 1

        logger.info("Jour %s : %d événements générés.", day.date(), n_events)

    # Marque quelques véhicules comme non autorisés, pour peupler l'onglet alertes
    async with AsyncSessionLocal() as session:
        vehicles = list((await session.execute(select(Vehicle))).scalars().all())
        n_unauthorized = max(1, int(len(vehicles) * unauthorized_ratio))
        for vehicle in random.sample(vehicles, min(n_unauthorized, len(vehicles))):
            vehicle.is_authorized = False
            session.add(vehicle)
        await session.commit()
        logger.info("%d véhicule(s) marqué(s) non autorisé(s) (pour les alertes).", n_unauthorized)

    logger.info(
        "Seeding terminé : %d événements / %d jours / %d véhicules distincts dans le pool.",
        total_events, days, len(fleet),
    )

    # Backfill du job ETL sur toute la période générée, pour peupler aussi
    # la table de faits daily_traffic_summary (sinon l'onglet "Agrégats ETL"
    # resterait vide jusqu'au prochain run planifié).
    logger.info("Backfill du job ETL sur %d jours...", days)
    for day_offset in range(days, 0, -1):
        await run_etl(target_date=today - timedelta(days=day_offset))
    logger.info("Backfill ETL terminé.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Génère des données de trafic portuaire synthétiques réalistes.")
    parser.add_argument("--days", type=int, default=30, help="Nombre de jours d'historique à générer (défaut: 30).")
    parser.add_argument("--events-per-day", type=int, default=25, help="Nombre moyen d'événements/jour (défaut: 25).")
    parser.add_argument("--fleet-size", type=int, default=20, help="Nb de véhicules 'habitués' récurrents (défaut: 20).")
    parser.add_argument("--unauthorized-ratio", type=float, default=0.05, help="Proportion de véhicules non autorisés (défaut: 0.05).")
    parser.add_argument("--reset", action="store_true", help="Vide vehicles+detections avant de seeder.")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = _parse_args()
    asyncio.run(seed(args.days, args.events_per_day, args.fleet_size, args.unauthorized_ratio, args.reset))
