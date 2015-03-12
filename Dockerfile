FROM ubuntu:14.04
ENV DEBIAN_FRONTEND noninteractive

#
# - update & install the java JRE, python, supervisor and a few other utilities
# - add the ochopod package & install it
#
RUN apt-get -y update
RUN apt-get -y install wget curl default-jre python python-requests supervisor
ADD sdk /opt/ochopod/sdk
RUN cd /opt/ochopod/sdk && python setup.py install

#
# - setup zookeeper 3.4.6 straight from their mirror
# - add our pod code & resources from examples/zookeeper/
#
RUN wget -q -O - http://apache.mirrors.pair.com/zookeeper/zookeeper-3.4.6/zookeeper-3.4.6.tar.gz | tar -C /opt -xz
RUN mkdir /var/lib/zookeeper
ADD examples/zookeeper /opt/pod

#
# - setup supervisor with a job to run our pod script
# - boot the container by running supervisor
#
RUN cp /opt/pod/pod.conf /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
