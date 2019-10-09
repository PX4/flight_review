FROM ubuntu:18.04
ARG CESIUM_API_KEY
ARG MAPBOX_API_ACCESS_TOKEN

RUN apt-get update
RUN apt-get install -y apt-utils
RUN apt-get install -y python3
RUN apt-get install -y python3-pip
RUN apt-get install -y python3-dev
RUN apt-get install -y sqlite3
RUN apt-get install -y fftw3
RUN apt-get install -y libfftw3-dev
RUN apt-get install -y git
RUN apt-get -y upgrade

RUN echo PATH="$HOME/.local/bin:$PATH" >> ~/.bashrc
RUN /bin/bash -c "source ~/.bashrc"

## use local project source
COPY . flight_review
WORKDIR flight_review

## set cesium and mabox keys
RUN echo "[general]" >> config_user.ini
RUN echo "cesium_api_key = $CESIUM_API_KEY" >> config_user.ini
RUN echo "mapbox_api_access_token = $MAPBOX_API_ACCESS_TOKEN" >> config_user.ini

RUN pip3 install -r requirements.txt

## app setup
RUN python3 setup_db.py

EXPOSE 5006
CMD ["python3", "serve.py"]

## USAGE
## ## ## ## ## ## ## ## ## ## ## ## 
## BUILD  docker build --build-arg CESIUM_API_KEY=[cesium-key] --build-arg MAPBOX_API_ACCESS_TOKEN=[mapbox_key] -t px4flightreview .
## RUN    docker run -d -p 5006:5006 px4flightreview
