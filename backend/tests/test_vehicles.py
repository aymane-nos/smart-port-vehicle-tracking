"""Tests du router /vehicles."""


async def test_list_vehicles_filter_by_status(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "INPLATE", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    response = await client.get("/api/v1/vehicles", params={"status": "IN_PORT"})
    assert response.status_code == 200
    plates = [v["plate_number"] for v in response.json()]
    assert "INPLATE" in plates


async def test_update_vehicle_authorization(client):
    await client.post("/api/v1/detections", json={
        "plate_raw": "AUTHTEST", "plate_confidence": 0.9, "detection_confidence": 0.9,
        "gate_id": "G1", "direction": "IN", "vehicle_type": "CAR",
    })
    response = await client.patch("/api/v1/vehicles/AUTHTEST", json={"is_authorized": False})
    assert response.status_code == 200
    assert response.json()["is_authorized"] is False


async def test_get_unknown_vehicle_returns_404(client):
    response = await client.get("/api/v1/vehicles/DOESNOTEXIST")
    assert response.status_code == 404


async def test_update_unknown_vehicle_returns_404(client):
    response = await client.patch("/api/v1/vehicles/DOESNOTEXIST", json={"is_authorized": False})
    assert response.status_code == 404
