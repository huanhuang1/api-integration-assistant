import pytest

from api_assistant.knowledge import build_plan, load_sources, validate_records
from api_assistant.models import KnowledgeError


@pytest.mark.parametrize("kind,currency", [("personal", "USD"), ("business", "EUR")])
def test_complete_scenario_uses_correct_fields_and_response_bindings(records, kind, currency):
    plan = build_plan(records, f"open_{kind}_account", currency, "UNKNOWN")
    customer, verification, account = plan
    assert [s["operation_id"] for s in plan] == [
        "createCustomer",
        "verifyIdentity",
        "createAccount",
    ]
    expected = (
        {"customerType", "fullName"}
        if kind == "personal"
        else {"customerType", "legalName", "companyRegistrationNumber"}
    )
    assert set(customer["request"]) == expected
    assert "marketingOptIn" in customer["optional_fields"]
    customer_id = customer["example_response"]["customerId"]
    assert verification["request"]["customerId"] == customer_id
    assert account["request"]["customerId"] == customer_id
    assert (
        account["request"]["verificationId"] == verification["example_response"]["verificationId"]
    )
    assert account["request"]["currency"] == currency
    assert "PASSED" in account["precondition"]


@pytest.mark.parametrize("status", ["FAILED", "PENDING"])
def test_nonpassed_verification_removes_account_request(records, status):
    plan = build_plan(records, "open_personal_account", "USD", status)
    assert plan[1]["example_response"]["status"] == status
    assert plan[2]["blocked"]
    assert plan[2]["request"] is None
    assert plan[2]["example_response"] is None


@pytest.mark.parametrize("broken_reference", ["operation", "rule", "binding", "order"])
def test_broken_registry_is_rejected(records, broken_reference):
    workflow = records["workflows"]["open_personal_account"]
    if broken_reference == "operation":
        workflow["api_sequence"][0] = "missingApi"
    elif broken_reference == "rule":
        workflow["rule_id"] = "missingRule"
    elif broken_reference == "binding":
        workflow["bindings"]["createAccount.customerId"] = "createCustomer.response.missingId"
    else:
        workflow["api_sequence"] = ["createAccount", "createCustomer", "verifyIdentity"]
    with pytest.raises(KnowledgeError):
        validate_records(records)


def test_incompatible_personal_and_business_fields_are_rejected(records):
    rule = records["rules"]["personal_account_rules"]["operations"]["createCustomer"]
    rule["fixed"]["customerType"] = "BUSINESS"
    with pytest.raises(KnowledgeError, match="request"):
        validate_records(records)


def test_bound_field_cannot_override_rule(records):
    records["rules"]["personal_account_rules"]["operations"]["createAccount"]["fixed"][
        "customerId"
    ] = "cus_wrong"
    with pytest.raises(KnowledgeError, match="overwrite"):
        validate_records(records)


def test_duplicate_operation_id_is_rejected(settings):
    source = settings.source_dir / "apis/customer-api.yaml"
    (source.parent / "duplicate.yaml").write_text(source.read_text())
    with pytest.raises(KnowledgeError, match="Duplicate operationId"):
        load_sources(settings.source_dir)


def test_schema_references_are_explicitly_rejected(settings):
    source = settings.source_dir / "apis/customer-api.yaml"
    source.write_text(source.read_text() + '\nunsupported: {"$ref": "missing.json"}\n')
    with pytest.raises(KnowledgeError, match="inline schemas"):
        load_sources(settings.source_dir)


def test_invalid_currency_cannot_become_an_api_payload(records):
    with pytest.raises(KnowledgeError, match="request"):
        build_plan(records, "open_personal_account", "GBP", "UNKNOWN")


def test_gate_cannot_allow_failed_verification(records):
    records["workflows"]["open_personal_account"]["gate"]["equals"] = "FAILED"
    with pytest.raises(KnowledgeError, match="PASSED verification gate"):
        validate_records(records)
