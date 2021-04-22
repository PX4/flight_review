#! /bin/bash
# execute pylint on the source

pylint_exec=$(which pylint 2>/dev/null)

[[ $? != 0 ]] && { echo >&2 "pylint not found. Aborting."; exit 1; }

set -e

pushd app
export PYTHONPATH="plot_app:plot_app/libevents/libs/python"
python3 $pylint_exec tornado_handlers/*.py serve.py \
	plot_app/*.py download_logs.py
popd
exit 0
