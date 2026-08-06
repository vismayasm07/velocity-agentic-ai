import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from google import genai
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.policies import OPERATIONAL_POLICIES, OperationalPolicy


class EmbeddingService(Protocol):
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalEmbeddingService:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]


class GoogleEmbeddingService:
    def __init__(self, settings: Settings) -> None:
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when EMBEDDING_PROVIDER=google")
        self.dimensions = settings.embedding_dimensions
        self.model = settings.google_embedding_model
        self.client = genai.Client(api_key=settings.google_api_key)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.aio.models.embed_content(
            model=self.model,
            contents=list(texts),
            config={"output_dimensionality": self.dimensions},
        )
        return [list(embedding.values or []) for embedding in response.embeddings or []]


def get_embedding_service(settings: Settings | None = None) -> EmbeddingService:
    resolved = settings or get_settings()
    if resolved.embedding_dimensions != 768:
        raise ValueError("EMBEDDING_DIMENSIONS must remain 768 for the current schema")
    if resolved.embedding_provider.lower() == "google":
        return GoogleEmbeddingService(resolved)
    if resolved.embedding_provider.lower() == "local":
        return LocalEmbeddingService(resolved.embedding_dimensions)
    raise ValueError(f"Unsupported embedding provider: {resolved.embedding_provider}")


def split_policy(content: str) -> list[tuple[str, dict[str, object]]]:
    sections = re.split(r"(?m)^##\s+", content.strip())
    chunks: list[tuple[str, dict[str, object]]] = []
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        chunk = f"{heading}\n{body}" if body else heading
        chunks.append((chunk, {"section": heading}))
    return chunks


async def persist_policy(
    session: AsyncSession,
    policy: OperationalPolicy,
    embedding_service: EmbeddingService,
) -> KnowledgeDocument:
    document = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.document_type == policy.document_type,
            KnowledgeDocument.version == policy.version,
        )
    )
    if document is not None:
        return document

    document = KnowledgeDocument(
        title=policy.title,
        document_type=policy.document_type,
        version=policy.version,
        content=policy.content,
    )
    session.add(document)
    await session.flush()
    chunks = split_policy(policy.content)
    embeddings = await embedding_service.embed([content for content, _ in chunks])
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding provider returned an unexpected result count")
    session.add_all(
        KnowledgeChunk(
            document_id=document.id,
            content=content,
            chunk_index=index,
            chunk_metadata={
                **metadata,
                "document_type": policy.document_type,
                "policy_title": policy.title,
            },
            embedding=embedding,
        )
        for index, ((content, metadata), embedding) in enumerate(zip(chunks, embeddings))
    )
    return document


async def seed_operational_policies(
    session: AsyncSession,
    embedding_service: EmbeddingService | None = None,
) -> None:
    service = embedding_service or get_embedding_service()
    for policy in OPERATIONAL_POLICIES:
        await persist_policy(session, policy, service)
    await session.commit()


def _knowledge_search_statement(
    query_embedding: list[float],
    incident_type: str | None,
    limit: int,
) -> Select[tuple[KnowledgeChunk, KnowledgeDocument, float]]:
    distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument, (1 - distance).label("similarity"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .order_by(distance)
        .limit(limit)
    )
    if incident_type:
        statement = statement.where(
            KnowledgeDocument.document_type.in_((incident_type, "deal_stage_sla", "sales_follow_up"))
        )
    return statement


async def search_knowledge(
    session: AsyncSession,
    query: str,
    incident_type: str | None,
    limit: int,
    embedding_service: EmbeddingService | None = None,
) -> list[tuple[KnowledgeChunk, KnowledgeDocument, float]]:
    service = embedding_service or get_embedding_service()
    query_embedding = (await service.embed([query]))[0]
    rows = await session.execute(
        _knowledge_search_statement(query_embedding, incident_type, limit)
    )
    return [(chunk, document, float(similarity)) for chunk, document, similarity in rows]