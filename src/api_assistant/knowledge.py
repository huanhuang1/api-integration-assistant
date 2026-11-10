"""Read the supported OpenAPI subset and validate the fictional workflow registry."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from api_assistant.models import KnowledgeError


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_fingerprint(source_dir: Path) -> str:
    files = sorted(p for p in source_dir.rglob("*") if p.suffix in {".yaml", ".yml", ".json"})
    return digest(
        {str(p.relative_to(source_dir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    )


def read_source(path: Path):
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise KnowledgeError(f"{path.name}: expected an object.")
        return data
    except (OSError, yaml.YAMLError) as exc:
        raise KnowledgeError(f"Cannot read {path.name}: {exc}") from exc


def reject_references(value, source: str):
    """Keep the first demo's supported subset explicit; never silently lose referenced schemas."""
    if isinstance(value, dict):
        if "$ref" in value or "$dynamicRef" in value:
            raise KnowledgeError(
                f"{source}: this demo requires inline schemas; resolve references first."
            )
        for child in value.values():
            reject_references(child, source)
    elif isinstance(value, list):
        for child in value:
            reject_references(child, source)


def schema_field(schema: dict, path: str) -> dict:
    branches = schema.get("oneOf") or schema.get("anyOf")
    if branches:
        for branch in branches:
            try:
                return schema_field(branch, path)
            except KnowledgeError:
                pass
        raise KnowledgeError(f"Unknown schema field: {path}")
    head, *tail = path.split(".", 1)
    if head not in schema.get("properties", {}):
        raise KnowledgeError(f"Unknown schema field: {path}")
    field = schema["properties"][head]
    return schema_field(field, tail[0]) if tail else field


def validate_payload(value: dict, schema: dict, label: str):
    try:
        Draft202012Validator(schema).validate(value)
    except (ValidationError, SchemaError) as exc:
        raise KnowledgeError(f"{label}: {exc.message}") from exc


def _parse_operations(path: Path, source_dir: Path) -> list[dict]:
    spec = read_source(path)
    source = str(path.relative_to(source_dir))
    if not str(spec.get("openapi", "")).startswith("3.1"):
        raise KnowledgeError(f"{source}: this demo supports OpenAPI 3.1 inline JSON schemas.")
    reject_references(spec, source)
    records = []
    for route, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            raise KnowledgeError(f"{source}: invalid path item {route}.")
        for method in ("get", "post", "put", "patch", "delete", "options", "head", "trace"):
            if method not in path_item:
                continue
            op = path_item[method]
            try:
                operation_id = op["operationId"]
                request = op["requestBody"]["content"]["application/json"]["schema"]
                success = sorted(str(code) for code in op["responses"] if str(code).startswith("2"))
                if len(success) != 1:
                    raise KnowledgeError(
                        f"{source}: demo operations need one JSON success response."
                    )
                response = op["responses"][success[0]]["content"]["application/json"]["schema"]
                Draft202012Validator.check_schema(request)
                Draft202012Validator.check_schema(response)
            except (KeyError, TypeError, SchemaError) as exc:
                raise KnowledgeError(
                    f"{source}: invalid operation at {method} {route}: {exc}"
                ) from exc
            parameters = path_item.get("parameters", []) + op.get("parameters", [])
            if parameters:
                raise KnowledgeError(
                    f"{source}: demo inputs must use JSON bodies; parameter handling is not implemented."
                )
            records.append(
                {
                    "operation_id": operation_id,
                    "method": method.upper(),
                    "path": route,
                    "description": op.get("description", op.get("summary", "")),
                    "request_schema": request,
                    "response_schema": response,
                    "success_status": success[0],
                    "parameters": parameters,
                    "security": op.get("security", spec.get("security", [])),
                    "security_schemes": spec.get("components", {}).get("securitySchemes", {}),
                    "servers": op.get("servers", path_item.get("servers", spec.get("servers", []))),
                    "source": source,
                    "spec_version": spec["info"]["version"],
                }
            )
    if not records:
        raise KnowledgeError(f"{source}: no supported operations found.")
    return records


