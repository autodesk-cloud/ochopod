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
This is a collection of binding interfaces meant to be used on AWS/EC2.
"""
from ochopod.api import Binding


class EC2Marathon(Binding):
    """
    Mesosphere/Marathon framework binding for pods running on AWS/EC2, providing some basic environment variable
    translation (especially the port mappings). We run a Flask micro-server to handle leader or CLI requests. The
    pod IP addresses are retrieved via the EC2 instance metadata.

    You **must** run this on a EC2 instance with Apache Mesos installed unless you use the local mode in which case
    everything will be assumed to run on localhost (include Zookeeper). You also **must** mount /etc/mesos onto the
    container (preferably in read-only mode).

    The pod requires configuration settings from the environment variables. All settings are simple key/value
    pairs prefixed by *ochopod*. These are optional settings you may specify (e.g you can set them in your application
    configuration):

        - *ochopod_cluster*: identifier for the cluster to run this pod under (e.g "database" or "web-server"
          for instance, defaulted to the Marathon application identifier if not specified).
        - *ochopod_debug*: turns debug logging on if set to "true".
        - *ochopod_namespace*: namespace as dot separated tokens (e.g "my-app.staging"), defaulted to "marathon".
        - *ochopod_port*: pod control port on which we listen for HTTP requests, defaulted to 8080.

    The following payload is registered by the pod at boot time:

        - **cluster**: the pod cluster
        - **namespace**: the pod namespace
        - **binding**: set to *marathon*
        - **ports**: port remapping, as a dict
        - **port**: local control port
        - **debug**: true if debug logging is on
        - **application**: Marathon application identifier
        - **task**: Mesos task identifier
        - **seq**: unique pod index within the cluster
        - **node**: EC2 instance id of the underlying node running the container.
        - **ip**: EC2 instance local IPv4.
        - **public**: externally reachable EC2 instance IPv4 (used for the CLI or 3rd party integrations).
        - **zk**: connection string for our Zookeeper ensemble (looked up from /etc/mesos/zk).
    """
    pass

class EC2Kubernetes(Binding):

    pass