"""Non-secret embedding compatibility specifications shared with consumers."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scrapyrus.embeddings.clients import effective_provider_options

EMBEDDING_CONTRACT_VERSION = 1


class EmbeddingSpecification(BaseModel):
    """Identify the provider, model, and effective document/query options."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_name: str
    provider: str
    embedding_size: int | None = Field(default=None, gt=0)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    endpoint_profile: str | None = None
    contract_version: int = EMBEDDING_CONTRACT_VERSION

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_specification(self) -> EmbeddingSpecification:
        if self.contract_version != EMBEDDING_CONTRACT_VERSION:
            raise ValueError("Unsupported embedding contract version")
        options = effective_provider_options(self.provider, self.provider_options)
        if self.provider == "vllm" and not self.endpoint_profile:
            raise ValueError("vllm requires an endpoint_profile")
        if self.endpoint_profile is not None and not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", self.endpoint_profile
        ):
            raise ValueError(
                "endpoint_profile must be an environment variable profile name"
            )
        declared_size = options.get(
            "dimensions", options.get("output_dimension", options.get("truncate_dim"))
        )
        if (
            self.embedding_size is not None
            and declared_size is not None
            and self.embedding_size != declared_size
        ):
            raise ValueError("embedding_size disagrees with provider dimensions")
        object.__setattr__(self, "provider_options", options)
        return self

    @property
    def requested_dimensions(self) -> int | None:
        """Return an explicit size requested from the provider, if configured."""
        return self.embedding_size or self.provider_options.get(
            "dimensions",
            self.provider_options.get(
                "output_dimension", self.provider_options.get("truncate_dim")
            ),
        )

    def compatible_with(self, other: EmbeddingSpecification) -> bool:
        """Compare vector spaces, allowing an as-yet unknown dimension."""
        fields = (
            "model_name",
            "provider",
            "provider_options",
            "endpoint_profile",
            "contract_version",
        )
        return all(getattr(self, name) == getattr(other, name) for name in fields) and (
            self.embedding_size is None
            or other.embedding_size is None
            or self.embedding_size == other.embedding_size
        )


class EmbeddingTableMetadata(EmbeddingSpecification):
    """The complete specification published for one corpus table."""

    table_name: str

    @property
    def specification(self) -> EmbeddingSpecification:
        return EmbeddingSpecification.model_validate(
            self.model_dump(exclude={"table_name"})
        )
