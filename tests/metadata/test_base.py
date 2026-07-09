import pytest

from scrapyrus.metadata import (
    AncientEditionMetadataTable,
    KeywordMetadataTable,
    OrigDateMetadataTable,
    OrigPlaceMetadataTable,
    PapyrusMetadataTable,
    PrincipalEditionMetadataTable,
)
from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.ancient_edition import AncientEditionModel
from scrapyrus.metadata.keywords import KeywordModel
from scrapyrus.metadata.origdate import OrigDateModel
from scrapyrus.metadata.origplace import OrigPlaceModel
from scrapyrus.metadata.papyri import PapyrusModel
from scrapyrus.metadata.principal_edition import PrincipalEditionModel


def test_metadata_table_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(MetadataTable, "_tables", [])

    class FirstTable(MetadataTable):
        pass

    class SecondTable(MetadataTable):
        pass

    class UnregisteredTable(MetadataTable, register=False):
        pass

    assert MetadataTable.registered_tables() == (FirstTable, SecondTable)
    assert UnregisteredTable not in MetadataTable.registered_tables()


def test_metadata_table_registry_contains_builtin_tables():
    assert MetadataTable.registered_tables() == (
        PapyrusMetadataTable,
        PrincipalEditionMetadataTable,
        KeywordMetadataTable,
        OrigDateMetadataTable,
        OrigPlaceMetadataTable,
        AncientEditionMetadataTable,
    )


def test_base_metadata_table_requires_llm_catalog_methods():
    table = MetadataTable()

    with pytest.raises(NotImplementedError):
        table.description()
    with pytest.raises(NotImplementedError):
        table.semantic_catalog()


def test_metadata_table_columns_match_model_fields():
    papyri = PapyrusMetadataTable()
    principal_editions = PrincipalEditionMetadataTable()
    keywords = KeywordMetadataTable()
    orig_dates = OrigDateMetadataTable()
    orig_places = OrigPlaceMetadataTable()
    ancient_editions = AncientEditionMetadataTable()

    assert papyri.model_class is PapyrusModel
    assert papyri.columns == tuple(PapyrusModel.model_fields)
    assert principal_editions.model_class is PrincipalEditionModel
    assert principal_editions.columns == tuple(PrincipalEditionModel.model_fields)
    assert keywords.model_class is KeywordModel
    assert keywords.columns == tuple(KeywordModel.model_fields)
    assert orig_dates.model_class is OrigDateModel
    assert orig_dates.columns == tuple(OrigDateModel.model_fields)
    assert orig_places.model_class is OrigPlaceModel
    assert orig_places.columns == tuple(OrigPlaceModel.model_fields)
    assert ancient_editions.model_class is AncientEditionModel
    assert ancient_editions.columns == tuple(AncientEditionModel.model_fields)


def test_builtin_metadata_tables_expose_llm_catalog_text():
    for table_type in MetadataTable.registered_tables():
        table = table_type()
        description = table.description()
        semantic_catalog = table.semantic_catalog()

        assert description.strip() == description
        assert semantic_catalog.strip() == semantic_catalog
        assert table.name in description
        assert table.name in semantic_catalog
        for column in table.columns:
            assert column in semantic_catalog
