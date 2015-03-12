Introduction
============

Problem statement
_________________

You are building some cool distributed backend and since you're at the bleeding edge you decided to use Docker_
containers. Even better you decided to be even cooler and run atop a Mesos_ platform.

You now have plenty of containers floating around on multiple nodes and using all kinds of random ports.

How do you manage them? How do you solve annoying cross-container configuration issues? How do you identify issues
and peek at logs? How do you reconnect your CI/CD pipeline with this?

No need to pull you hair anymore, simply use Ochopod!


Mesos, Marathon & Ochopod
_________________________

Without getting too much into details Mesos_ and its Marathon_ framework will manage Docker_ containers for you. What
you do is run an *application* : you specify an image, environment variables, constraints plus a number of instances
and Marathon_ will ask Mesos_ for available resources. It will then ask the Docker_ daemon on those resources to run
your image. Marathon_ will also automatically remap the ports exposed by the containers.

By embedding and invoking the Ochopod SDK in your Docker_ image you will run an init-like system in your container
which will do 3 things :

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

The cluster
***********

You first of course need a Mesos_ cluster running Marathon_. This is easy to do and can be nicely automated using
Chef_ for instance. I won't cover this, you know how to do it. Just make sure you install Docker_ and setup your
slaves to use it. If you're lazy you can always run a master/slave hybrid on one single node (not recommended but
whatever).

.. note:: Run your cluster in AWS/EC2 as we only offer bindings for that provider right now.

Try it out locally
******************

Simply run a local Zookeeper_ server on your workstation. Then install the SDK and run the little *shell.py* example:

.. code:: python

    $ cd ochopod-python-sdk/sdk
    $ python setup.py install
    $ python ../examples/shell.py
    INFO - EC2 marathon bindings started
    INFO - running in local mode (make sure you run a standalone zookeeper)
    INFO - starting marathon.local (marathon/ec2) @ local
    ...

This pod will terminate after around 5 seconds and runs a trivial bash statement. You can tweak the code and
experiment. Try turning your Zookeeper_ server on/off and you'll see the pod re-connecting automatically.

Let's containerize Zookeeper !
******************************

It's now time to do something a bit more realistic. You probably noticed there is a *Dockerfile* in the repository.
Just build and either push it to your private repository or build the image on each node within your cluster if you
prefer. Our pod is a small example of how to run a containerized Zookeeper_ ensemble over Mesos_. The corresponding
code and resources are located under */examples/zookeeper*.

You are now ready to spawn an application in Marathon_ using our new image. Since we're running Zookeeper_ make sure
to expose ports 2181, 2888 and 3888. Also expose 8080 since this is our control port (e.g the port used by the pods
to communicate). Be bold and go for at least 3 instances.

Once your containers are running wait a few seconds for the cluster to form and stabilize. You can then test out your
newly formed ensemble by sending a *MNTR* command to any pod on the port remapping TCP 2181. You should get a
well-formed response telling you the remote server is indeed up and part of a ensemble.

That's pretty much it. Now go in the Marathon_ UI and scale your application up. You'll again get a functional
ensemble (larger this time) after a few seconds! Woa now that is cool.

I picked Zookeeper_ as it's a classic case giving dev/ops engineers nightmares. Swap it for any system requiring
either a sequenced bootstrap (usually Gossip_ based system or RabbitMQ_ for instance) or some level of global
knowledge prior to configuring its nodes and you will then realize how much Ochopod can help you.


.. _Cassandra: http://cassandra.apache.org/
.. _Chef: http://www.getchef.com/chef/
.. _Docker: https://www.docker.com/
.. _Gossip: http://en.wikipedia.org/wiki/Gossip_protocol
.. _Kafka: http://kafka.apache.org/
.. _Marathon: https://mesosphere.github.io/marathon/
.. _Mesos: http://mesos.apache.org/
.. _RabbitMQ: http://www.rabbitmq.com/
.. _Zookeeper: http://zookeeper.apache.org/




