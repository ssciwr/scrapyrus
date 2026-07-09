from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel


def _metadata_tables() -> tuple["MetadataTable", ...]:
    return tuple(table_type() for table_type in MetadataTable.registered_tables())


def table_summary() -> str:
    """Return the descriptions of all registered metadata tables."""

    return "\n\n".join(table.description() for table in _metadata_tables())


def catalog(table_name: str) -> str:
    """Return the semantic catalog for a registered metadata table."""

    tables = _metadata_tables()
    for table in tables:
        if table.name == table_name:
            return table.semantic_catalog()

    table_names = ", ".join(table.name for table in tables)
    raise ValueError(
        f"Unknown metadata table {table_name!r}. Available tables: {table_names}"
    )


class MetadataTable:
    """Base class for generated metadata database tables.

    Subclasses are registered in definition order. Ingestion creates one
    instance of each registered subclass for the duration of a metadata run.
    """

    name: str
    order_by: tuple[str, ...]
    schema_sql: str

    _tables: ClassVar[list[type[MetadataTable]]] = []

    def __init_subclass__(
        cls,
        *,
        register: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if register:
            MetadataTable._tables.append(cls)

    @classmethod
    def registered_tables(cls) -> tuple[type[MetadataTable], ...]:
        """Return registered metadata table classes in ingestion order."""

        return tuple(cls._tables)

    @property
    def model_class(self) -> type[BaseModel]:
        """Return the Pydantic model class representing this table schema."""

        raise NotImplementedError

    @property
    def columns(self) -> tuple[str, ...]:
        """Return database columns in Pydantic model field order."""

        return tuple(self.model_class.model_fields)

    def create_factory(self, proc: Any) -> Any:
        raise NotImplementedError

    def description(self) -> str:
        """Return a short description of the table contents."""

        raise NotImplementedError

    def semantic_catalog(self) -> str:
        """Return field-level semantic guidance for natural-language SQL mapping."""

        raise NotImplementedError

    def build_rows(
        self, factory: Any, idp_data: Path, metadata: Path
    ) -> tuple[dict[str, Any], ...] | list[dict[str, Any]]:
        raise NotImplementedError
