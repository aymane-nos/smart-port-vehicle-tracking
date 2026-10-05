"""
Pipeline d'inférence : détection véhicule -> détection plaque -> OCR.

Deux modèles YOLOv8 sont utilisés :
  1. Un modèle véhicule (classes COCO standard : car, truck, bus, motorcycle) —
     `yolov8n.pt` pré-entraîné suffit en détection générique.
  2. Un modèle plaque, fine-tuné spécifiquement pour localiser les plaques
     d'immatriculation dans le crop véhicule (à entraîner sur un dataset
     dédié — un fallback "pas de modèle -> pas de crop plaque" est prévu).

EasyOCR effectue la lecture de caractères sur le crop de plaque, avec un
nettoyage regex du texte lu (suppression des caractères non alphanumériques).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import easyocr
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger("ai_service.detector")

# Classes COCO pertinentes pour un contexte portuaire
COCO_VEHICLE_CLASSES = {
    2: "CAR",
    3: "MOTORCYCLE",
    5: "BUS",
    7: "TRUCK",
}

PLATE_TEXT_CLEAN_RE = re.compile(r"[^A-Z0-9]")


@dataclass
class VehicleDetection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    vehicle_type: str


@dataclass
class PlateReading:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None


class VehicleDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.45):
        logger.info("Chargement du modèle véhicule: %s", model_path)
        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> list[VehicleDetection]:
        results = self.model.predict(frame, conf=self.confidence, verbose=False)[0]
        detections: list[VehicleDetection] = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in COCO_VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            detections.append(
                VehicleDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(box.conf[0]),
                    vehicle_type=COCO_VEHICLE_CLASSES[cls_id],
                )
            )
        return detections


class PlateDetector:
    """
    Localise la plaque à l'intérieur d'un crop véhicule.
    Si aucun modèle fine-tuné n'est fourni (models/plate_detector.pt absent),
    retombe sur la région basse du véhicule comme heuristique (moins précis,
    mais permet au pipeline de fonctionner sans dataset custom).
    """

    def __init__(self, model_path: str | None, confidence: float = 0.4):
        self.confidence = confidence
        self.model: YOLO | None = None
        if model_path and Path(model_path).exists():
            logger.info("Chargement du modèle plaque: %s", model_path)
            self.model = YOLO(model_path)
        else:
            logger.warning(
                "Modèle plaque introuvable (%s) -> heuristique de repli activée.",
                model_path,
            )

    def locate(self, vehicle_crop: np.ndarray) -> np.ndarray | None:
        if vehicle_crop.size == 0:
            return None

        if self.model is not None:
            results = self.model.predict(vehicle_crop, conf=self.confidence, verbose=False)[0]
            if len(results.boxes) == 0:
                return None
            # On prend la détection la plus confiante
            best = max(results.boxes, key=lambda b: float(b.conf[0]))
            x1, y1, x2, y2 = map(int, best.xyxy[0].tolist())
            return vehicle_crop[y1:y2, x1:x2]

        # --- Fallback heuristique : tiers inférieur du véhicule, centré ---
        h, w = vehicle_crop.shape[:2]
        y1, y2 = int(h * 0.65), h
        x1, x2 = int(w * 0.15), int(w * 0.85)
        return vehicle_crop[y1:y2, x1:x2]


class PlateOCR:
    def __init__(self, languages: list[str] | None = None, gpu: bool = False):
        languages = languages or ["en"]
        logger.info("Initialisation EasyOCR (langues=%s, gpu=%s)", languages, gpu)
        self.reader = easyocr.Reader(languages, gpu=gpu)

    def read(self, plate_crop: np.ndarray | None) -> PlateReading | None:
        if plate_crop is None or plate_crop.size == 0:
            return None

        processed = self._preprocess(plate_crop)
        results = self.reader.readtext(processed)
        if not results:
            return None

        # Concatène les segments de texte détectés, pondère par la confiance
        texts, confidences = [], []
        for _, text, conf in results:
            texts.append(text)
            confidences.append(conf)

        raw_text = " ".join(texts).upper()
        clean_text = PLATE_TEXT_CLEAN_RE.sub("", raw_text)
        if not clean_text:
            return None

        avg_confidence = sum(confidences) / len(confidences)
        return PlateReading(text=clean_text, confidence=avg_confidence, bbox=None)

    @staticmethod
    def _preprocess(crop: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        gray = cv2.equalizeHist(gray)
        return gray


class DetectionPipeline:
    """Orchestration complète : véhicule -> plaque -> OCR, pour une frame."""

    def __init__(
        self,
        vehicle_model_path: str,
        plate_model_path: str | None,
        ocr_languages: list[str],
        confidence: float,
    ):
        self.vehicle_detector = VehicleDetector(vehicle_model_path, confidence)
        self.plate_detector = PlateDetector(plate_model_path, confidence)
        self.ocr = PlateOCR(ocr_languages)

    def process_frame(self, frame: np.ndarray) -> list[tuple[VehicleDetection, PlateReading | None]]:
        vehicles = self.vehicle_detector.detect(frame)
        output = []
        for vehicle in vehicles:
            x1, y1, x2, y2 = vehicle.bbox
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            plate_crop = self.plate_detector.locate(crop)
            reading = self.ocr.read(plate_crop)
            output.append((vehicle, reading))
        return output
