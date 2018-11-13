#!/bin/bash

set -e

# Check requirements lock file
pipenv lock --requirements > local-requirements.txt
cmp --silent requirements.txt local-requirements.txt || echo "ERROR: Pipenv.lock difers from requirements.txt"

# Check pylint
# TODO: fix pylint on source and enable
#bash run_pylint.sh
