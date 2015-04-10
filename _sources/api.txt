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
.. autoclass:: Cluster
   :members: dependencies, index, key, pods, seq, size, grep
.. autoclass:: LifeCycle
   :members: initialize, can_configure, configure, sanity_check, tear_down, signaled, finalize
.. autoclass:: Reactive
   :members: damper, depends_on, full_shutdown, grace, sequential
.. autoclass:: Piped
   :members: checks, cwd, grace, shell, strict

Bindings
________

.. autoclass:: bindings.ec2.api.EC2Marathon