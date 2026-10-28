"""Field extraction for uploads and natural-language input (Features 4 and 11).

The contract these tests hold: every value that comes back carries the text it
was read from, nothing is invented, a negated hazard is not a hazard, and the
preview never promises a better material guess than the pipeline itself would
produce - the preview calls the very same classifier.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services.extract import FIELD_KEYS, extract_fields  # noqa: E402

SPEC_SENTENCE = "We produce around 5 tonnes of fly ash every month in Chennai."


def test_spec_example_sentence_is_fully_extracted():
    result = extract_fields(SPEC_SENTENCE)
    fields = {key: result[key] for key in FIELD_KEYS}

    assert fields["quantity"]["value"] == 5.0
    assert fields["unit"]["value"] == "tonnes"
    assert fields["frequency"]["value"] == "monthly"
    assert fields["location"]["value"] == "Chennai"
    assert result["material"]["value"]["material_id"] == "fly_ash"


def test_every_extracted_value_carries_its_evidence():
    """A number the user cannot trace back to their document is not reviewable."""
    result = extract_fields(
        "Thermal Power Station, Manali. 480 tonnes per month of fly ash, SiO2 55%. Location: Chennai."
    )
    for name, field in ((key, result[key]) for key in FIELD_KEYS):
        if field["found"]:
            assert field["evidence"], f"{name} was extracted with no evidence to show"
            # The evidence must be a real slice of the input, not a paraphrase.
            core = field["evidence"].strip("…").split("…")[0]
            assert core.split(" ")[0].strip(".,:").lower() in result["description"].lower()


def test_unknown_thousands_separator_and_decimal_comma():
    assert extract_fields("1,200 tonnes monthly")["quantity"]["value"] == 1200.0
    assert extract_fields("5,5 tonnes monthly")["quantity"]["value"] == 5.5
    assert extract_fields("12.75 tonnes monthly")["quantity"]["value"] == 12.75


def test_units_are_normalised():
    assert extract_fields("300 kg per week")["unit"]["value"] == "kg"
    assert extract_fields("3 tons a day")["unit"]["value"] == "tonnes"
    assert extract_fields("40 t monthly")["unit"]["value"] == "tonnes"


def test_missing_fields_are_reported_rather_than_defaulted():
    """Silently filling in a quantity is how a demo lies to a judge."""
    result = extract_fields("Some grey powder comes off the filter bags now and then.")
    assert "quantity" in result["missing"]
    assert result["quantity"]["value"] is None
    # unit belongs to quantity, so it is never demanded on its own
    assert "unit" not in result["missing"]


def test_assumption_is_stated_when_frequency_is_absent():
    result = extract_fields("5 tonnes of fly ash in Chennai")
    assert result["frequency"]["value"] is None
    assert any("per-month" in note or "Per-month" in note for note in result["notes"])


def test_negated_hazard_is_not_flagged():
    """'No hazardous constituents detected' must not read as a hazard."""
    result = extract_fields("3 t/month of sludge. No hazardous constituents detected; not toxic, free of oil.")
    assert result["safety_flags"] == []


def test_genuine_hazard_word_is_flagged():
    result = extract_fields("3 t/month of oil-contaminated toxic sludge requiring licensed handling.")
    markers = {flag["marker"] for flag in result["safety_flags"]}
    assert {"toxic", "licensed handling"} <= markers


def test_negation_only_suppresses_the_clause_it_sits_in():
    result = extract_fields("Sludge is non-hazardous. It is however carcinogenic in dust form.")
    markers = {flag["marker"] for flag in result["safety_flags"]}
    assert markers == {"carcinogenic"}


def test_source_type_from_a_power_station_header():
    result = extract_fields("WASTE AUDIT - Thermal Power Station, Unit 3. 480 tonnes per month.")
    assert result["source_type"]["value"] == "industry"


def test_location_is_only_taken_from_the_demo_gazetteer():
    """A place we cannot geocode must not be offered, or the map lies."""
    assert extract_fields("5 tonnes monthly in Chennai")["location"]["value"]
    assert extract_fields("5 tonnes monthly at Somehamlet Village")["location"]["value"] is None


def test_material_guess_equals_the_pipeline_fallback():
    """The preview cannot promise a better identification than the run gives."""
    from ai.fallback import classify

    text = "Pulverised coal fly ash from the electrostatic precipitator, dry fine grey powder."
    preview = extract_fields(text)["material"]["value"]
    direct = classify(text, None, None)
    assert preview["material_id"] == direct["material_id"]
    assert preview["confidence"] == direct["confidence"]


def test_empty_input_is_handled():
    result = extract_fields("")
    assert result["missing"]
    assert result["notes"] == ["No text to read."]
    assert result["material"]["value"] is None


def test_garbage_input_does_not_raise():
    result = extract_fields("asdf qwer zxcv 12!!")
    assert set(FIELD_KEYS) <= set(result)  # the shape always exists
    assert result["quantity"]["value"] is None or result["quantity"]["value"] > 0
    assert "material" in result["missing"]


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


def test_extract_endpoint(client):
    resp = client.post("/api/extract", json={"text": SPEC_SENTENCE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["quantity"]["value"] == 5.0
    assert body["demo_data"] is True


def test_extract_endpoint_rejects_empty_text(client):
    assert client.post("/api/extract", json={"text": ""}).status_code == 422


def test_upload_returns_fields_alongside_the_text(client, tmp_path):
    report = tmp_path / "audit.txt"
    report.write_text("Thermal Power Station, Manali, Chennai. 480 tonnes per month of fly ash.")
    with open(report, "rb") as handle:
        resp = client.post("/api/upload", files={"file": ("audit.txt", handle, "text/plain")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["fields"]["quantity"]["value"] == 480.0
    assert body["fields"]["location"]["value"] in ("Manali", "Chennai")


def test_failed_upload_has_no_fields(client):
    resp = client.post("/api/upload", files={"file": ("x.exe", b"binary", "application/octet-stream")})
    body = resp.json()
    assert body["ok"] is False
    assert body["fields"] is None
