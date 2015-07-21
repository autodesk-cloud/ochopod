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
import json
import logging
import ochopod
import os
import threading
import time

from copy import deepcopy
from ochopod.api import LifeCycle, Model
from ochopod.bindings.ec2.api import EC2Marathon
from ochopod.core.core import Coordinator
from ochopod.core.fsm import diagnostic, shutdown, spin_lock
from ochopod.core.utils import shell
from ochopod.models.reactive import Actor as Reactive
from pykka import ThreadingFuture
from pykka.exceptions import Timeout, ActorDeadError
from flask import Flask, request
from requests import post

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Pod(EC2Marathon):
    """
    Implementation for the :class:`ochopod.bindings.ec2.api.EC2Marathon` interface.
    """

    def boot(self, lifecycle, model=Reactive, local=0):

        #
        # - quick check to make sure we get the right implementations
        #
        assert issubclass(model, Model), 'model must derive from ochopod.api.Model'
        assert issubclass(lifecycle, LifeCycle), 'lifecycle must derive from ochopod.api.LifeCycle'

        #
        # - start logging to /var/log/ochopod.log
        #
        logger.info('EC2 marathon bindings started')
        web = Flask(__name__)

        #
        # - default presets in case we run outside of marathon (local vm testing)
        # - any environment variable prefixed with "ochopod." is of interest for us (e.g this is what the user puts
        #   in the marathon application configuration for instance)
        # - the other settings come from marathon (namely the port bindings & application/task identifiers)
        # - the MESOS_TASK_ID is important to keep around to enable task deletion via the marathon REST API
        #
        env = \
            {
                'ochopod_application': '',
                'ochopod_cluster': 'default',
                'ochopod_debug': 'true',
                'ochopod_local': 'false',
                'ochopod_namespace': 'marathon',
                'ochopod_port': '8080',
                'ochopod_start': 'true',
                'ochopod_task': '',
                'PORT_8080': '8080'
            }

        env.update(os.environ)
        ochopod.enable_cli_log(debug=env['ochopod_debug'] == 'true')
        try:

            #
            # - grab our environment variables (which are set by the marathon executor)
            # - extract the mesos PORT_* bindings and construct a small remapping dict
            #
            ports = {}
            logger.debug('environment ->\n%s' % '\n'.join(['\t%s -> %s' % (k, v) for k, v in env.items()]))
            for key, val in env.items():
                if key.startswith('PORT_'):
                    ports[key[5:]] = int(val)

            #
            # - keep any "ochopod_" environment variable & trim its prefix
            # - default all our settings, especially the mandatory ones
            # - the ip and zookeeper are defaulted to localhost to enable easy testing
            #
            hints = {k[8:]: v for k, v in env.items() if k.startswith('ochopod_')}
            if local or hints['local'] == 'true':

                #
                # - we are running in local mode (e.g on a dev workstation)
                # - default everything to localhost
                #
                logger.info('running in local mode (make sure you run a standalone zookeeper)')
                hints.update(
                    {
                        'fwk': 'marathon-ec2',
                        'ip': '127.0.0.1',
                        'node': 'local',
                        'ports': ports,
                        'public': '127.0.0.1',
                        'zk': '127.0.0.1:2181'
                    })
            else:

                #
                # - we are (assuming to be) deployed on EC2
                # - get our underlying metadata using curl
                #
                def _peek(token, strict=True):
                    code, lines = shell('curl -f http://169.254.169.254/latest/meta-data/%s' % token)
                    assert not strict or code is 0, 'unable to lookup EC2 metadata for %s (are you running on EC2 ?)' % token
                    return lines[0]

                #
                # - get our local and public IPV4 addresses
                # - the "node" will show up as the EC2 instance ID
                # - note we allow the public IPv4 lookup to fail (in case we run in VPC)
                #
                hints.update(
                    {
                        'application': env['MARATHON_APP_ID'][1:],
                        'fwk': 'marathon-ec2',
                        'ip': _peek('local-ipv4'),
                        'node': _peek('instance-id'),
                        'ports': ports,
                        'public': _peek('public-ipv4', strict=False),
                        'task': env['MESOS_TASK_ID'],
                        'zk': ''
                    })

                def _install_from_package():

                    #
                    # - a regular package install will write the slave settings under /etc/mesos/zk
                    # - the snippet in there looks like zk://10.0.0.56:2181/mesos
                    #
                    code, lines = shell("cat /etc/mesos/zk")
                    assert code is 0 and lines[0], 'unable to retrieve the zk connection string'
                    return lines[0][5:].split('/')[0]

                def _dcos_deployment():

                    #
                    # - a DCOS slave is setup slightly differently with the settings being environment
                    #   variables set in /opt/mesosphere/etc/mesos-slave
                    # - the snippet in there is prefixed by MESOS_MASTER= and uses an alias
                    # - it looks like MESOS_MASTER=zk://leader.mesos:2181/mesos
                    #
                    code, lines = shell("grep MASTER /opt/mesosphere/etc/mesos-slave")
                    assert code is 0 and lines[0], 'unable to retrieve the zk connection string'
                    return lines[0][18:].split('/')[0]

                #
                # - depending on how the slave has been installed we might have to look in various places
                #   to find out what our zookeeper connection string is
                # - warning, a URL like format such as zk://<ip:port>,..,<ip:port>/mesos is used
                # - just keep the ip & port part and discard the rest
                #
                for method in [_install_from_package, _dcos_deployment]:
                    try:
                        hints['zk'] = method()
                        break

                    except:
                        pass

                assert hints['zk'], 'unable to determine where zookeeper is located (unsupported/bogus setup ?)'

            #
            # - the cluster must be fully qualified with a namespace (which is defaulted anyway)
            #
            assert hints['cluster'] and hints['namespace'], 'no cluster and/or namespace defined (user error ?)'

            #
            # - start the life-cycle actor which will pass our hints (as a json object) to its underlying sub-process
            # - start our coordinator which will connect to zookeeper and attempt to lead the cluster
            # - upon grabbing the lock the model actor will start and implement the configuration process
            # - the hints are a convenient bag for any data that may change at runtime and needs to be returned (via
            #   the HTTP POST /info request)
            # - what's being registered in zookeeper is immutable though and decorated with additional details by
            #   the coordinator (especially the pod index which is derived from zookeeper)
            #
            latch = ThreadingFuture()
            logger.info('starting %s.%s (marathon/ec2) @ %s' % (hints['namespace'], hints['cluster'], hints['node']))
            breadcrumbs = deepcopy(hints)
            hints['metrics'] = {}
            env.update({'ochopod': json.dumps(hints)})
            executor = lifecycle.start(env, latch, hints)
            coordinator = Coordinator.start(
                hints['zk'].split(','),
                hints['namespace'],
                hints['cluster'],
                int(hints['port']),
                breadcrumbs,
                model,
                hints)

            #
            # - external hook forcing a coordinator reset
            # - this will force a re-connection to zookeeper and pod registration
            # - please note this will not impact the pod lifecycle (e.g the underlying sub-process will be
            #   left running)
            #
            @web.route('/reset', methods=['POST'])
            def _reset():
                coordinator.tell({'request': 'reset'})
                return '{}', 200

            #
            # - external hook exposing information about our pod
            # - this is a subset of what's registered in zookeeper at boot-time
            # - the data is dynamic and updated from time to time by the model and executor actors
            #
            @web.route('/info', methods=['POST'])
            def _info():
                keys = \
                    [
                        'application',
                        'ip',
                        'metrics',
                        'node',
                        'port',
                        'ports',
                        'process',
                        'public',
                        'state',
                        'status',
                        'task'
                    ]

                subset = dict(filter(lambda i: i[0] in keys, hints.iteritems()))
                return json.dumps(subset), 200

            #
            # - external hook exposing our circular log
            # - reverse and dump ochopod.log as a json array
            #
            @web.route('/log', methods=['POST'])
            def _log():
                with open(ochopod.LOG, 'r+') as log:
                    lines = [line for line in log]
                    return json.dumps(lines), 200

            #
            # - web-hook used to receive requests from the leader or the CLI tools
            # - those requests are passed down to the executor actor
            # - any non HTTP 200 response is a failure
            # - failure to acknowledge within the specified timeout will result in a HTTP 408 (REQUEST TIMEOUT)
            # - attempting to send a control request to a dead pod will result in a HTTP 410 (GONE)
            #
            @web.route('/control/<task>', methods=['POST'])
            @web.route('/control/<task>/<timeout>', methods=['POST'])
            def _control(task, timeout='60'):
                try:

                    ts = time.time()
                    logger.debug('http in -> /control/%s' % task)
                    latch = ThreadingFuture()
                    executor.tell({'request': task, 'latch': latch, 'data': request.data})
                    js, code = latch.get(timeout=int(timeout))
                    ms = time.time() - ts
                    logger.debug('http out -> HTTP %s (%d ms)' % (code, ms))
                    return json.dumps(js), code

                except Timeout:

                    #
                    # - we failed to match the specified timeout
                    # - gracefully fail on a HTTP 408
                    #
                    return '{}', 408

                except ActorDeadError:

                    #
                    # - the executor has been shutdown (probably after a /control/kill)
                    # - gracefully fail on a HTTP 410
                    #
                    return '{}', 410

            #
            # - internal hook required to shutdown the web-server
            # - it's not possible to do it outside of a request handler
            # - make sure this calls only comes from localhost (todo)
            #
            @web.route('/terminate', methods=['POST'])
            def _terminate():
                request.environ.get('werkzeug.server.shutdown')()
                return '{}', 200

            class _Runner(threading.Thread):
                """
                Run werkzeug from a separate thread to avoid blocking the main one. We'll have to shut it down
                using a dedicated HTTP POST.
                """

                def run(self):
                    web.run(host='0.0.0.0', port=int(hints['port']), threaded=True)

            try:

                #
                # - block on the lifecycle actor until it goes down (usually after a /control/kill request)
                #
                _Runner().start()
                spin_lock(latch)
                logger.debug('pod is dead, idling')

                #
                # - simply idle forever (since the framework would restart any container that terminates)
                # - /log and /hints HTTP requests will succeed (and show the pod as being killed)
                # - any control request will now fail
                #
                while 1:
                    time.sleep(60.0)

            finally:

                #
                # - when we exit the block first shutdown our executor (which may probably be already down)
                # - then shutdown the coordinator to un-register from zookeeper
                # - finally ask werkzeug to shutdown via a REST call
                #
                shutdown(executor)
                shutdown(coordinator)
                post('http://127.0.0.1:%s/terminate' % env['ochopod_port'])

        except KeyboardInterrupt:

            logger.fatal('CTRL-C pressed')

        except Exception as failure:

            logger.fatal('unexpected condition -> %s' % diagnostic(failure))