"""Availability must agree with booking validation; synthetic in-memory data only."""
import pytest
from conftest import create, make_client, provision_tenant


@pytest.fixture()
def pool():
    with make_client() as client:
        tenant = provision_tenant(client, company_name="Synthetic resources", email="resources@example.test")
        headers = {"X-API-Key": tenant["plain_text_api_key"]}
        employee = create(client, headers, "employees", name="Synthetic requester")["id"]
        resource = create(client, headers, "resources", name="Synthetic pool", resource_type="equipment", booking_mode="shared", max_quantity=2)["id"]
        def book(start, end, quantity=1):
            return client.post("/api/v1/resource-bookings", headers=headers, json={
                "resource_id": resource, "booked_by_employee_id": employee, "title": "Synthetic booking",
                "start_at": f"2026-11-01T{start}:00+00:00", "end_at": f"2026-11-01T{end}:00+00:00", "quantity": quantity})
        def availability(start, end):
            result = client.get(f"/api/v1/resources/{resource}/availability", headers=headers, params={
                "start_at": f"2026-11-01T{start}:00+00:00", "end_at": f"2026-11-01T{end}:00+00:00"})
            assert result.status_code == 200, result.text
            return result.json()["data"]
        yield client, headers, book, availability


def test_adjacent_bookings_leave_one_unit_across_the_whole_window(pool):
    _, _, book, availability = pool
    assert book("09:00", "10:00").status_code == 201
    assert book("10:00", "11:00").status_code == 201
    result = availability("09:00", "11:00")
    assert result["available_quantity"] == 1
    assert result["available"] is True
    assert book("09:00", "11:00", 2).status_code == 409
    assert availability("09:00", "11:00")["available"] is True
    assert book("09:00", "11:00").status_code == 201
    assert availability("09:00", "11:00")["available_quantity"] == 0
    assert book("09:30", "10:30").status_code == 409


def test_peak_not_overlap_count_and_window_boundary(pool):
    _, _, book, availability = pool
    assert book("08:00", "10:00").status_code == 201
    assert book("09:00", "11:00").status_code == 201
    assert availability("09:30", "10:30")["available_quantity"] == 0
    assert availability("10:00", "11:00")["available_quantity"] == 1
    assert availability("11:00", "12:00")["available_quantity"] == 2


def test_cancelled_booking_releases_capacity(pool):
    client, headers, book, availability = pool
    booking = book("09:00", "11:00", 2).json()["data"]["id"]
    assert availability("09:00", "11:00")["available"] is False
    response = client.request("DELETE", f"/api/v1/resource-bookings/{booking}", headers=headers, json={"cancel_reason": "Synthetic test"})
    assert response.status_code == 204, response.text
    assert availability("09:00", "11:00")["available_quantity"] == 2


def test_reschedule_validation_excludes_itself_but_read_does_not(pool):
    client, headers, book, availability = pool
    booking = book("09:00", "11:00", 2).json()["data"]["id"]
    assert availability("10:00", "12:00")["available_quantity"] == 0
    response = client.patch(f"/api/v1/resource-bookings/{booking}", headers=headers, json={
        "start_at": "2026-11-01T10:00:00+00:00", "end_at": "2026-11-01T12:00:00+00:00"})
    assert response.status_code == 200, response.text


def test_exclusive_availability_also_returns_quantity(pool):
    client, headers, _, _ = pool
    resource = create(client, headers, "resources", name="Synthetic exclusive room", resource_type="room", booking_mode="exclusive", capacity=6)["id"]
    employee = create(client, headers, "employees", name="Synthetic second requester")["id"]
    query = {"start_at": "2026-11-01T09:00:00+00:00", "end_at": "2026-11-01T10:00:00+00:00"}
    endpoint = f"/api/v1/resources/{resource}/availability"
    assert client.get(endpoint, headers=headers, params=query).json()["data"]["available_quantity"] == 1
    response = client.post("/api/v1/resource-bookings", headers=headers, json={**query, "resource_id": resource, "booked_by_employee_id": employee, "title": "Synthetic exclusive reservation", "quantity": 1})
    assert response.status_code == 201, response.text
    result = client.get(endpoint, headers=headers, params=query).json()["data"]
    assert result["available_quantity"] == 0
    assert result["available"] is False
