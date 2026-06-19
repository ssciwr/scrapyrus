import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def idp_data() -> Path:
    """Return a local clone of the papyri.info data repository."""

    repository = Path(__file__).resolve().parents[1] / "idp.data"
    if not repository.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "https://github.com/papyri/idp.data.git",
                str(repository),
            ],
            check=True,
        )
    return repository
