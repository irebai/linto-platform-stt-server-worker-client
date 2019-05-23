FROM debian:9
MAINTAINER Yoann Houpert <yhoupert@linagora.com>

RUN apt-get update &&\
    apt-get install -y \
    sox \
    python2.7 \
    python-pip &&\
    apt-get clean

ENV BASE_DIR /opt/speech-to-text

WORKDIR $BASE_DIR

COPY . .
COPY modules/server/server.cfg .
RUN pip install -r modules/server/requirements.txt

EXPOSE 8888

CMD ./modules/server/master_server.py