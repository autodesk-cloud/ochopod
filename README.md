## Ochopod 

[![Build Status](https://travis-ci.org/autodesk-cloud/ochopod.svg)](https://travis-ci.org/autodesk-cloud/ochopod)

### Overview

This project is a small [**Python**](https://www.python.org/) package you can use to boot your
[**Docker**](https://www.docker.com/) containers. It is by default configured to interface with
[**Apache Mesos**](http://mesos.apache.org/) and its [**Marathon**](https://mesosphere.github.io/marathon/) framework
but could easily be extended to run off [**Kubernetes**](https://github.com/GoogleCloudPlatform/kubernetes) and
the like.

### What does it do ?

Ochopod coordinates how a given family of containers should cluster together at run-time. It transparently
manages dependencies and port remapping as well. In short you effectively apply an _overlay_ to your provisioning
stack that enables you to do _more_ ! It is a mix between an _init system_ and a distributed _discovery mechanism_.

Ochopod internally relies on [**Apache Zookeeper**](http://zookeeper.apache.org/) for synchronization and metadata
storage.

### Ochopod + Mesos + Marathon + CLI == PaaS

Please have a look at our [**Ochothon**](https://github.com/autodesk-cloud/ochothon) stack and see how we built a
quick PaaS on top of [**Marathon**](https://mesosphere.github.io/marathon/) including a comprehensive tool suite, a
cool web-shell, a tiny CLI and more !

Both a manual package install and the spiffy [**DCOS deployments from Mesosphere**](https://mesosphere.com/) have
been tested. We also tested it on the cool [**Mantl.io**](http://mantl.io/) project.

### How is it different ?

The DIY PaaS market is filled with interesting offers and every company has its own take on how to do things. Now
Ochopod is different when it comes to clustering and idempotency. Our general goal is to remain non opiniated (and
lightweight) but yet allow for watertight orchestration. Our _finite state machine_ design coupled to Zookeeper is
quite unique.

### Your base image

In case you had not noticed you can build this repo as a Docker image ! This will give you a basic Ubuntu container
that includes our code, Python 2.7 and the handy supervisor package. We run supervisor as PID 1 and set it up to
listen on TCP 8081 (not exposed).

You can find it on the [**Docker hub**](https://registry.hub.docker.com/) as the _autodeskcloud/pod_ image (tagged
with release numbers).

### Documentation

You can [**peruse our online documentation**](http://autodesk-cloud.github.io/ochopod/) for examples, design notes,
API docs and more !

The [**Sphinx**](http://sphinx-doc.org/) materials can be found under docs/. Just go in there and build for your
favorite target, for instance:

```
$ cd docs
$ make html
```

The docs will be written to _docs/_build/html_. This is all Sphinx based and you have many options and knobs to
tweak should you want to customize the output.

### Support

Contact autodesk.cloud.opensource@autodesk.com for more information about this project.


### License

© 2015 Autodesk Inc.
All rights reserved

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
