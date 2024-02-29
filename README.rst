======
Tobiko
======


Test Big Cloud Operations
-------------------------

Tobiko is an OpenStack testing framework focusing on areas mostly
complementary to `Tempest <https://docs.openstack.org/tempest/latest/>`__.
While Tempest main focus has been testing OpenStack rest APIs, the main Tobiko
focus is to test OpenStack system operations while "simulating"
the use of the cloud as the final user would.

Tobiko's test cases populate the cloud with workloads such as Nova instances;
they execute disruption operations such as services/nodes restart; finally they
run test cases to validate that the cloud workloads are still functional.

Tobiko's test cases can also be used, for example, for testing that previously
created workloads are working right after OpenStack services update/upgrade
operation.


Project Requirements
--------------------

Tobiko Python framework is being automatically tested with below Python
versions:

- Python 3.8
- Python 3.9
- Python 3.10 (new)

and below Linux distributions:

- CentOS 9 / RHEL 8 (with Python 3.9)
- Ubuntu Focal (with Python 3.8)
- Ubuntu Jammy (with Python 3.10)

Tobiko has also been tested for development purposes with below OSes:

- OSX (with Python 3.6 to 3.10)

The Tobiko Python framework is being used to implement test cases. As Tobiko
can be executed on nodes that are not part of the cloud to test against, this
doesn't mean Tobiko requires cloud nodes have to run with one of above Python
versions or Linux distributions.

There is also a Docker file that can be used to create a container for running
test cases from any node that do support containers execution.


Main Project Goals
~~~~~~~~~~~~~~~~~~

- To test OpenStack and Red Hat OpenStack Platform projects before they are
  released.
- To provide a Python framework to write system scenario test cases (create
  and test workloads).
- To verify previously created workloads are working fine after executing
  OpenStack nodes update/upgrade.
- To write white boxing test cases (to log to cloud nodes
  for internal inspection purpose).
- To write disruptive test cases (to simulate
  service disruptions like for example rebooting/interrupting a service to
  verify cloud reliability).
- To provide Ansible roles implementing a workflow designed to run an ordered
  sequence of test suites. For example a workflow could do below steps:

  - creates workloads;
  - run disruptive test cases (IE reboot OpenStack nodes or services);
  - verify workloads are still working.

  The main use of these roles is writing continuous integration jobs for Zuul
  or other services like Jenkins (IE by using the Tobiko InfraRed plug-in).
- To provide tools to monitor and recollect the healthy status of the cloud as
  seen from user perspective (black-box testing) or from an inside point of
  view (white-box testing built around SSH client).


References
----------

* Free software: Apache License, Version 2.0
* Documentation: https://tobiko.readthedocs.io/
* Release notes: https://docs.openstack.org/releasenotes/tobiko/
* Source code: https://opendev.org/x/tobiko
* Bugs: https://storyboard.openstack.org/#!/project/x/tobiko
* Code review: https://review.opendev.org/q/project:x/tobiko


Related projects
~~~~~~~~~~~~~~~~
* OpenStack: https://www.openstack.org/
* Red Hat OpenStack Platform: https://www.redhat.com/en/resources/openstack-platform-datasheet
* Python: https://www.python.org/
* Testtools: https://github.com/testing-cabal/testtools
* Ansible: https://www.ansible.com/
* InfraRed: https://infrared.readthedocs.io/en/latest/
* DevStack: https://docs.openstack.org/devstack/latest/
* Zuul: https://docs.openstack.org/infra/system-config/zuul.html
* Jenkins: https://www.jenkins.io/
