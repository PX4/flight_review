#! /bin/bash
# execute pylint on the source

pylint_exec=$(which pylint 2>/dev/null)

[[ $? != 0 ]] && { echo >&2 "pylint not found. Aborting."; exit 1; }

set -e

export PYTHONPATH=app/plot_app
python $pylint_exec app/tornado_handlers/*.py app/serve.py \
	app/plot_app/*.py app/download_logs.py

exit 0
