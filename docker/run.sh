#!/bin/bash

PORT_VALUE=${PORT:-5006}
DOMAIN_VALUE=${DOMAIN:-*}

WORK_PATH=/opt/service
DATA_PATH=${WORK_PATH}/data

# app setup
if [ -z "$(ls -A ${DATA_PATH})" ]; then
	python3 ${WORK_PATH}/setup_db.py
fi

if [ -n "${USE_PROXY}" ]; then
	python3 ${WORK_PATH}/serve.py \
		--port=${PORT_VALUE} \
		--address=0.0.0.0 \
		--allow-websocket-origin=${DOMAIN_VALUE} \
		--use-xheaders
else
	python3 ${WORK_PATH}/serve.py --port=${PORT_VALUE}
fi
