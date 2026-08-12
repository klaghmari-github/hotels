#!/usr/bin/env bash
# Publish placeholder package to PyPI (name reservation).
set -euo pipefail

cd "$(dirname "$0")"
PYPI_REPOSITORY="${PYPI_REPOSITORY:-pypi}"

python -m pip install --upgrade pip build twine -q
rm -rf build dist src/*.egg-info *.egg-info
python -m build
twine check dist/*
if [ "$PYPI_REPOSITORY" = "testpypi" ]; then
  twine upload --repository testpypi dist/*
else
  twine upload dist/*
fi
echo "Published renatus to ${PYPI_REPOSITORY}"
