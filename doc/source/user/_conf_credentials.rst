Configure Tobiko Credentials
----------------------------

Tobiko needs to have Keystone credentials in order to run the OpenStack test cases.
We are going to assume you are using one of the two OpenStack distributions
supported by Tobiko:

- DevStack
- TripleO

Get credentials from a DevStack host
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copy the `clouds.yaml <https://docs.openstack.org/python-openstackclient/latest/configuration/index.html#clouds-yaml>`__
file from your remote cloud to any one of the below locations:

  - Tobiko source files directory
  - ~/.config/openstack
  - /etc/openstack


| The clouds.yaml file contains valid Keystone credentials.

You can copy the file in the following way::

    ssh <... connection options here ...> cat /etc/openstack/clouds.yaml > clouds.yaml


Get credentials from a TripleO undercloud host
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tobiko test cases will be able to setup some type of SSH tunneling
to be able to reach the remote cloud, but for achieving it you are
required to be able to connect to a remote SSH server that is
able to connect the OpenStack services and hosts. We will
refer to that server as the SSH proxy host.

Tobiko test cases will execute some commands on the SSH proxy host
(like ping, nc, curl, etc).
Those commands need to have direct connectivity to target cloud.

Test cases will use Python REST API clients configured to make HTTP
requests coming out from such SSH server (mainly by using nc
command) or SSH server direct connect feature.

Test cases will make all SSH connection to cloud nodes by using
this SSH proxy host.

To resume the purpose of the SSH proxy, all network packages
sent by Tobiko test cases to the tested cloud will come from the
SSH proxy host, while all Tobiko test cases will be executed
from the developer workstation.

SetUp SSH public key to connect to remote cloud
+++++++++++++++++++++++++++++++++++++++++++++++

First of all we need to make sure we can connect to the SSH proxy server
without requiring any password.
We therefore need to have a local SSH key pair to be used by tobiko.
This key by default is the same default one used by openSSH client:
- default SSH private key filename:  `~/.ssh/id_rsa`
- default SSH public key filename:  `~/.ssh/id_rsa.pub`


**Note: In case that you already have a public key which does not require a**
**password (it requires an empty passphrase), you can skip the ssh keypair**
**creation (continue with**
:ref:`defining your ssh variables <define-your-ssh-variables>`
**).**

In case that you don't, to avoid having problems with other uses of the same
file, let's instead create our SSH key pair only for Tobiko in a sub-folder
near to your tobiko.conf

Make sure you run the following commands in the tobiko directory.
Ensure we do have this key pair on your workstation by typing::

    mkdir -p .ssh
    chmod 700 .ssh
    ssh-keygen -v -f .ssh/id -N ''
    chmod 600 .ssh/id .ssh/id.pub

.. _define-your-ssh-variables:

Define the below SSH variables to later connect to your SSH server::

    SSH_HOST=<your-ssh-proxy-address>
    SSH_USERNAME=<your-ssh-proxy-user>

For example::

    SSH_HOST=seal100.your.domain
    SSH_USERNAME=root

Copy your SSH public key to your remote server::

    ssh-copy-id -i .ssh/id "${SSH_USERNAME}@${SSH_HOST}"


Make sure the SSH key pair is working::

    ssh -i .ssh/id "${SSH_USERNAME}@${SSH_HOST}" hostname


Now let's make sure Tobiko test cases will use the SSH key pair to connect
to your SSH remote host. Add the following lines to tobiko.conf file::

    [ssh]
    proxy_jump = SSH_USERNAME@SSH_HOST

For example::

    [ssh]
    proxy_jump = root@seal100.your.domain
    #proxy_jump = root@seal99.your.domain
    #proxy_jump = root@seal98.your.domain

.. tip::
    You could have multiple hosts in your tobiko.conf [ssh] section, where the
    ones you are not currently using are commented (as appear above).
    Moving your tobiko tests from one host to another will be as easy as
    commenting the host you are stop using and uncommenting the one you are
    start using (remember to copy your SSH key to your other remote hosts as well).
