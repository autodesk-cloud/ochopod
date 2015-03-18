FAQ
===

How does Ochopod differ from Docker Swarm or Compose ?
______________________________________________________

Ochopod goes beyond Swarm and Compose. For one thing we rely on Mesos_ for resourcing and provisioning containers on a
fleet of hosts (containers which may or may not be Docker_ based by the way). We also do not rely on container
specific features such as links and allow for more generic clustering (e.g your containers will connect to other
containers running - possibly on remote hosts - using their remapped ports). Ochopod also provides lookup and directory
capabilities on its own.

Now the big functional difference is that you can express all your clustering logic in Python_ and go as crazy (or
minimalist) as you want. This is how we let you for instance cluster a containerized Zookeeper_ ensemble over multiple
hosts.

So in a nutshell we provide the same general feature set except you can customize how you need to cluster things
together and swap out parts of the underlying technology stack (resourcing framework, container engine and so on) to
suit your needs.


Is Ochopod bound to Docker ?
____________________________

No it's not. The containerization technology used to run Ochopod does not really matter. You could run Ochopod using
a Rocket_ platform for instance.


How do I get Ochopod in my containers ?
_______________________________________

Just include the module in your container image and set it up ! You can that way build a base image that suits your
needs the best. You just need to install Python_ 2.7.


Do I need Mesos to take advantage of Ochopod ?
_______________________________________________

No you don't. Ochopod only relies on Zookeeper_ for synchronization but can be run anywhere, even on your workstation.
You could use Yarn_ for instance and have it run a Docker_ container that then invokes Ochopod.


Do I need to use Ochopod on Amazon EC2 ?
________________________________________

Not at all. Ochopod is not tied to any specific environment. You could totally run Ochopod over a cluster of
bare-metal resources if you wanted to. The only constraint is to be able to find out where you are running from and
where your synchronization Zookeeper_ ensemble is.


Does Ochopod provision resources ?
__________________________________

No. Ochopod simply allows several Docker_ containers to coordinate their configuration. Provisioning and resourcing
are performed one level down, for instance by letting Marathon_ cooperate with Mesos_ to run your containers.


Can I perform elastic scaling with Ochopod ?
____________________________________________

Yes, you can at the pod level. You could for instance dynamically leverage Marathon_ to scale your applications
up depending on some metrics. You could also do it one level lower and have your infrastructure scale the Mesos_
cluster up by physically adding new slaves. This is however not linked to Ochopod directly.


Can I run Ochopod to do Windows stuff ?
_______________________________________

Well, if you can find a suitable containerization technology dealing with Windows, it's a yes.


.. _Docker: https://www.docker.com/
.. _Marathon: https://mesosphere.github.io/marathon/
.. _Mesos: http://mesos.apache.org/
.. _Python: https://www.python.org/
.. _Pykka: https://github.com/jodal/pykka/
.. _Rocket: https://github.com/coreos/rocket
.. _Yarn: http://hadoop.apache.org/docs/current/hadoop-yarn/hadoop-yarn-site/YARN.html
.. _Zookeeper: http://zookeeper.apache.org/
