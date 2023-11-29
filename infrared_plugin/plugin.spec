---

config:
  plugin_type: test
  entry_point: main.yaml


subparsers:

  tobiko:
    description: Deploy, configure and execute Tobiko test cases
    include_groups: ["Ansible options", "Inventory", "Common options", "Answers file"]
    groups:

      - title: Common options
        options:
          no-become:
            type: Flag
            help: Forbid roles from escalate tasks execution as superuser
            ansible_variable: test_no_become

      - title: Topology options
        options:
          host:
            type: Value
            help: Target host where test cases are deployed and executed
            ansible_variable: test_host

      - title: Control flow
        options:
          stage:
            type: Value
            ansible_variable: test_stage

      - title: Deploy stage
        options:
          clean:
            type: Flag
            help: Cleanup directory where test cases will be downloaded
            ansible_variable: deploy_clean
          git-base:
            type: Value
            help: Git Url prefix where test projects are fetched from
            ansible_variable: git_base
          test-dir:
            type: Value
            help: Test host directory where test cases (and tox.ini file) are found
            ansible_variable: test_dir
          test-user:
            type: Value
            help: Test host user that should own tests directory
            ansible_variable: test_user
          test-group:
            type: Value
            help: Test host user group that should own tests directory
            ansible_variable: test_group
          test-repo:
            type: Value
            help: Git URL from where to download test files
            ansible_variable: test_git_repo
          test-remote:
            type: Value
            help: Git remote name to be used for checking out test scripts
            ansible_variable: test_git_remote
          test-refspec:
            type: Value
            help: Git refspect to be used for checking out test scripts
            ansible_variable: test_git_refspec
          test-src-dir:
            type: Value
            help: Local directory where test cases (and tox.ini file) are found
            ansible_variable: test_src_dir
          tobiko-dir:
            type: Value
            help: Test host directory where Tobiko has to be deployed to
            ansible_variable: tobiko_dir
          tobiko-user:
            type: Value
            help: Test host user that should own Tobiko directory
            ansible_variable: tobiko_user
          tobiko-group:
            type: Value
            help: Test host user group that should own Tobiko directory
            ansible_variable: tobiko_group
          tobiko-repo:
            type: Value
            help: Git URL from where to download tobiko files
            ansible_variable: tobiko_git_repo
            default: 'https://opendev.org/x/tobiko.git'
          tobiko-remote:
            type: Value
            help: Git remote name to be used for checking out test scripts
            ansible_variable: tobiko_git_remote
          tobiko-refspec:
            type: Value
            help: Git refspect to be used for checking out Tobiko scripts
            ansible_variable: tobiko_git_refspec
          tobiko-src-dir:
            type: Value
            help: Local directory where tobiko scripts are found
            required: yes
            ansible_variable: tobiko_src_dir
            default: '{{ inventory_dir }}/src/tobiko'
          openshift-ir-src-dir:
            type: Value
            help: Local directory where OpenShift InfraRed scripts are deployed from0
            ansible_variable: openshift_infrared_src_dir
          openshift-ir-dir:
            type: Value
            help: Remote directory where OpenShift InfraRed scripts are deployed to
            ansible_variable: openshift_infrared_dir
          openshift-ir-repo:
            type: Value
            help: Git URL from where to download OpenShift InfraRed files
            ansible_variable: openshift_infrared_git_repo
          openshift-ir-remote:
            type: Value
            help: Git remote name to be used for checking out OpenShift InfraRed files
            ansible_variable: openshift_infrared_git_remote
          openshift-ir-refspec:
            type: Value
            help: Git refspect to be used for checking out OpenShift InfraRed files
            ansible_variable: openshift_infrared_git_refspec

      - title: Configure stage
        options:
          config:
            type: Value
            help: tobiko.conf file location
            ansible_variable: test_conf_file
          debug:
            type: Value
            help: enable/disable verbose log entries in tests results log file
            ansible_variable: test_log_debug
            default: 'true'
          test-case-timeout:
            type: Value
            help: Test case timeout in seconds
            ansible_variable: test_case_timeout
          test-runner-timeout:
            type: Value
            help: Test runner timeout in seconds
            ansible_variable: test_runner_timeout
          undercloud_host:
            type: Value
            help: inventory hostname of the undercloud host
            ansible_variable: undercloud_hostname
          undercloud_ssh_host:
            type: Value
            help: hostname or IP address to be used to connect to undercloud host
            ansible_variable: undercloud_ssh_hostname
          undercloud_ssh_key_filename:
            type: Value
            help: SSH key filename to connect to undercloud host
            ansible_variable: undercloud_ssh_key_filename
          overcloud-ssh-username:
            type: Value
            help: user name to be used to connect to TripleO Overcloud hosts
            ansible_variable: overcloud_ssh_username
          has_external_load_balancer:
            type: Bool
            help: OSP env was done with an external load balancer
            ansible_variable: has_external_load_balancer
          manila-share-protocol:
            type: Value
            help: Protocol used when creating a manila share object
            ansible_variable: manila_share_protocol

      - title: Run stage
        options:
          workflow:
            type: Value
            help: name of workflow to execute
            ansible_variable: test_workflow
          failfast:
            type: Flag
            help: Stop the test run on the first step error or failure
            ansible_variable: test_failfast
          tox-dir:
            type: Value
            help: directory from where run tox (typically test_dir)
            ansible_variable: tox_dir
          tox-command:
            type: Value
            help: command to be executed for tox (typically tox)
            ansible_variable: tox_command
          tox-environment:
            type: Value
            help: envitonment variables to be set when running test cases
            ansible_variable: tox_environment
          tox-envlist:
            type: Value
            help: Tox environment names to be executed
            ansible_variable: tox_envlist
          tox-extra-args:
            type: Value
            help: extra options to be passed to Tox
            ansible_variable: tox_extra_args
          tox-python:
            type: Value
            help: Python interpreter to be used for executing test cases
            ansible_variable: tox_python
          pytest-addopts:
            type: Value
            help: >
                Extra options to be passed to PyTest. This value is overriden
                when it is defined at workflow level too.
            ansible_variable: pytest_addopts_global
          pytest-markers:
            type: Value
            help: >
                only run tests matching given mark expression.
                For example: --pytest-markers 'mark1 and not mark2'.
            ansible_variable: pytest_markers
          pytest-maxfail:
            type: Value
            help: Max number of test case failures before aborting
            ansible_variable: pytest_maxfail
          run-tests-timeout:
            type: Value
            help: Timeout (in seconds) to interrupt test cases execution
            ansible_variable: tox_run_tests_timeout
          test-report-dir:
            type: Value
            help: directory where to store test report files
            ansible_variable: test_report_dir
          test-report-name:
            type: Value
            help: prefix used to create report file names
            ansible_variable: test_report_name
          test-log-file:
            type: Value
            help: test cases log file
            ansible_variable: test_log_file
          ignore-test-failures:
            type: Flag
            help: Ignore test execution errors
            ansible_variable: ignore_test_failures
          flaky:
            type: Flag
            help: Ignore flaky test cases
            ansible_variable: test_flaky
          quota:
            type: NestedDict
            action: append
            ansible_variable: quota
            help: |
                Configure quota values for different resources
                These quotas will be applied to the admin openstack project
                Example:
                    --quota routers=30
                    --quota secgroups=50
                Check "openstack quota set --help" for more information
          ceph-rgw:
            type: Bool
            help: Skip Swift containers healthchecks when CephAdm is deployed
            ansible_variable: ceph_rgw
            default: False
          ubuntu-connection-timeout:
            type: Value
            help: |
                Timeout error is raised if a connection to an ubuntu instance
                is not successful before it expires
            ansible_variable: ubuntu_connection_timeout
          ubuntu-is-reachable-timeout:
            type: Value
            help: |
                Timeout error is raised if an ubuntu instance is not reachable
                before it expires
            ansible_variable: ubuntu_is_reachable_timeout
          cleanup-containerlist-file:
            type: Bool
            help:  |
                 Remove containers-list file (saved during a resource creation
                 stage) before running a Tobiko second stage, if we expect changes
                 to the containers list (For example, after the FFU upgrade).
            default: False
            ansible_variable: cleanup_containerlist_file


      - title: Cleanup stage
        options:
          cleanup-heat-stacks:
            type: Flag
            help: Cleanup heat stacks created by tobiko
            ansible_variable: stacks_cleanup

      - title: Collect stage
        options:
          collect-dir:
            type: Value
            help: local directory where report files are going to be copied to
            ansible_variable: test_collect_dir
            default: '{{ inventory_dir }}/{{ test_report_name }}'
