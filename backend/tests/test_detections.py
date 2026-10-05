"""Tests du router /detections — upsert véhicule, mise à jour de statut, validation."""


async def test_create_detection_creates_vehicle_and_sets_status(client):
    payload = {
        "plate_raw": "TEST123",
        "plate_confidence": 0.9,
        "detection_confidence": 0.85,
        "gate_id": "GATE_TEST",
        "direction": "IN",
        "vehicle_type": "CAR",
        "track_id": 1,
    }
    response = await client.post("/api/v1/detections", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["plate_raw"] == "TEST123"
    assert data["vehicle_id"] is not None

    vehicle_resp = await client.get("/api/v1/vehicles/TEST123")
    assert vehicle_resp.status_code == 200
    assert vehicle_resp.json()["status"] == "IN_PORT"


async def test_second_detection_same_plate_reuses_vehicle_and_updates_status(client):
    """Une même plaque ne doit JAMAIS créer un deuxième véhicule (upsert, pas insert)."""
    base_payload = {
        "plate_raw": "DUPLIC8",
        "plate_confidence": 0.9,
        "detection_confidence": 0.9,
        "gate_id": "GATE_TEST",
        "vehicle_type": "TRUCK",
    }
    r1 = await client.post("/api/v1/detections", json={**base_payload, "direction": "IN"})
    r2 = await client.post("/api/v1/detections", json={**base_payload, "direction": "OUT"})

    assert r1.json()["vehicle_id"] == r2.json()["vehicle_id"]

    vehicle = (await client.get("/api/v1/vehicles/DUPLIC8")).json()
    assert vehicle["status"] == "OUT"  # la direction la plus récente gagne


async def test_timestamp_with_timezone_is_normalized(client):
    """
    Non-régression : ai_service envoie un timestamp timezone-aware
    (ex: 2026-09-29T12:00:00+00:00). Avant le fix, ça cassait avec
    asyncpg ("can't subtract offset-naive and offset-aware datetimes").
    """
    payload = {
        "plate_raw": "TZTEST1",
        "plate_confidence": 0.8,
        "detection_confidence": 0.8,
        "gate_id": "GATE_TEST",
        "direction": "IN",
        "vehicle_type": "CAR",
        "timestamp": "2026-09-29T12:00:00+00:00",
    }
    response = await client.post("/api/v1/detections", json=payload)
    assert response.status_code == 201


async def test_invalid_payload_rejected(client):
    response = await client.post("/api/v1/detections", json={"plate_raw": "X"})
    assert response.status_code == 422


async def test_list_detections_filters_by_plate(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "FILTERME", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    await client.post("/api/v1/detections", json={
        "plate_raw": "OTHERPLATE", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })

    response = await client.get("/api/v1/detections", params={"plate": "FILTER"})
    plates = [d["plate_raw"] for d in response.json()]
    assert plates == ["FILTERME"]
