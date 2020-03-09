FROM ubuntu:18.04

COPY requirements.txt requirements.txt

RUN apt-get	update && \
	apt-get install -y --no-install-recommends apt-utils python3 python3-pip sqlite3 fftw3 python3-setuptools && \
	apt-get install -y --no-install-recommends python3-dev libfftw3-dev git && \
	pip3 install --no-cache-dir -r requirements.txt && \
	apt-get remove -y python3-dev libfftw3-dev git && \
	apt-get -y autoremove && \
	rm -rf /var/lib/apt/lists/*


## set cesium and mabox keys
# RUN echo "[general]" >> config_user.ini
# RUN echo "cesium_api_key = $CESIUM_API_KEY" >> config_user.ini
# RUN echo "mapbox_api_access_token = $MAPBOX_API_ACCESS_TOKEN" >> config_user.ini

RUN mkdir -p /opt/service/data
COPY [".", "/opt/service/"]

WORKDIR /opt/service
EXPOSE 5006
CMD ["/opt/service/docker/run.sh"]

## USAGE
## ## ## ## ## ## ## ## ## ## ## ## 
## BUILD  docker build --build-arg CESIUM_API_KEY=[cesium-key] --build-arg MAPBOX_API_ACCESS_TOKEN=[mapbox_key] -t px4flightreview .
## RUN    docker run -d -p 5006:5006 px4flightreview
