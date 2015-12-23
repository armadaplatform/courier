FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

ENV COURIER_APT_GET_UPDATE_DATE 2015-06-24
RUN apt-get update
RUN apt-get install -y git

ADD scripts/setup_ssh.sh /tmp/
RUN cd /tmp && chmod +x * && sync && ./setup_ssh.sh

ADD . /opt/courier
ADD ./supervisor/* /etc/supervisor/conf.d/

EXPOSE 22 80