def _keyed_records(source_dir: Path, folder: str, key: str) -> dict:
    result = {}
    for path in sorted((source_dir / folder).glob("*")):
        if path.suffix not in {".yaml", ".yml", ".json"}:
            continue
        record = read_source(path)
        identifier = record.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise KnowledgeError(f"{path.name}: missing or duplicate {key}.")
        record["source"] = str(path.relative_to(source_dir))
        result[identifier] = record
    if not result:
        raise KnowledgeError(f"No {folder} files found in {source_dir}.")
    return result


def load_sources(source_dir: Path) -> dict:
    operations = {}
    for path in sorted((source_dir / "apis").glob("*")):
        if path.suffix not in {".yaml", ".yml", ".json"}:
            continue
        for record in _parse_operations(path, source_dir):
            key = record["operation_id"]
            if key in operations:
                raise KnowledgeError(
                    f"Duplicate operationId {key}; demo operation IDs must be unique."
                )
            operations[key] = record
    if not operations:
        raise KnowledgeError("No API specifications were found.")
    records = {
        "operations": operations,
        "workflows": _keyed_records(source_dir, "workflows", "workflow_id"),
        "rules": _keyed_records(source_dir, "rules", "rule_id"),
    }
    validate_records(records)
    return records


def validate_records(records: dict):
    try:
        operations, rules = records["operations"], records["rules"]
        for workflow in records["workflows"].values():
            sequence = workflow["api_sequence"]
            if not sequence or len(sequence) != len(set(sequence)):
                raise KnowledgeError("Workflow needs a nonempty sequence without duplicate steps.")
            if workflow["intent"] != "open_account" or workflow["customer_status"] != "NEW":
                raise KnowledgeError(
                    "The demo supports new-customer account-opening workflows only."
                )
            if workflow["customer_type"] not in {"PERSONAL", "BUSINESS"}:
                raise KnowledgeError("Unknown customer type in workflow.")
            rule = rules[workflow["rule_id"]]
            if set(rule["operations"]) != set(sequence):
                raise KnowledgeError("Workflow and rule operation lists do not agree.")
            for operation_id in sequence:
                op = operations[operation_id]
                if op["operation_id"] != operation_id:
                    raise KnowledgeError("Operation record key does not match its ID.")
                for name in ("request_schema", "response_schema"):
                    Draft202012Validator.check_schema(op[name])
                per_op = rule["operations"][operation_id]
                if not isinstance(per_op["explanation"], str) or not per_op["explanation"].strip():
                    raise KnowledgeError(
                        f"{operation_id}: a scenario-specific explanation is required."
                    )
                fields = (
                    list(per_op["fixed"])
                    + list(per_op["example_inputs"])
                    + list(per_op["context_inputs"])
                )
                if len(fields) != len(set(fields)):
                    raise KnowledgeError(f"{operation_id}: conflicting field value sources.")
                if any("." in field for field in fields):
                    raise KnowledgeError("This demo supports top-level request fields only.")
                for field in fields + per_op["optional_fields"] + per_op["not_applicable_fields"]:
                    schema_field(op["request_schema"], field)
                if set(fields) & set(per_op["not_applicable_fields"]):
                    raise KnowledgeError(
                        f"{operation_id}: an inapplicable field has an assigned value."
                    )
            for target, source in workflow["bindings"].items():
                target_op, target_field = target.split(".", 1)
                if "." in target_field:
                    raise KnowledgeError("This demo supports top-level binding destinations only.")
                source_op, marker, source_field = source.split(".", 2)
                if marker != "response" or sequence.index(source_op) >= sequence.index(target_op):
                    raise KnowledgeError(f"Binding {source} -> {target} violates API order.")
                schema_field(operations[source_op]["response_schema"], source_field)
                schema_field(operations[target_op]["request_schema"], target_field)
                assigned = rule["operations"][target_op]
                if any(
                    target_field in assigned[k]
                    for k in ("fixed", "example_inputs", "context_inputs")
                ):
                    raise KnowledgeError(f"Binding would overwrite an assigned field: {target}")
            gate = workflow["gate"]
            if gate["equals"] != "PASSED":
                raise KnowledgeError("Account creation requires a PASSED verification gate.")
            source_op, marker, source_field = gate["source"].split(".", 2)
            if marker != "response" or sequence.index(source_op) >= sequence.index(gate["before"]):
                raise KnowledgeError("The verification gate must precede account creation.")
            validate_payload(
                gate["equals"],
                schema_field(operations[source_op]["response_schema"], source_field),
                "Gate value",
            )
            # Also validate scenario-specific examples against oneOf and shared schemas.
            build_plan(records, workflow["workflow_id"], "USD", "UNKNOWN")
    except (KeyError, TypeError, ValueError, SchemaError) as exc:
        if isinstance(exc, KnowledgeError):
            raise
        raise KnowledgeError(f"Invalid workflow/API/rule reference: {exc}") from exc


