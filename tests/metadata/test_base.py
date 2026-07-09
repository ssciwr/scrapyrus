from scrapyrus.metadata import (
    AncientEditionMetadataTable,
    KeywordMetadataTable,
    OrigDateMetadataTable,
    OrigPlaceMetadataTable,
    PapyrusMetadataTable,
)
from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.ancient_edition import AncientEditionModel
from scrapyrus.metadata.keywords import KeywordModel
from scrapyrus.metadata.origdate import OrigDateModel
from scrapyrus.metadata.origplace import OrigPlaceModel
from scrapyrus.metadata.papyri import PapyrusModel


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
        KeywordMetadataTable,
        OrigDateMetadataTable,
        OrigPlaceMetadataTable,
        AncientEditionMetadataTable,
    )


def test_metadata_table_columns_match_model_fields():
    papyri = PapyrusMetadataTable()
    keywords = KeywordMetadataTable()
    orig_dates = OrigDateMetadataTable()
    orig_places = OrigPlaceMetadataTable()
    ancient_editions = AncientEditionMetadataTable()

    assert papyri.model_class is PapyrusModel
    assert papyri.columns == tuple(PapyrusModel.model_fields)
    assert keywords.model_class is KeywordModel
    assert keywords.columns == tuple(KeywordModel.model_fields)
    assert orig_dates.model_class is OrigDateModel
    assert orig_dates.columns == tuple(OrigDateModel.model_fields)
    assert orig_places.model_class is OrigPlaceModel
    assert orig_places.columns == tuple(OrigPlaceModel.model_fields)
    assert ancient_editions.model_class is AncientEditionModel
    assert ancient_editions.columns == tuple(AncientEditionModel.model_fields)
