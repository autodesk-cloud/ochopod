## Ochopod

### Overview

This project is a small [**Python**](https://www.python.org/) package you can use to boot your
[**Docker**](https://www.docker.com/) containers. It is configured to interface with various
[**Apache Mesos**](http://mesos.apache.org/) frameworks and coordinates how a given family of containers should
cluster together at run-time. It transparently manages dependencies and port remapping as well.

Ochopod uses the [**Apache Zookeeper**](http://zookeeper.apache.org/) ensemble used by Mesos for synchronization
and data storage, so that you do not have to add yet another piece to the puzzle. The SDK also comes with a set of
command line tools you can use to automate operations around your containers !

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