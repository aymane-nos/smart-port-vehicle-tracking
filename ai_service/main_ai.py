"""
Point d'entrée du service IA : lit un flux vidéo (webcam / fichier / RTSP),
exécute le pipeline de détection à chaque frame retenue, met à jour le
tracker anti-doublon, et pousse chaque détection consolidée vers le backend
FastAPI via son endpoint POST /detections.

Variables d'environnement (voir .env.example) :
    VIDEO_SOURCE, YOLO_VEHICLE_MODEL, YOLO_PLATE_MODEL, OCR_LANGUAGES,
    DETECTION_CONFIDENCE, FRAME_SKIP, GATE_ID, BACKEND_API_URL
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import httpx
from dotenv import load_dotenv

from detector import DetectionPipeline
from tracker import ConsolidatedDetection, VehicleTracker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_service.main")

MEDIA_DIR = Path("/app/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    def __init__(self):
        self.video_source = self._parse_video_source(os.getenv("VIDEO_SOURCE", "0"))
        self.vehicle_model = os.getenv("YOLO_VEHICLE_MODEL", "yolov8n.pt")
        self.plate_model = os.getenv("YOLO_PLATE_MODEL", "models/plate_detector.pt")
        self.ocr_languages = os.getenv("OCR_LANGUAGES", "en").split(",")
        self.confidence = float(os.getenv("DETECTION_CONFIDENCE", "0.45"))
        self.frame_skip = int(os.getenv("FRAME_SKIP", "2"))
        self.gate_id = os.getenv("GATE_ID", "GATE_A_ENTRY")
        self.backend_url = os.getenv("BACKEND_API_URL", "http://backend:8000/api/v1")
        self.capture_interval = float(os.getenv("CAPTURE_INTERVAL_SECONDS", "1.0"))

    @staticmethod
    def _parse_video_source(value: str):
        return int(value) if value.isdigit() else value


def save_snapshot(frame, track_id: int) -> str:
    filename = f"{track_id}_{int(time.time() * 1000)}.jpg"
    path = MEDIA_DIR / filename
    cv2.imwrite(str(path), frame)
    return str(path)


def send_detection(client: httpx.Client, backend_url: str, gate_id: str, det: ConsolidatedDetection, image_path: str):
    payload = {
        "plate_raw": det.plate_text,
        "plate_confidence": det.plate_confidence,
        "detection_confidence": det.detection_confidence,
        "gate_id": gate_id,
        "direction": "IN",
        "vehicle_type": det.vehicle_type,
        "track_id": det.track_id,
        "image_path": image_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = client.post(f"{backend_url}/detections", json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(
            "Détection envoyée: plaque=%s conf=%.2f track_id=%s",
            det.plate_text, det.plate_confidence, det.track_id,
        )
    except httpx.HTTPError as exc:
        logger.error("Échec envoi détection au backend: %s", exc)


def run():
    settings = Settings()
    logger.info("Démarrage ai_service — source vidéo: %s, gate: %s", settings.video_source, settings.gate_id)

    pipeline = DetectionPipeline(
        vehicle_model_path=settings.vehicle_model,
        plate_model_path=settings.plate_model,
        ocr_languages=settings.ocr_languages,
        confidence=settings.confidence,
    )
    tracker = VehicleTracker()

    cap = cv2.VideoCapture(settings.video_source)
    if not cap.isOpened():
        logger.error("Impossible d'ouvrir la source vidéo: %s", settings.video_source)
        return

    frame_index = 0
    last_crop_by_track: dict[int, "object"] = {}

    with httpx.Client() as client:
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    logger.info("Flux vidéo terminé — finalisation des tracks restants.")
                    break

                frame_index += 1
                if frame_index % max(settings.frame_skip, 1) != 0:
                    continue

                detections = pipeline.process_frame(frame)
                track_map = tracker.update(frame.shape[:2], detections)

                # On garde uniquement le dernier crop en mémoire (pas d'écriture
                # disque ici) : l'image n'est sauvegardée qu'une fois la
                # détection consolidée/finalisée, pas à chaque frame traitée.
                for track_id, vehicle in track_map.items():
                    x1, y1, x2, y2 = vehicle.bbox
                    crop = frame[max(0, y1):y2, max(0, x1):x2]
                    if crop.size > 0:
                        last_crop_by_track[track_id] = crop

                finalized = tracker.pop_finalized_detections()
                for det in finalized:
                    crop = last_crop_by_track.pop(det.track_id, None)
                    image_path = save_snapshot(crop, det.track_id) if crop is not None else ""
                    send_detection(client, settings.backend_url, settings.gate_id, det, image_path)

                time.sleep(max(settings.capture_interval - 0.0, 0))

            # Vidéo terminée : on finalise et envoie les tracks encore actifs
            # (véhicule toujours visible à la dernière frame) au lieu de les perdre.
            for det in tracker.force_finalize_all():
                crop = last_crop_by_track.pop(det.track_id, None)
                image_path = save_snapshot(crop, det.track_id) if crop is not None else ""
                send_detection(client, settings.backend_url, settings.gate_id, det, image_path)

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur.")
        finally:
            cap.release()
            logger.info("Traitement terminé — arrêt propre du service.")


if __name__ == "__main__":
    run()
