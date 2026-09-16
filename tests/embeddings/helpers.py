"""Complete contract specifications used by embedding test fixtures."""

from scrapyrus.embeddings.specification import EmbeddingSpecification


def specification(model="model", size=None, **options):
    return EmbeddingSpecification(
        model_name=model,
        provider=options.pop("provider", "vllm"),
        endpoint_profile=options.pop("endpoint_profile", "vllm"),
        embedding_size=size,
        **options,
    )


def configuration(model="model", size=2, **options):
    value = specification(model, size, **options)
    return (
        value.model_name,
        value.embedding_size,
        value.provider,
        value.provider_options,
        value.endpoint_profile,
        value.contract_version,
    )
