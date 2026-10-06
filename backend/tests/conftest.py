"""Shared pytest fixtures.

`sys.path` points at the backend directory so `import main` resolves exactly the
way it does under `uvicorn main:app`.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest  # noqa: E402


FLY_ASH_REQUEST = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash collected from the electrostatic precipitator of our "
        "thermal power station. Dry, fine grey powder, consistent quality."
    ),
    "quantity": 5.0,
    "unit": "tonnes",
    "location": "Manali, Chennai",
    "frequency": "monthly",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}


@pytest.fixture
def fly_ash_analysis():
    from services import analysis as analysis_service

    return analysis_service.build_analysis(dict(FLY_ASH_REQUEST))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client
