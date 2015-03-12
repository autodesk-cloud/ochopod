
Overview
========

Ochopod
_______

Ochopod is a Python_ package that performs automatic orchestration for containers running over Mesos_. It does
rely on Zookeeper_ for synchronization and is built using the cool Pykka_ actor system port. You can easily embed
Ochopod in your Docker_ containers and address complex situations where various systems cross-reference each others
at run-time.

Contents
________

.. toctree::
   :maxdepth: 3

   intro
   concepts
   api
   tools
   faq

Indices and tables
__________________

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _Docker: https://www.docker.com/
.. _Mesos: http://mesos.apache.org/
.. _Python: https://www.python.org/
.. _Pykka: https://github.com/jodal/pykka/
.. _Zookeeper: http://zookeeper.apache.org/
