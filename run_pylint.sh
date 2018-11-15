#! /bin/bash
PYTHONPATH=plot_app pipenv run pylint serve.py \
  download_logs.py \
  tornado_handlers/*.py \
  plot_app/*.py
