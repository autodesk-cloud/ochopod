Tools & Automation
==================

Our Swiss army knife
____________________

Ochopod comes with an extensible tool aptly named *ocho*. We bundled some core logic that makes querying pods
very easy. Tools are imported on the fly:
    - from the local *ochopod* package (this gives you access to our default tools).
    - from the current directory (e.g from where you run *ocho*).
    - from a sub-directory called */tools*/ and relative to the current directory (provided */tools* exists of course).

A tool is essentially a standalone Python_ module that exports a *go()* callable that returns an instance of
:class:`ochopod.tools.tool.Template`. The *ocho* command line utility will import any module matching this description.
The Zookeeper_ ensemble used for synchronization is provided either by setting the *$OCHOPOD_ZK* environment
variable or by using the *--zk* option.

You can find an example of such a custom tool under */examples/tools*. Go in there and try to run it :

.. code:: python

    $ cd examples/tools
    $ ocho count
    9 pods

This system makes a simple yet flexible foundation for building small automation pieces (typically to spawn pods,
wait for them to be configured, etc.). As an example you can easily list your pods:

.. code:: python

    $ ocho ls
    3 pods total, 100% running ->
     - my-service.sandbox.kafka #0
     - my-service.sandbox.kafka #1
     - my-service.sandbox.rabbitmq #0

Need to see who is exposing TCP22 and what it is remapped to ? Easy breezy:

.. code:: python

    $ ocho port 22
    * (2 pods exposing 22) ->
     - 1038		54.237.49.208      my-service.dev.haproxy #0
     - 9093		54.145.22.4        my-service.dev.redis #0

.. _Python: https://www.python.org/
.. _Zookeeper: http://zookeeper.apache.org/



