API
===

General
_______

.. automodule:: ochopod
   :members: enable_cli_log

Data model
__________

.. automodule:: api
.. autoclass:: Model
   :members: probe
.. autoclass:: Cluster
   :members: dependencies, index, key, pods, seq, size, grep
.. autoclass:: LifeCycle
   :members: initialize, can_configure, configure, configured, sanity_check, tear_down, signaled, finalize
.. autoclass:: Reactive
   :members: probe_every, damper, depends_on, full_shutdown, grace, sequential
.. autoclass:: Piped
   :members: checks, check_every, cwd, grace, pipe_subprocess, shell, strict, soft

Bindings
________

.. autoclass:: bindings.ec2.api.EC2Marathon
.. autoclass:: bindings.ec2.api.EC2Kubernetes