FROM ubuntu:14.04
ENV DEBIAN_FRONTEND noninteractive

#
# - update our repo
# - add python 2.7 + some utilities
# - note we explicitly add python-requests
# - pip install ochopod
# - remove defunct packages
# - start supervisor
#
RUN apt-get -y update && apt-get -y upgrade && apt-get -y install git curl python python-requests supervisor
RUN curl https://bootstrap.pypa.io/get-pip.py | python
ADD resources/supervisor/supervisord.conf /etc/supervisor/supervisord.conf
RUN pip install git+https://github.com/autodesk-cloud/ochopod.git
RUN apt-get -y autoremove
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
