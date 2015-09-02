#
# Copyright (c) 2015 Autodesk Inc.
# All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
This is the high-level SDK API you can use to define your pod. A pod script is made of two things :

  - a **model** defining their clustering characteristics.
  - a **life-cycle** with callbacks defining what is being run and how to tear it down.

In its simplest form a pod script can be as trivial as:

.. code:: python

    from ochopod.bindings.ec2.marathon import Pod
    from ochopod.models.piped import Actor as Piped


    if __name__ == '__main__':

        class Strategy(Piped):

            def configure(self, _):

                return 'redis-server', {}

        Pod().boot(Strategy)

A slightly more complex example (which for instance customizes the clustering model we wish to use and sets
an explicit working directory) could be:

.. code:: python

    from ochopod.bindings.ec2.marathon import Pod
    from ochopod.models.piped import Actor as Piped
    from ochopod.models.reactive import Actor as Reactive


    if __name__ == '__main__':

        class Model(Reactive):

            damper = 30.0
            full_shutdown = True
            sequential = True

        class Strategy(Piped):

            cwd = '/opt/redis'

            def configure(self, _):

                return 'redis-server', {}

        Pod().boot(Strategy, model=Model)

"""


class Cluster(object):
    """
    Cluster description including dependencies. This is what is passed down to you when the pod needs to be configured
    or when a probe() callback is invoked.

    The :attr:`pods` and :attr:`dependencies` dicts contain the registration payload for a set of pods. The keys do
    not really matter (they are random and unique). The payload describes things such as where the pods run, what
    their underlying task identifier is and so on. For instance:

    .. code:: python

        "195bdf5a-8da4-47de-8c87-00429e71d447":
        {
            "application": "my-service.database.342",
            "task": "my-service.database.4c279439-c336-11e4-ac49-56847afe9799",
            "node": "i-d5d1b53a",
            "seq": 19,
            "zk": "10.181.124.223:2181",
            "binding": "marathon-ec2",
            "namespace": "my-service",
            "port": "8080",
            "cluster": "database",
            "ip": "10.109.129.218",
            "debug": "true",
            "local": "false",
            "public": "54.145.22.4",
            "status": "",
            "ports":
            {
                "8080": 1024
            }
        }

    The important settings are "ip", "public" and "ports" (dict indexing ports the container exposes to their
    dynamically allocated counterpart). You may get additional settings depending on which bindings you use.

    The :attr:`seq` integer allows you to identify your pod within your cluster without any ambiguity. The
    :attr:`index` integer has to be used more carefully as any change in the cluster (e.g less pods for instance)
    will not be reflected accurately.
    """

    #: Pod summary describing your dependencies, as a dict (make sure your clustering model specifies dependencies).
    dependencies = {}

    #: Pod index within the cluster (starts at 0). This index is relative to the current cluster and will change
    #: across future configurations should pods be added or removed (do not use it if you need an index that is
    #: guarantee to remain the same during the pod's lifetime). Values are always consecutive (0, 1, 2...).
    index = 0

    #: Internal identifier for the pod being configured. Use pods[key] if you want your settings.
    key = ''

    #: Pod summary describing the cluster, as a dict.
    pods = {}

    #: Monotonic counter allocated to each pod once and guaranteed unique within the cluster over time. This value
    #: is not necessarily spanning a continuous interval but is truly unique and can be used in situations where
    #: you need an index that will never change during the pod's lifetime.
    seq = 0

    #: Total number of pods in the cluster (e.g len(pods)).
    size = 0

    def grep(self, dependency, port, public=False):
        """
        Ancillary helper to look a dependency up by name and return a comma separated connection string. The specified
        connection port is automatically remapped to what the underlying framework allocated. The dependency
        is always assumed to be located in the same namespace.

        Each token within the connection string is laid out as the IP address followed by ':' and a port number. By
        default this method will return internal IP addresses.

        .. warning:: the dependency must be valid otherwise an assert will be raised.
        .. code-block:: python

            cnxstring = cluster.grep('kafka', 9092)

        :type dependency: string
        :type port: int
        :type public: bool
        :param dependency: dependency cluster identifier (e.g 'zookeeper', 'web-server', etc.)
        :param port: TCP port to remap
        :param public: if true the method will return public IP addresses
        :rtype: str
        """
        pass


class Model(object):
    """
    Abstract class defining a clustering model (e.g how pods belonging to the same family will orchestrate to
    end up forming a functional cluster).
    """

    def probe(self, cluster):
        """
        Optional callback invoked at regular intervals by the leader pod to assess the overall cluster health.
        Detailed information about the cluster is passed (similarly to the configuration phase). A typical use case
        would be to check if each peer functions as expected whatever this means given the context. Any exception
        thrown in here will be gracefully trapped and the cluster status set accordingly. An arbitrary status message
        can also be set by returning a string (e.g to indicate some high-level metrics maybe).

        :type cluster: :class:`Cluster`
        :param cluster: the current cluster topology
        :rtype: str or None
        """
        pass


class LifeCycle(object):
    """
    Abstract class defining what your pod does. This is where you implement the configuration logic. You can also
    define several other operations such as the pod initialization or finalization.
    """

    def initialize(self):
        """
        Optional callback invoked at the very first configuration. This can typically be used to implement once-only
        setup operations such as mounting a EBS volume for instance.

        .. warning:: throwing an exception in here will cause the pod to shutdown.
        """
        pass

    def can_configure(self, cluster):
        """
        Optional callback invoked before configuration. Throwing an exception in here will gracefully prevent
        the configuration from happening (at which point the leader will re-schedule it after the damper period
        expires).

        This can be used to check that all dependencies are there (for instance if you require a specific amount of
        nodes). You can also use it to check on other dynamic factors that may influence the configuration process.

        The cluster information passed to you will contain any registered pod, including the ones that may be tagged
        as dead. Please note running this callback does not mean that the configuration will actually happen (another
        pod in the cluster may fail this check).

        :type cluster: :class:`Cluster`
        :param cluster: the current cluster topology
        """
        pass

    def configure(self, cluster):
        """
        Mandatory callback invoked at configuration time. This is where you define what needs to be run by the pod.
        The method must return a 2-uple formed by an invocation line defining what needs to be executed and a
        dict containing environment variable overrides.

        The cluster information passed to you will only contain any registered pod that is not tagged as dead.

        Any environment variable passed to the pod will be also passed down to the underlying process. Any additional
        key/value pair specified in the output dict will be passed as well (e.g you can override variables
        specified at the framework level). Please note all values will be turned into strings.

        Once the process is started it will be monitored on a regular basis. Any successful exit (code 0) will shutdown
        the pod and let it idle until the container is physically destroyed. Any error (exit code between 1 and 254)
        will trigger an automatic process re-start.

        .. warning:: throwing an exception in here will cause the pod to shutdown right away.

        :type cluster: :class:`Cluster`
        :param cluster: the current cluster topology
        :rtype: a (string, dict) 2-uple
        """
        pass

    def configured(self, cluster):
        """
        Optional callback invoked on each pod within a cluster if and only if its configuration process successfully
        completed (the leader will trigger this callback on each pod in parallel). The cluster information is passed
        again for symmetry with the other callbacks. Any exception raised within this callback will be silently trapped.

        :type cluster: :class:`Cluster`
        :param cluster: the current cluster topology
        """
        pass

    def signaled(self, js, process):
        """
        Optional callback invoked upon a user /control/signal HTTP request is sent to the pod. This is meant to be a
        placeholder for situations where one needs to perform out-of-band operations on a pod. Any exception raised
        in this method will result in a HTTP 500 being returned to the caller. Please note you can return arbitrary
        json content as well (handy when building monitoring or deployment tools).

        ..warning:: it is not advised to terminate the underlying process in this method.

        :type js: dict
        :type forked: :class:`subprocess.Popen`
        :param js: optional json payload passed via the HTTP request, can be anything
        :param process: the underlying process run by the pod or None if off
        :rtype: a dict that will be serialized back to the caller as utf-8 json or None
        """
        pass

    def sanity_check(self, process):
        """
        Optional callback invoked at regular interval to check on the underlying process run by the pod. Any exception
        thrown in here will mean that the process should be torn down and restarted. You can typically use this
        mechanism to implement fined-grained control on how your process is behaving (for instance by querying
        some REST API on localhost or by looking at log files).

        This method provides also a way to report arbitrary metrics. An optional dict may be returned to set the
        pod's metrics (which are accessible via a POST /info request). Please note those metrics will be returned as
        serialized json.

        :type process: :class:`subprocess.Popen`
        :param process: the underlying process run by the pod
        :rtype: a dict that will be used as the pod metrics or None
        """
        pass

    def tear_down(self, process):
        """
        Optional callback invoked when the pod needs to tear down the underlying process. The default implementation
        is to send a SIGTERM. You can use this mechanism to implement sophisticated shutdown strategies.

        :type process: :class:`subprocess.Popen`
        :param process: the underlying process run by the pod
        """
        pass

    def finalize(self):
        """
        Optional callback invoked last whenever the pod is shutting down. You can use it to perform cleanup tasks
        (for instance to free-up resources you may have provisioned for the pod, typically some EBS volume).
        """
        pass


class Reactive(Model):
    """
    Specialization of :class:`Model` defining reactive clustering. This means the leader pod will be notified
    whenever any peer either joins or leaves the cluster at which point it will trigger a re-configuration. To import
    its actor implementation do something like:

    .. code:: python

       from ochopod.models.reactive import Actor as Reactive

    """

    #: Delay in seconds between two probes
    probe_every = 60.0

    #: Damper in seconds, e.g how long does the leader pod waits after spotting changes and before configuring.
    #: It is *strongly* advised to set it to something reasonable (30 seconds ?) whenever forming clusters.
    #: Be aware that any sudden drop of connectivity to zookeeper is considered a change, meaning that a small
    #: damper might trigger useless re-configurations. On the other hand a large damper may turned out to be
    #: impractical.
    damper = 0.0

    #: Array listing what clusters we depend on (e.g 'zookeeper' for instance). Those clusters *must* be registered
    #: in the same namespace. A re-configuration will be triggered if any dependency changes.
    depends_on = []

    #: If true the leader will first turn off all pods before configuring them.
    full_shutdown = False

    #: Timeout in seconds when issuing control requests to a pod. This can be changed for instance when dealing
    #: with pods that are known to configure slowly.
    grace = 60.0

    #: If true the leader will fire its control requests to the pods one after the other. Otherwise all the
    #: pods will be sent requests in parallel.
    sequential = False


class Piped(LifeCycle):
    """
    Implementation of :class:`LifeCycle` defining a pod that will configure and manage an underlying sub-process.
    You **must** specialize this class in your pod script to at least provide the :meth:`LifeCycle.configure`
    callback. To import its actor implementation do something like:

    .. code:: python

       from ochopod.models.piped import Actor as Piped
    """

    #: Number of sanity checks we can afford to fail before turning the sub-process off.
    checks = 1

    #: Delay in seconds between two sanity checks.
    check_every = 60.0

    #: Optional working directory to explicitly enforce when running the sub-process. If not defined the
    #: sub-process will be run the current directory, wherever that may be (usually / if you are running your
    #: pod script from an init service).
    cwd = None

    #: Grace period in seconds, e.g how long does the pod wait before forcefully killing its sub-process (SIGKILL).
    #: The termination is done by default with a SIGTERM (but can be overwritten using :meth:`LifeCycle.tear_down`
    #: and/or the soft switch).
    grace = 60.0

    #: If true the pod will pipe stdout/stderr from the sub-process into the ochopod log.
    pipe_subprocess = False

    #: If true the sub-process will interpret its command line as a shell command (e.g you can use pipes for instance).
    shell = False

    #: If true the pod will **not** attempt to force a SIGKILL to terminate the sub-process. Be careful as this may
    #: possibly lead to leaking your process if :meth:`LifeCycle.tear_down` is defined (and not killing it). Use this
    #: option to handle uncommon scenarios (for instance a 0-downtime HAProxy re-configuration).
    soft = False

    #: If true the pod will always configure itself whenever requested by the leader. If false it will only do so
    #: either upon the first leader request (e.g when it joins the cluster) or if its dependencies change. This
    #: mechanism ensures we don't restart the underlying sub-process for no reason, typically when scaling the
    #: cluster capacity up or down.
    strict = False


class Binding(object):
    """
    Abstract class defining the interface to start a pod given a specific framework (e.g Mesosphere/Marathon over EC2
    for instance).
    """

    def boot(self, lifecycle, model=Reactive, local=False):
        """
        Pod entry point. You must specify a class that implements :class:`LifeCycle' and may also specify the
        clustering model you wish to use.

        This binding ties the pod to a specific environment and framework (e.g specific environment variables
        and port mappings will be handled transparently at that level). Upon starting the pod will register its
        data and attempt to become the leader.

        The pod will also start a micro web-server and listen for requests (either control commands or informative
        queries).

        .. warning:: do not run this over multiple threads as you would register more than one pods at once.

        :type lifecycle: :class:`LifeCycle`
        :param lifecycle: the lifecycle implementation class to use
        :type model: :class:`Model`
        :param model: the model implementation class to use (defaulted to :class:`Reactive`)
        :type local: bool
        :param local: if set to True the pod will run locally (and assume a local Zookeeper server)
        """
        pass
