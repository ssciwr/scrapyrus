from importlib.metadata import version as _distribution_version


__version__ = _distribution_version("scrapyrus")

__all__ = ["__version__"]
