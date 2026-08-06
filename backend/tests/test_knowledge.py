import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import async_session_factory, engine
from app.knowledge import seed_operational_policies
from app.main import app
from app.models import KnowledgeChunk, KnowledgeDocument


@pytest.fixture(scope="module")
def knowledge_facts() -> dict[str, object]:
    async def collect() -> dict[str, object]:
        async with async_session_factory() as session:
            await seed_operational_policies(session)
            documents = list(
                await session.scalars(
                    select(KnowledgeDocument).order_by(KnowledgeDocument.title)
                )
            )
            chunks = list(
                await session.scalars(
                    select(KnowledgeChunk).order_by(
                        KnowledgeChunk.document_id,
                        KnowledgeChunk.chunk_index,
                    )
                )
            )
            facts = {
                "document_titles": {document.title for document in documents},
                "document_count": len(documents),
                "chunk_count": len(chunks),
                "chunk_indices": [chunk.chunk_index for chunk in chunks],
                "chunk_sections": [chunk.chunk_metadata.get("section") for chunk in chunks],
                "embedding_lengths": [len(chunk.embedding) for chunk in chunks],
                "embeddings_nonzero": all(any(chunk.embedding) for chunk in chunks),
            }
        await engine.dispose()
        return facts

    return asyncio.run(collect())


@pytest.fixture(scope="module")
def client(knowledge_facts: dict[str, object]) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@velocitycrm.com", "password": "VelocityAdmin@2026"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_five_operational_policies_are_persisted(
    knowledge_facts: dict[str, object],
) -> None:
    assert knowledge_facts["document_count"] == 5
    assert knowledge_facts["document_titles"] == {
        "Approval Escalation",
        "Deal Stage SLA Rules",
        "Deal-Owner Reassignment",
        "Sales Follow-Up Procedure",
        "Stalled-Deal Handling",
    }


def test_policy_sections_are_stored_as_ordered_chunks(
    knowledge_facts: dict[str, object],
) -> None:
    assert knowledge_facts["chunk_count"] == 10
    assert knowledge_facts["chunk_indices"].count(0) == 5
    assert knowledge_facts["chunk_indices"].count(1) == 5
    assert all(knowledge_facts["chunk_sections"])


def test_every_chunk_has_a_stored_embedding(
    knowledge_facts: dict[str, object],
) -> None:
    assert set(knowledge_facts["embedding_lengths"]) == {768}
    assert knowledge_facts["embeddings_nonzero"] is True


def test_stalled_deal_query_returns_relevant_policies(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/knowledge/search",
        headers=auth_headers,
        json={
            "query": "deal inactive beyond stage SLA with overdue follow-up",
            "incident_type": "stalled_deal",
            "limit": 5,
        },
    )
    assert response.status_code == 200
    results = response.json()
    assert {result["title"] for result in results[:2]} == {
        "Sales Follow-Up Procedure",
        "Stalled-Deal Handling",
    }
    assert all(
        {"title", "content", "similarity", "version", "metadata"} == set(result)
        for result in results
    )


def test_search_respects_result_limit(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/knowledge/search",
        headers=auth_headers,
        json={"query": "deal policy", "limit": 2},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_knowledge_endpoints_require_authentication(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assert client.get("/api/knowledge/documents").status_code == 401
    assert client.post(
        "/api/knowledge/search",
        json={"query": "stalled deal"},
    ).status_code == 401

    documents = client.get("/api/knowledge/documents", headers=auth_headers)
    assert documents.status_code == 200
    assert len(documents.json()) == 5