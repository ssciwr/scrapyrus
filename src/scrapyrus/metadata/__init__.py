from scrapyrus.metadata.papyri import PapyrusMetadataTable
from scrapyrus.metadata.principal_edition import PrincipalEditionMetadataTable
from scrapyrus.metadata.keywords import KeywordMetadataTable
from scrapyrus.metadata.origdate import OrigDateMetadataTable
from scrapyrus.metadata.origplace import OrigPlaceMetadataTable
from scrapyrus.metadata.ancient_edition import AncientEditionMetadataTable

__all__ = [
    "AncientEditionMetadataTable",
    "KeywordMetadataTable",
    "OrigDateMetadataTable",
    "OrigPlaceMetadataTable",
    "PapyrusMetadataTable",
    "PrincipalEditionMetadataTable",
]
