"""
Suivi d'objets (ByteTrack via `supervision`) + agrégation anti-doublon.

Problème résolu : un même véhicule traverse le champ de la caméra pendant
plusieurs dizaines de frames -> sans tracking, on émettrait des dizaines de
détections (et de lectures OCR potentiellement différentes) pour un seul
passage réel. On assigne donc un `track_id` stable par véhicule physique
(ByteTrack), on accumule les lectures OCR par track, et on n'émet **une
seule** détection consolidée (vote majoritaire sur le texte lu) quand le
track disparaît du champ (ou après un nombre de frames stable suffisant).
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import supervision as sv

from detector import PlateReading, VehicleDetection

logger = logging.getLogger("ai_service.tracker")


@dataclass
class TrackBuffer:
    vehicle_type_votes: Counter = field(default_factory=Counter)
    plate_votes: Counter = field(default_factory=Counter)
    plate_confidences: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    detection_confidences: list[float] = field(default_factory=list)
    last_seen_frame: int = 0
    emitted: bool = False


@dataclass
class ConsolidatedDetection:
    track_id: int
    plate_text: str
    plate_confidence: float
    detection_confidence: float
    vehicle_type: str


class VehicleTracker:
    """
    Enveloppe ByteTrack + agrégation. Appeler `update()` à chaque frame ;
    récupérer les détections consolidées prêtes à être envoyées via
    `pop_finalized_detections()`.
    """

    def __init__(
        self,
        min_votes_to_emit: int = 3,
        max_frames_without_update: int = 15,
    ):
        self.byte_tracker = sv.ByteTrack()
        self.buffers: dict[int, TrackBuffer] = {}
        self.min_votes_to_emit = min_votes_to_emit
        self.max_frames_without_update = max_frames_without_update
        self._frame_count = 0

    def update(
        self,
        frame_shape: tuple[int, int],
        detections: list[tuple[VehicleDetection, PlateReading | None]],
    ) -> dict[int, VehicleDetection]:
        """
        Met à jour le tracker avec les détections de la frame courante.
        Retourne un mapping track_id -> VehicleDetection pour cette frame.
        """
        self._frame_count += 1

        if not detections:
            sv_detections = sv.Detections.empty()
        else:
            xyxy = np.array([d[0].bbox for d in detections], dtype=np.float32)
            confidence = np.array([d[0].confidence for d in detections], dtype=np.float32)
            class_id = np.zeros(len(detections), dtype=int)
            sv_detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)

        tracked = self.byte_tracker.update_with_detections(sv_detections)

        track_id_to_vehicle: dict[int, VehicleDetection] = {}
        for i, track_id in enumerate(tracked.tracker_id):
            if track_id is None or i >= len(detections):
                continue
            vehicle, reading = detections[i]
            track_id = int(track_id)
            track_id_to_vehicle[track_id] = vehicle

            buffer = self.buffers.setdefault(track_id, TrackBuffer())
            buffer.last_seen_frame = self._frame_count
            buffer.vehicle_type_votes[vehicle.vehicle_type] += 1
            buffer.detection_confidences.append(vehicle.confidence)

            if reading is not None and len(reading.text) >= 4:
                buffer.plate_votes[reading.text] += 1
                buffer.plate_confidences[reading.text].append(reading.confidence)

        return track_id_to_vehicle

    def pop_finalized_detections(self) -> list[ConsolidatedDetection]:
        """
        Renvoie les détections consolidées prêtes à émettre : tracks
        suffisamment votés et non vus depuis `max_frames_without_update`
        frames (= le véhicule a quitté le champ), ou déjà stables.
        """
        finalized: list[ConsolidatedDetection] = []
        stale_track_ids = []

        for track_id, buffer in self.buffers.items():
            frames_since_seen = self._frame_count - buffer.last_seen_frame
            is_stale = frames_since_seen >= self.max_frames_without_update
            has_enough_votes = (
                buffer.plate_votes
                and max(buffer.plate_votes.values()) >= self.min_votes_to_emit
            )

            if buffer.emitted:
                if is_stale:
                    stale_track_ids.append(track_id)
                continue

            if is_stale and buffer.plate_votes:
                # Le véhicule quitte le champ : on émet le meilleur candidat
                # même sous le seuil de votes minimal (mieux que rien).
                finalized.append(self._consolidate(track_id, buffer))
                buffer.emitted = True
            elif has_enough_votes:
                finalized.append(self._consolidate(track_id, buffer))
                buffer.emitted = True

            if is_stale:
                stale_track_ids.append(track_id)

        for track_id in stale_track_ids:
            self.buffers.pop(track_id, None)

        return finalized

    def force_finalize_all(self) -> list[ConsolidatedDetection]:
        """
        À appeler quand le flux vidéo se termine (fin de fichier) : finalise
        tous les tracks encore actifs (non émis) qui ont au moins une lecture
        OCR, même s'ils n'ont pas atteint le seuil de staleness normal.
        Évite de perdre la détection d'un véhicule encore dans le champ au
        moment où la vidéo s'arrête (cas fréquent sur une vidéo de test courte).
        """
        finalized = []
        for track_id, buffer in self.buffers.items():
            if not buffer.emitted and buffer.plate_votes:
                finalized.append(self._consolidate(track_id, buffer))
                buffer.emitted = True
        return finalized

    @staticmethod
    def _consolidate(track_id: int, buffer: TrackBuffer) -> ConsolidatedDetection:
        best_plate, _ = buffer.plate_votes.most_common(1)[0]
        plate_confidence = (
            sum(buffer.plate_confidences[best_plate]) / len(buffer.plate_confidences[best_plate])
        )
        best_vehicle_type, _ = buffer.vehicle_type_votes.most_common(1)[0]
        avg_detection_conf = sum(buffer.detection_confidences) / len(buffer.detection_confidences)

        return ConsolidatedDetection(
            track_id=track_id,
            plate_text=best_plate,
            plate_confidence=round(plate_confidence, 3),
            detection_confidence=round(avg_detection_conf, 3),
            vehicle_type=best_vehicle_type,
        )
