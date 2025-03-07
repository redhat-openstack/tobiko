Tobiko can be run through the `Test-operator
<https://github.com/openstack-k8s-operators/test-operator>`_. This can be done
manually, following the Test-operator documentation but it may require some
additional preparation tasks, like e.g. prepare ssh keys which are required by
the Tobiko tests.
To avoid extra manual steps, Tobiko can be run using `ci-framework
<https://ci-framework.readthedocs.io/en/latest>`_.

Clone ci-framework on the host with access to the OpenShift API::

    $ git clone https://github.com/openstack-k8s-operators/ci-framework

Install required ansible-galaxy dependencies::

    $ cd ci-framework
    $ ansible-galaxy install -r requirements.yml

Additonally create directory where ci-framework and Test-operator will store
some data. In the example below it is `/tmp/ci-fmw`::

    $ mkdir /tmp/ci-fmw

Create Tobiko custom variables file. It will be placed in
`ci-framework/custom/tobiko_vars.yaml` and its content should be something
like::

    $ cat custom/tobiko_vars.yaml
    ---
    ansible_user_dir: '/tmp/ci-fmw'
    cifmw_openshift_kubeconfig: '/home/zuul/.crc/machines/crc/kubeconfig'
    cifmw_run_tests: true
    cifmw_run_test_role: test_operator
    cifmw_test_operator_stages:
     - name: tobiko-stage-1
       type: tobiko
       test_vars:
         cifmw_test_operator_tobiko_image: 'quay.io/podified-antelope-centos9/openstack-tobiko'
         cifmw_test_operator_tobiko_image_tag: 'current-podified'
         cifmw_test_operator_tobiko_testenv: 'scenario -- tobiko/tests/scenario/neutron/test_network.py::BackgroundProcessTest'
         cifmw_test_operator_tobiko_debug: true
    cifmw_test_operator_cleanup: false

Most important lines in this file are ``cifmw_test_operator_tobiko_testenv``
where Tobiko test environment and even specific test(s) which should be run
can be specified.
There is also ``cifmw_test_operator_tobiko_debug`` which if set to `True` will
prevent Tobiko POD to be deleted. After tests will finish, POD will still be
there and it will be possible to connect to it and run or even modify Tobiko
tests as needed.
