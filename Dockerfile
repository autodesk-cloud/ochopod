FROM ubuntu:14.04
ENV DEBIAN_FRONTEND noninteractive

#
# - update our repo
# - add python 2.7 + some utilities
# - note we explicitly add python-requests
#
RUN apt-get -y update && apt-get -y upgrade && apt-get -y install curl python python-requests supervisor

#
# - add the ochopod package and install it
# - remove defunct packages
# - start supervisor
#
ADD resources/supervisor/supervisord.conf /etc/supervisor/supervisord.conf
ADD ochopod /opt/ochopod
RUN cd /opt/ochopod && python setup.py install
RUN apt-get -y autoremove
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf