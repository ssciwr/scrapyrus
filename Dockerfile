FROM python:3.13-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY pyproject.toml README.md LICENSE.md ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --editable .

CMD ["sleep", "infinity"]
