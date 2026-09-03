# Tests for the stress-test batch generator.
#
# The generator's whole point is that its "expect" field can be trusted -
# a stress test that grades itself against wrong expectations would report
# false confidence, which is worse than not having one. So every
# deterministic case here is run through the real validate_mandate(), not
# just asserted to match by construction, mirroring how
# test_buyer_agent_simulator.py proves the five demo scenarios actually
# demonstrate what they claim.

from fastapi.testclient import TestClient

from app.catalog.catalog_service import get_catalog
from app.main import app
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.scenarios.stress_cases import INJECTION_PAIRS, build_stress_cases
from app.upsell.upsell_engine import _select_candidates
from app.validator.mandate_validator import validate_mandate

client = TestClient(app)


def catalog_as_dicts():
    return [product.model_dump() for product in get_catalog()]


def catalog_as_products():
    return get_catalog()


def run_through_validator(case):
    mandate = Mandate(**case["mandate"])
    transaction = ProposedTransaction(**case["transaction"])
    return validate_mandate(mandate, transaction)


def test_batch_covers_every_catalog_item_five_times_plus_injection_pairs():
    catalog = catalog_as_dicts()
    cases = build_stress_cases(catalog)
    assert len(cases) == 5 * len(catalog) + 2 * len(INJECTION_PAIRS)


def test_case_ids_are_unique():
    cases = build_stress_cases(catalog_as_dicts())
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_every_case_parses_as_a_valid_mandate_and_transaction():
    for case in build_stress_cases(catalog_as_dicts()):
        Mandate(**case["mandate"])
        ProposedTransaction(**case["transaction"])


def test_deterministic_cases_actually_match_the_real_validator():
    # This is the load-bearing test: it proves the batch's "expect" field is
    # correct, not just self-consistent - the entire feature is worthless
    # if this doesn't hold.
    for case in build_stress_cases(catalog_as_dicts()):
        expect = case["expect"]
        result = run_through_validator(case)
        assert result.approved == expect["approved"], case["id"]
        if not expect["approved"]:
            assert result.violated_rule.value == expect["violated_rule"], case["id"]


def test_multi_violation_cases_report_expiry_specifically():
    # Confirms the fixed check order (expiry, then category, then budget)
    # holds across every catalog item, not just one hand-picked example.
    multi_cases = [c for c in build_stress_cases(catalog_as_dicts()) if c["group"] == "multi_violation"]
    assert multi_cases
    for case in multi_cases:
        result = run_through_validator(case)
        assert result.violated_rule.value == "mandate_expired"


def test_injection_category_bypass_cases_are_structurally_declined():
    bypass_cases = [
        c for c in build_stress_cases(catalog_as_dicts()) if c["id"].endswith("-category-bypass")
    ]
    assert len(bypass_cases) == len(INJECTION_PAIRS)
    for case in bypass_cases:
        result = run_through_validator(case)
        assert result.approved is False
        assert result.violated_rule.value == "category_not_allowed"


def test_injection_cases_never_let_the_forbidden_sku_into_the_llm_candidate_list():
    # The upsell LLM only ever sees _select_candidates()'s output - if the
    # forbidden SKU can't get into that list, it structurally cannot be
    # proposed, independent of what the model itself does with the prompt.
    catalog = catalog_as_products()
    injection_cases = [c for c in build_stress_cases(catalog_as_dicts()) if c["id"].endswith("-injection")]
    assert len(injection_cases) == len(INJECTION_PAIRS)
    for case in injection_cases:
        mandate = Mandate(**case["mandate"])
        transaction = ProposedTransaction(**case["transaction"])
        candidates = _select_candidates(mandate, transaction, catalog)
        candidate_skus = {product.sku for product in candidates}
        assert case["expect"]["forbidden_upsell_sku"] not in candidate_skus


def test_stress_cases_endpoint_returns_the_full_batch():
    response = client.get("/stress-cases")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5 * len(catalog_as_dicts()) + 2 * len(INJECTION_PAIRS)
    assert "expect" in body[0]
