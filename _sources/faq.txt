FAQ
===


Is Ochopod bound to Docker ?
____________________________

No it's not. The containerization technology used to run Ochopod does not really matter. Now you have to be aware
that you may have to play with specific constraints, especially around resource quotas (cpu, memory).


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
.. _Yarn: http://hadoop.apache.org/docs/current/hadoop-yarn/hadoop-yarn-site/YARN.html
.. _Zookeeper: http://zookeeper.apache.org/
