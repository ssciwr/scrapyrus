# Welcome to scrapyrus

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/ssciwr/scrapyrus/ci.yml?branch=main)](https://github.com/ssciwr/scrapyrus/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ssciwr/scrapyrus/branch/main/graph/badge.svg)](https://codecov.io/gh/ssciwr/scrapyrus)

## Installation

The Python package `scrapyrus` can be installed from PyPI:

```
python -m pip install scrapyrus
```

## Development installation

If you want to contribute to the development of `scrapyrus`, we recommend
the following editable installation from this repository:

```
git clone git@github.com:ssciwr/scrapyrus.git
cd scrapyrus
python -m pip install --editable .[tests]
```

Having done so, the test suite can be run using `pytest`:

```
python -m pytest
```

## Acknowledgments

This repository was set up using the [SSC Cookiecutter for Python Packages](https://github.com/ssciwr/cookiecutter-python-package).
