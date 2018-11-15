#!/bin/bash

set -e
echo "[$(date)] Starting tests."

echo "[$(date)] Validating python dependency match"
# Check requirements lock file
pipenv lock --requirements > local-requirements.txt
cmp --silent requirements.txt local-requirements.txt || echo "[$(date)] ERROR: Pipenv.lock difers from requirements.txt"

echo "[$(date)] Running pylint"
bash run_pylint.sh

echo "[$(date)] End of test script."
