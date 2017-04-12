FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

ENV COURIER_APT_GET_UPDATE_DATE 2016-05-19
RUN apt-get update && apt-get install -y git openssh-server rsync sudo

ADD scripts/setup_ssh.sh /tmp/
RUN cd /tmp && chmod +x * && sync && ./setup_ssh.sh

ADD . /opt/courier
ADD ./supervisor/* /etc/supervisor/conf.d/

EXPOSE 22 80
