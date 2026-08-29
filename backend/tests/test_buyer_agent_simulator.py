# Tests for the buyer agent simulator and the /decide stub it talks to.
#
# The scenario-building logic is checked two ways: structurally (each
# scenario's mandate/transaction actually parses as Mandate/
# ProposedTransaction) and behaviorally (running each scenario through the
# real validator from Step 3 produces the outcome the scenario claims to
# demonstrate). That second check is what actually proves the four
# scenarios exercise the rules they're supposed to.

from fastapi.testclient import TestClient

from app.catalog.catalog_service import get_catalog
from app.main import app
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.validation_result import ValidationRule
from app.validator.mandate_validator import validate_mandate
from scripts.buyer_agent_simulator import build_scenarios, find_product

client = TestClient(app)


def catalog_as_dicts():
    return [product.model_dump() for product in get_catalog()]


def scenario_by_name(scenarios, name):
    return next(s for s in scenarios if s["name"] == name)


def run_through_validator(scenario):
    mandate = Mandate(**scenario["mandate"])
    transaction = ProposedTransaction(**scenario["transaction"])
    return validate_mandate(mandate, transaction)


def test_build_scenarios_returns_the_four_expected_names():
    scenarios = build_scenarios(catalog_as_dicts())
    names = [s["name"] for s in scenarios]
    assert names == [
        "clean_purchase",
        "upsell_eligible_purchase",
        "mandate_violation",
        "adversarial_upsell_attempt",
    ]


def test_find_product_raises_on_unknown_sku():
    try:
        find_product(catalog_as_dicts(), "DOES-NOT-EXIST")
        assert False, "expected ValueError for a missing SKU"
    except ValueError:
        pass


def test_clean_purchase_scenario_is_approved():
    scenario = scenario_by_name(build_scenarios(catalog_as_dicts()), "clean_purchase")
    result = run_through_validator(scenario)
    assert result.approved is True


def test_upsell_eligible_scenario_is_approved_with_budget_headroom():
    scenario = scenario_by_name(
        build_scenarios(catalog_as_dicts()), "upsell_eligible_purchase"
    )
    result = run_through_validator(scenario)
    assert result.approved is True
    headroom = scenario["mandate"]["budget_max"] - scenario["transaction"]["amount"]
    assert headroom > 0


def test_mandate_violation_scenario_declines_on_budget():
    scenario = scenario_by_name(build_scenarios(catalog_as_dicts()), "mandate_violation")
    result = run_through_validator(scenario)
    assert result.approved is False
    assert result.violated_rule == ValidationRule.BUDGET_EXCEEDED


def test_adversarial_upsell_attempt_declines_on_category():
    scenario = scenario_by_name(
        build_scenarios(catalog_as_dicts()), "adversarial_upsell_attempt"
    )
    result = run_through_validator(scenario)
    assert result.approved is False
    assert result.violated_rule == ValidationRule.CATEGORY_NOT_ALLOWED


def test_decide_stub_acknowledges_a_valid_payload():
    scenario = scenario_by_name(build_scenarios(catalog_as_dicts()), "clean_purchase")
    response = client.post(
        "/decide",
        json={"mandate": scenario["mandate"], "transaction": scenario["transaction"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["buyer_id"] == scenario["mandate"]["buyer_id"]
    assert "not implemented" in body["message"].lower()


def test_decide_stub_rejects_malformed_payload():
    response = client.post("/decide", json={"mandate": {}, "transaction": {}})
    assert response.status_code == 422
