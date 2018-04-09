#! /bin/bash
# execute pylint on the source

pylint_exec=$(which pylint 2>/dev/null)

[[ $? != 0 ]] && { echo >&2 "pylint not found. Aborting."; exit 1; }

set -e

export PYTHONPATH=plot_app
python $pylint_exec tornado_handlers/*.py serve.py \
	plot_app/*.py download_logs.py

exit 0
