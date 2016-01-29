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
import tempfile
import threading
import time
import shutil

from argparse import ArgumentParser
from copy import deepcopy
from ochopod.api import Binding, LifeCycle, Model, Tool
from ochopod.core.core import Coordinator
from ochopod.core.fsm import diagnostic, shutdown, spin_lock
from ochopod.core.utils import shell
from ochopod.models.reactive import Actor as Reactive
from os import path
from pykka import ThreadingFuture
from pykka.exceptions import Timeout, ActorDeadError
from flask import Flask, request
from requests import post
from urlparse import urlparse
from werkzeug.exceptions import default_exceptions, HTTPException

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Marathon(Binding):
    """
    Mesosphere/Marathon framework abstract binding, providing some basic environment variable translation (especially
    the port mappings). We run a Flask micro-server to handle leader or CLI requests.

    The pod requires configuration settings from the environment variables. All settings are simple key/value
    pairs prefixed by *ochopod*. These are optional settings you may specify (e.g you can set them in your application
    configuration):

        - *ochopod_cluster*: identifier for the cluster to run this pod under (e.g "database" or "web-server"
          for instance, defaulted to the Marathon application identifier if not specified).
        - *ochopod_debug*: turns debug logging on if set to "true".
        - *ochopod_namespace*: namespace as dot separated tokens (e.g "my-app.staging"), defaulted to "marathon".
        - *ochopod_port*: pod control port on which we listen for HTTP requests, defaulted to 8080.
        - *ochopod_zk*: location of ZK ensemble, default to an empty string. This string must be a well formed ZK URL
         for instance zk://127.0.0.1:2181

    The following payload is registered by the pod at boot time:

        - **cluster**: the pod cluster
        - **namespace**: the pod namespace
        - **binding**: set to *mesos+marathon*
        - **ports**: exposed ports, as a dict
        - **port**: local control port
        - **debug**: true if debug logging is on
        - **application**: controlling Marathon application identifier
        - **task**: underlying Mesos task identifier
        - **seq**: unique pod index within the cluster
        - **node**: resource id of the underlying node running the container.
        - **ip**: local IPv4 for the resource on which the pod is running.
        - **public**: externally reachable resource IPv4 (used for the CLI or 3rd party integrations if applicable).
        - **zk**: connection string for our ZK ensemble.
    """

    def get_node_details(self):
        raise NotImplementedError

    def boot(self, lifecycle, model=Reactive, tools=None, local=False):

        #
        # - quick check to make sure we get the right implementations
        #
        assert issubclass(model, Model), 'model must derive from ochopod.api.Model'
        assert issubclass(lifecycle, LifeCycle), 'lifecycle must derive from ochopod.api.LifeCycle'

        #
        # - instantiate our flask endpoint
        # - default to a json handler for all HTTP errors (including an unexpected 500)
        #
        def _handler(error):
            http = error.code if isinstance(error, HTTPException) else 500
            return '{}', http, {'Content-Type': 'application/json; charset=utf-8'}

        web = Flask(__name__)
        for code in default_exceptions.iterkeys():
            web.error_handler_spec[None][code] = _handler

        #
        # - default presets in case we run outside of marathon (local vm testing)
        # - any environment variable prefixed with "ochopod." is of interest for us (e.g this is what the user puts
        #   in the marathon application configuration for instance)
        # - the other settings come from marathon (namely the port bindings & application/task identifiers)
        # - the MESOS_TASK_ID is important to keep around to enable task deletion via the marathon REST API
        #
        env = \
            {
                'ochopod_application':  '',
                'ochopod_cluster':      'default',
                'ochopod_debug':        'true',
                'ochopod_local':        'false',
                'ochopod_namespace':    'marathon',
                'ochopod_port':         '8080',
                'ochopod_start':        'true',
                'ochopod_task':         '',
                'ochopod_zk':           '',
                'PORT_8080':            '8080'
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
                        'fwk':          'marathon (debug)',
                        'ip':           '127.0.0.1',
                        'node':         'local',
                        'ports':        ports,
                        'public':       '127.0.0.1',
                        'zk':           '127.0.0.1:2181'
                    })
            else:

                #
                # - extend our hints
                # - add the application + task
                #
                hints.update(
                    {
                        'application':  env['MARATHON_APP_ID'][1:],
                        'fwk':          'marathon',
                        'ip':           '',
                        'node':         '',
                        'ports':        ports,
                        'public':       '',
                        'task':         env['MESOS_TASK_ID'],
                        'zk':           ''
                    })

                #
                # - use whatever subclass is implementing us to infer 'ip', 'node' and 'public'
                #
                hints.update(self.get_node_details())

                #
                # - lookup for the zookeeper connection string from environment variable or on disk
                # - we have to look into different places depending on how mesos was installed
                #
                def _1():

                    #
                    # - most recent DCOS release
                    # - $MESOS_MASTER is located in /opt/mesosphere/etc/mesos-slave-common
                    # - the snippet in there is prefixed by MESOS_MASTER=zk://<ip:port>/mesos
                    #
                    logger.debug('checking /opt/mesosphere/etc/mesos-slave-common...')
                    _, lines = shell("grep MESOS_MASTER /opt/mesosphere/etc/mesos-slave-common")
                    return lines[0][13:]

                def _2():

                    #
                    # - same as above except for slightly older DCOS releases
                    # - $MESOS_MASTER is located in /opt/mesosphere/etc/mesos-slave
                    #
                    logger.debug('checking /opt/mesosphere/etc/mesos-slave...')
                    _, lines = shell("grep MESOS_MASTER /opt/mesosphere/etc/mesos-slave")
                    return lines[0][13:]

                def _3():

                    #
                    # - a regular package install will write the slave settings under /etc/mesos/zk (the snippet in
                    #   there looks like zk://10.0.0.56:2181/mesos)
                    #
                    logger.debug('checking /etc/mesos/zk...')
                    _, lines = shell("cat /etc/mesos/zk")
                    return lines[0]

                def _4():

                    #
                    # - look for ZK from environment variables
                    # - user can pass down ZK using $ochopod_zk
                    # - this last-resort situation is used mostly for debugging
                    #
                    logger.debug('checking $ochopod_zk environment variable...')
                    return env['ochopod_zk']

                #
                # - depending on how the slave has been installed we might have to look in various places
                #   to find out what our zookeeper connection string is
                # - use urlparse to keep the host:port part of the URL (possibly including a login+password)
                #
                for method in [_1, _2, _3, _4]:
                    try:
                        hints['zk'] = urlparse(method()).netloc
                        break

                    except Exception:
                        pass

            #
            # - the cluster must be fully qualified with a namespace (which is defaulted anyway)
            #
            assert hints['zk'], 'unable to determine where zookeeper is located (unsupported/bogus mesos setup ?)'
            assert hints['cluster'] and hints['namespace'], 'no cluster and/or namespace defined (user error ?)'

            #
            # - load the tools
            #
            if tools:
                tools = {tool.tag: tool for tool in [clz() for clz in tools if issubclass(clz, Tool)] if tool.tag}
                logger.info('supporting tools %s' % ', '.join(tools.keys()))

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
            logger.info('starting %s.%s (marathon) @ %s' % (hints['namespace'], hints['cluster'], hints['node']))
            breadcrumbs = deepcopy(hints)
            hints['metrics'] = {}
            hints['dependencies'] = model.depends_on
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

                logger.debug('http in -> /reset')
                coordinator.tell({'request': 'reset'})
                return '{}', 200, {'Content-Type': 'application/json; charset=utf-8'}

            #
            # - external hook exposing information about our pod
            # - this is a subset of what's registered in zookeeper at boot-time
            # - the data is dynamic and updated from time to time by the model and executor actors
            # - from @pferro -> the pod's dependencies defined in the model are now added as well
            #
            @web.route('/info', methods=['POST'])
            def _info():

                logger.debug('http in -> /info')
                keys = \
                    [
                        'application',
                        'dependencies',
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
                return json.dumps(subset), 200, {'Content-Type': 'application/json; charset=utf-8'}

            #
            # - external hook exposing our circular log
            # - reverse and dump ochopod.log as a json array
            #
            @web.route('/log', methods=['POST'])
            def _log():

                logger.debug('http in -> /log')
                with open(ochopod.LOG, 'r+') as log:
                    lines = [line for line in log]
                    return json.dumps(lines), 200, {'Content-Type': 'application/json; charset=utf-8'}

            #
            # - RPC call to run a custom tool within the pod
            #
            @web.route('/exec', methods=['POST'])
            def _exec():

                logger.debug('http in -> /exec')

                #
                # - make sure the command (first token in the X-Shell header) maps to a tool
                # - if no match abort on a 404
                #
                line = request.headers['X-Shell']
                tokens = line.split(' ')
                cmd = tokens[0]
                if not tools or cmd not in tools:
                    return '{}', 404, {'Content-Type': 'application/json; charset=utf-8'}

                code = 1
                tool = tools[cmd]

                #
                # - make sure the parser does not sys.exit()
                #
                class _Parser(ArgumentParser):
                    def exit(self, status=0, message=None):
                        raise ValueError(message)

                #
                # - prep a temporary directory
                # - invoke define_cmdline_parsing()
                # - switch off parsing if NotImplementedError is raised
                #
                use_parser = 1
                parser = _Parser(prog=tool.tag)
                try:
                    tool.define_cmdline_parsing(parser)

                except NotImplementedError:
                    use_parser = 0

                tmp = tempfile.mkdtemp()
                try:

                    #
                    # - parse the command line
                    # - upload any attachment
                    #
                    args = parser.parse_args(tokens[1:]) if use_parser else ' '.join(tokens[1:])
                    for tag, upload in request.files.items():
                        where = path.join(tmp, tag)
                        logger.debug('uploading %s @ %s' % (tag, tmp))
                        upload.save(where)

                    #
                    # - run the tool method
                    # - pass the temporary directory as well
                    #
                    logger.info('invoking "%s"' % line)
                    code, lines = tool.body(args, tmp)

                except ValueError as failure:

                    lines = [parser.format_help() if failure.message is None else failure.message]

                except Exception as failure:

                    lines = ['unexpected failure -> %s' % failure]

                finally:

                    #
                    # - make sure to cleanup our temporary directory
                    #
                    shutil.rmtree(tmp)

                out = \
                    {
                        'code': code,
                        'stdout': lines
                    }

                return json.dumps(out), 200, {'Content-Type': 'application/json; charset=utf-8'}

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

                logger.debug('http in -> /control/%s' % task)
                if task not in ['check', 'on', 'off', 'ok', 'kill', 'signal']:

                    #
                    # - fail on a HTTP 400 if the request is not supported
                    #
                    return '{}', 400, {'Content-Type': 'application/json; charset=utf-8'}

                try:

                    ts = time.time()
                    latch = ThreadingFuture()
                    executor.tell({'request': task, 'latch': latch, 'data': request.data})
                    js, code = latch.get(timeout=int(timeout))
                    ms = time.time() - ts
                    logger.debug('http out -> HTTP %s (%d ms)' % (code, ms))
                    return json.dumps(js), code, {'Content-Type': 'application/json; charset=utf-8'}

                except Timeout:

                    #
                    # - we failed to match the specified timeout
                    # - gracefully fail on a HTTP 408
                    #
                    return '{}', 408, {'Content-Type': 'application/json; charset=utf-8'}

                except ActorDeadError:

                    #
                    # - the executor has been shutdown (probably after a /control/kill)
                    # - gracefully fail on a HTTP 410
                    #
                    return '{}', 410, {'Content-Type': 'application/json; charset=utf-8'}

            #
            # - internal hook required to shutdown the web-server
            # - it's not possible to do it outside of a request handler
            # - make sure this calls only comes from localhost (todo)
            #
            @web.route('/terminate', methods=['POST'])
            def _terminate():

                request.environ.get('werkzeug.server.shutdown')()
                return '{}', 200, {'Content-Type': 'application/json; charset=utf-8'}

            #
            # - run werkzeug from a separate thread to avoid blocking the main one
            # - we'll have to shut it down using a dedicated HTTP POST
            #
            class _Runner(threading.Thread):

                def run(self):
                    web.run(host='0.0.0.0', port=int(hints['port']), threaded=True)

            try:

                #
                # - block on the lifecycle actor until it goes down (usually after a /control/kill request)
                #
                _Runner().start()
                spin_lock(latch)
                logger.debug('pod is dead, idling')
                while 1:

                    #
                    # - simply idle forever (since the framework would restart any container that terminates)
                    # - /log and /hints HTTP requests will succeed (and show the pod as being killed)
                    # - any control request will now fail
                    #
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
