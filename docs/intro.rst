Introduction
============

Problem statement
_________________

You are building some cool distributed backend and since you're at the bleeding edge you decided to use Docker_
containers. Even better you decided to be even cooler and run atop a Mesos_ or Kubernetes_ stack.

You now have plenty of containers floating around on multiple nodes and using all kinds of random ports and IPs.

How do you manage them? How do you solve annoying cross-container configuration issues? How do you identify issues
and peek at logs? How do you reconnect your CI/CD pipeline with this?

No need to pull you hair anymore, simply use Ochopod!


Mesos, Marathon & Ochopod
_________________________

Without getting too much into details system like Kubernetes_ or Mesos_ will manage Docker_ containers for you. What
you do is run some *high level construct* (a *replication controller* on Kubernetes_ for instance) : you specify an
image, environment variables, constraints plus a number of instances and the stack will look for available resources.
It will then ask the Docker_ daemon on those resources to run your image appropriately.

By embedding and invoking Ochopod in your Docker_ image you will run an init-like system in your container which will
do 3 things :

1. **Synchronize automatically** with all other containers spawned by your application (e.g your peers).
2. **Spawn the sub-process of your choice** and restart it in case of unexpected failure.
3. Let you query or **remote-control your containers** from a CI/CD pipeline or any other tool you wish to build.

Your *Dockerfile* specifies what needs to be installed in your container while your script defines what process needs
to be started and how to configure it across multiple instances.

This allows you to efficiently coordinate multiple containers to form for instance a Zookeeper_ ensemble or a
Cassandra_ ring in a nice automatic way. More interestingly you can also express transitive dependencies between your
clusters, e.g your set of Kafka_ brokers will only configure when their underlying zookeeper_ ensemble is up and
running with more than 3 nodes. Finding out where the pods run and what ports they expose is all taken care of for you.

Getting started
_______________

Try it out locally
******************

Simply run a local Zookeeper_ server on your workstation. Then install the sdk (make sure you have pip & git installed),
get the code and run the little shell_ example:

.. code:: python

    $ pip install git+https://github.com/autodeskcloud/ochopod.git
    $ git clone https://github.com/autodesk-cloud/ochopod.git
    $ python ochopod/examples/shell.py
    INFO - EC2 marathon bindings started
    INFO - running in local mode (make sure you run a standalone zookeeper)
    INFO - starting marathon.local (marathon/ec2) @ local
    ...

This pod will terminate after around 5 seconds and runs a trivial bash statement. You can tweak the code and
experiment. Try turning your Zookeeper_ server on/off and you'll see the pod re-connecting automatically.

A real Zookeeper ensemble over Mesosphere's DCOS !
**************************************************

It's now time to do something a bit more realistic. Go peek at our little sample_ repo. That container is a
simple example of how to run a containerized Zookeeper_ ensemble over DCOS_ by runnning Ochopod. Feel free to explore
the code and see how it is done.

Since we're running Zookeeper_ we make sure to expose ports 2181, 2888 and 3888 in the JSON definition. We also expose
8080 since this is our control port (e.g the port used by the pods to communicate). We are bold and go for 3 instances.

You'll notice we pass *ochopod_cluster* down to the container. This will tell Ochopod to assemble all those pods into
one single cluster called *ensemble*. Please note the corresponding DCOS_ application will be named differently (which
is fine).

Once your containers are running wait a few seconds for the cluster to form and stabilize. You can then test out your
newly formed ensemble by sending a *MNTR* command to any pod on what TCP 2181 is remapped to. You should get a
well-formed response telling you the remote server is indeed up and part of a ensemble.

That's pretty much it. Now scale your controller up. You'll again get a functional ensemble (larger this time) after a
few seconds! Woa now that is cool.

I picked Zookeeper_ as it's a classic case giving dev/ops engineers nightmares. Swap it for any system requiring
either a sequenced bootstrap (usually Gossip_ based system or RabbitMQ_ for instance) or some level of global
knowledge prior to configuring its nodes and you will then realize how much Ochopod can help you.


.. _Cassandra: http://cassandra.apache.org/
.. _Chef: http://www.getchef.com/chef/
.. _DCOS: https://mesosphere.com/
.. _Docker: https://www.docker.com/
.. _Gossip: http://en.wikipedia.org/wiki/Gossip_protocol
.. _Kafka: http://kafka.apache.org/
.. _Kubernetes: https://github.com/GoogleCloudPlatform/kubernetes
.. _Marathon: https://mesosphere.github.io/marathon/
.. _Mesos: http://mesos.apache.org/
.. _RabbitMQ: http://www.rabbitmq.com/
.. _sample: https://github.com/opaugam/marathon-ec2-zookeeper-sample
.. _shell: https://github.com/autodesk-cloud/ochopod/blob/master/examples/shell.py
.. _Zookeeper: http://zookeeper.apache.org




