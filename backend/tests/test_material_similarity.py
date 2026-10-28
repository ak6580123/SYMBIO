"""§12 - material similarity, and the boundary it must not cross.

The interesting assertion in here is the last one: the matching engine, the AI layer
and the analysis pipeline contain no reference to this module at all. Similarity is
allowed to be *explained* to the user; it is not allowed to decide anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def similarity():
    from knowledge_base import similarity

    return similarity


@pytest.fixture(scope="module")
def materials_by_id():
    from knowledge_base.materials import MATERIALS_BY_ID

    return MATERIALS_BY_ID


def test_fly_ash_neighbours_are_the_ash_like_materials(similarity):
    rows = similarity.similar_to("fly_ash", limit=5)
    names = {row["name"] for row in rows}
    assert "Bottom Ash" in names, "the lookalike list should start with actual pozzolans"
    assert rows == sorted(rows, key=lambda row: -row["similarity"])


def test_a_material_is_never_similar_to_itself(similarity):
    assert all(row["material_id"] != "fly_ash" for row in similarity.similar_to("fly_ash", limit=30))


def test_scores_are_percentages_within_range(similarity):
    rows = similarity.similar_to("fly_ash", limit=30)
    assert rows
    assert all(0.0 <= row["similarity"] <= 100.0 for row in rows)


def test_shared_evidence_is_real_evidence(similarity, materials_by_id):
    for row in similarity.similar_to("fly_ash", limit=6):
        source, other = materials_by_id["fly_ash"], materials_by_id[row["material_id"]]
        for field, values in row["shared"].items():
            assert set(values) <= {str(v).lower() for v in source[field]}
            assert set(values) <= {str(v).lower() for v in other[field]}


def test_similarity_is_symmetric(similarity, materials_by_id):
    a = materials_by_id["fly_ash"]
    b = materials_by_id["foundry_sand"]
    assert similarity.compare(a, b)["similarity"] == similarity.compare(b, a)["similarity"]


def test_order_is_stable_across_calls(similarity):
    assert similarity.similar_to("fly_ash", limit=8) == similarity.similar_to("fly_ash", limit=8)


def test_safety_level_is_reported_from_the_record_not_invented(similarity, materials_by_id):
    for row in similarity.similar_to("fly_ash", limit=10):
        assert row["safety_level"] == materials_by_id[row["material_id"]]["safety_level"]


def test_a_stricter_lookalike_is_flagged_before_it_is_scored(similarity):
    # Marble slurry is 'low'; fly ash is 'moderate'. The reverse - low looking up at a
    # hazardous material - has to carry the delta.
    rows = {row["material_id"]: row for row in similarity.similar_to("marble_slurry", limit=30)}
    catalyst = rows.get("spent_catalyst")
    if catalyst:
        assert catalyst["safety_delta"], "a hazardous lookalike must lead with the safety difference"
        assert "hazardous" in catalyst["differences"][0]


def test_min_similarity_filters_the_list(similarity):
    loose = similarity.similar_to("fly_ash", limit=30, min_score=0)
    tight = similarity.similar_to("fly_ash", limit=30, min_score=30)
    assert len(tight) < len(loose)
    assert all(row["similarity"] >= 30 for row in tight)


def test_least_similar_actually_means_least(similarity):
    rows = similarity.most_distinct("fly_ash", limit=3)
    full = similarity.similar_to("fly_ash", limit=30)
    assert len(rows) == 3
    # Everything in the "least similar" set is at most as similar as anything outside it.
    chosen = {row["material_id"] for row in rows}
    rest = [row for row in full if row["material_id"] not in chosen]
    assert rest
    assert max(row["similarity"] for row in rows) <= min(row["similarity"] for row in rest)


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------


def test_similar_endpoint(client):
    payload = client.get("/api/materials/fly_ash/similar?limit=4").json()
    assert payload["material"]["id"] == "fly_ash"
    assert len(payload["results"]) == 4
    assert payload["knowledge_base_size"] == 29
    assert "not a compatibility ruling" in payload["score_note"]
    assert payload["demo_data"] is True


def test_unknown_material_is_a_404_not_a_guess(client):
    response = client.get("/api/materials/not_a_real_material/similar")
    assert response.status_code == 404
    assert "knowledge base" in response.json()["detail"]


def test_limit_and_bounds_are_validated(client):
    assert client.get("/api/materials/fly_ash/similar?limit=0").status_code == 422
    assert client.get("/api/materials/fly_ash/similar?limit=99").status_code == 422


# ---------------------------------------------------------------------------
# the boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "matching/engine.py",
        "matching/scoring.py",
        "services/analysis.py",
        "services/explain.py",
        "ai/prompts.py",
        "ai/identification.py",
        "ai/fallback.py",
    ],
)
def test_the_ranking_pipeline_cannot_see_similarity(relative):
    path = BACKEND / relative
    if not path.exists():
        pytest.skip(f"{relative} is not part of this build")
    assert "similar" not in path.read_text().lower(), (
        f"{relative} must not consult material similarity - the safety layer and the "
        "engine are the only things that decide a route"
    )


def test_reading_similarity_is_read_only(client, fly_ash_analysis):
    """The endpoint must not be able to touch a stored analysis, its scores or its order."""
    analysis_id = fly_ash_analysis["id"]
    before = client.get(f"/api/analyses/{analysis_id}").json()
    client.get("/api/materials/fly_ash/similar?limit=20")
    client.get("/api/materials/fly_ash/similar?limit=20&min_similarity=20")
    after = client.get(f"/api/analyses/{analysis_id}").json()
    assert [m["recipient"]["id"] for m in before["matches"]] == [m["recipient"]["id"] for m in after["matches"]]
    assert before["totals"] == after["totals"]