def _value_at(value: dict, path: str):
    for part in path.split("."):
        value = value[part]
    return value


def build_plan(
    records: dict, workflow_id: str, currency: str, verification_status: str
) -> list[dict]:
    """Build and schema-check examples from stored rules; never call a business endpoint."""
    workflow = records["workflows"][workflow_id]
    rule = records["rules"][workflow["rule_id"]]
    context = {"currency": currency}
    responses, steps = {}, []
    gate = workflow["gate"]
    gate_op, _, gate_field = gate["source"].split(".", 2)
    for operation_id in workflow["api_sequence"]:
        operation = records["operations"][operation_id]
        per_op = rule["operations"][operation_id]
        blocked = (
            operation_id == gate["before"]
            and _value_at(responses[gate_op], gate_field) != gate["equals"]
        )
        request, field_sources = {}, {}
        for section, description in (
            ("fixed", "Workflow rule"),
            ("example_inputs", "Synthetic example; replace with customer data"),
        ):
            for field, value in per_op[section].items():
                request[field] = deepcopy(value)
                field_sources[field] = description
        for field, context_key in per_op["context_inputs"].items():
            request[field] = context[context_key]
            field_sources[field] = "User request"
        for target, source in workflow["bindings"].items():
            target_op, field = target.split(".", 1)
            if target_op == operation_id:
                source_op, _, path = source.split(".", 2)
                request[field] = _value_at(responses[source_op], path)
                field_sources[field] = source
        response = deepcopy(per_op["example_response"])
        if operation_id == gate_op and verification_status != "UNKNOWN":
            response[gate_field] = verification_status
        validate_payload(request, operation["request_schema"], f"{operation_id} request")
        validate_payload(response, operation["response_schema"], f"{operation_id} response")
        if set(request) & set(per_op["not_applicable_fields"]):
            raise KnowledgeError(f"{operation_id}: request contains inapplicable fields.")
        if set(request) & set(per_op["optional_fields"]):
            raise KnowledgeError(
                f"{operation_id}: fields labeled optional/omitted are present in the example."
            )
        if blocked:
            request = None
            response = None
        steps.append(
            {
                "operation_id": operation_id,
                "method": operation["method"],
                "path": operation["path"],
                "description": operation["description"],
                "blocked": blocked,
                "request": request,
                "example_response": response,
                "field_sources": field_sources if not blocked else {},
                "optional_fields": per_op["optional_fields"],
                "not_applicable_fields": per_op["not_applicable_fields"],
                "security": operation["security"],
                "source": operation["source"],
                "servers": operation["servers"],
                "explanation": per_op["explanation"]
                if not blocked
                else "Do not create the account. Identity verification must return PASSED first.",
                "precondition": f"{gate['source']} must equal {gate['equals']}"
                if operation_id == gate["before"]
                else None,
            }
        )
        if not blocked:
            responses[operation_id] = response
        else:
            break
    return steps
