import subprocess
from pathlib import Path

import pytest


def _idp_data_repository(checkout: Path) -> Path:
    git_common_dir = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    common_dir = Path(git_common_dir)
    if not common_dir.is_absolute():
        common_dir = checkout / common_dir

    return common_dir.resolve().parent / "idp.data"


@pytest.fixture(scope="session")
def idp_data() -> Path:
    """Return a local clone of the papyri.info data repository."""

    repository = _idp_data_repository(Path(__file__).resolve().parents[1])
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
