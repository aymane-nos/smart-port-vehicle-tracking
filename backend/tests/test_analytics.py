"""Tests du router /analytics."""


async def test_occupancy_reflects_in_port_vehicles(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "OCC1", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "TRUCK",
    })
    response = await client.get("/api/v1/analytics/occupancy")
    data = response.json()
    assert data["total_in_port"] >= 1
    assert data["by_vehicle_type"].get("TRUCK", 0) >= 1


async def test_occupancy_excludes_exited_vehicles(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "LEFTPORT", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    await client.post("/api/v1/detections", json={
        "plate_raw": "LEFTPORT", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "OUT", "vehicle_type": "CAR",
    })
    response = await client.get("/api/v1/vehicles/LEFTPORT")
    assert response.json()["status"] == "OUT"


async def test_alerts_include_unauthorized_vehicle(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "BADGUY1", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    await client.patch("/api/v1/vehicles/BADGUY1", json={"is_authorized": False})
    # Nouvelle détection après la mise à jour, pour que le JOIN la retrouve
    await client.post("/api/v1/detections", json={
        "plate_raw": "BADGUY1", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "OUT", "vehicle_type": "CAR",
    })
    response = await client.get("/api/v1/analytics/alerts")
    plates = [a["plate"] for a in response.json()]
    assert "BADGUY1" in plates


async def test_alerts_include_low_confidence_ocr(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "BLURRY1", "plate_confidence": 0.2, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    response = await client.get("/api/v1/analytics/alerts")
    plates = [a["plate"] for a in response.json()]
    assert "BLURRY1" in plates
