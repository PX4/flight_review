FROM ubuntu:18.04

COPY requirements.txt requirements.txt

RUN apt-get	update && \
	apt-get install -y --no-install-recommends apt-utils python3 python3-pip sqlite3 fftw3 python3-setuptools && \
	apt-get install -y --no-install-recommends python3-dev libfftw3-dev git && \
	pip3 install --no-cache-dir -r requirements.txt && \
	apt-get remove -y python3-dev libfftw3-dev git && \
	apt-get -y autoremove && \
	rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/service/data
COPY [".", "/opt/service/"]

WORKDIR /opt/service
EXPOSE 5006
CMD ["/opt/service/run.sh"]

## USAGE
## ## ## ## ## ## ## ## ## ## ## ## 
## BUILD  docker build -t px4flightreview -f docker/Dockerfile .
## RUN    docker run -d -p 5006:5006 -v /<full_path>/config_user.ini:/opt/service/config_user.ini px4flightreview
