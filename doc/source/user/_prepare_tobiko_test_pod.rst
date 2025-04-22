Prepare tobiko test pod to run tobiko tests

You may want to run tests from the tobiko test pod. To enable that, some more steps are required:

Log in to the tobiko test pod::

   $ oc rsh <tobiko-test pod name> /bin/bash
   bash-5.1$ cd ~
   bash-5.1$ pwd
   /var/lib/tobiko
   bash-5.1$ cd tobiko/

Export the OS_CLOUD value::

   $ export OS_CLOUD=default

To run tests dedicated for podified environment you will need to authenticate the openshift cluster from the tobiko pod before running them::

   $ cp /var/lib/tobiko/.kube/config /tmp/kubeconfig
   $ sudo chmod a+w /tmp/kubeconfig
   $ export KUBECONFIG=/tmp/kubeconfig
   $ oc login -u kubeadmin -p ...

Now, when the pod is ready to run tobiko, you can modify the code and test it locally.
For example::

   $ tox -e scenario
   $ tox -e sanity -- tobiko/tests/sanity/nova/test_server.py::CrateDeleteServerStackTest::test_1_create_server
   $ tox -e podified_ha_faults -- tobiko/tests/faults/podified/ha/test_cloud_recovery.py::DisruptPodifiedNodesTest::test_remove_one_grastate_galera

To monitor the progress of the tests, log in the test pod from another terminal window and run::

   $ cd ~/tobiko
   $ tail -F tobiko.log


Tip:
You may want to test your tobiko code locally using ipython.
To install ipython, first, create tox virtual environment::

   $ cd ~/tobiko/
   $ tox -e py3 -- notests

Then, install and run ipython::

   $ .tox/py3/bin/pip install ipython
   $ .tox/py3/bin/ipython


Tip
You can use the openstack client binary that is installed under the tobiko tox virtual environment::

   $ .tox/py3/bin/openstack --insecure service list

Or, in more common way, by accessing the openstackclient pod::

   $ oc exec openstackclient -- openstack server list
