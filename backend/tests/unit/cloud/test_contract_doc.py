"""The contract doc is a DELIVERABLE, not prose — keep it pinned to the code."""
from pathlib import Path

from app.cloud.contracts import ADMIN_API_ROUTES

DOC = Path(__file__).parents[3].parent / "docs" / "2026-07-21-saiife-cloud-admin-api-contract.md"


def test_contract_doc_exists() -> None:
    assert DOC.is_file(), f"missing contract deliverable at {DOC}"


def test_contract_doc_documents_every_route() -> None:
    text = DOC.read_text()
    for method, path in ADMIN_API_ROUTES.values():
        literal = path.replace("{tenant_id}", "{tenantId}")
        assert f"{method} {literal}" in text, f"undocumented route: {method} {literal}"


def test_contract_doc_pins_the_hash_scheme_and_shared_pepper() -> None:
    text = DOC.read_text()
    assert "scrypt$16384$8$1$" in text
    assert "N=16384" in text
    assert "shared pepper" in text.lower()
    assert "sfc_<tenantLookupId>_<secret>" in text


def test_contract_doc_states_idempotency_on_external_ref() -> None:
    text = DOC.read_text()
    assert "externalRef" in text
    assert "idempotent" in text.lower()
