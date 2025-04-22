.. _tobiko-test-case-execution-guide:

=================================
Tobiko Test Cases Execution Guide
=================================

This document describes how to execute Tobiko test cases.

.. sidebar:: See also

    For a quick and simpler start you can jump to the
    :ref:`tobiko-quick-start-guide`.

    To install Tobiko inside a virtualenv please read
    :ref:`tobiko-installation-guide`.

    To configure Tobiko please read :ref:`tobiko-configuration-guide`.


Prepare Your System
-------------------

Before running Tobiko test cases, you need to be sure you are doing it from
Tobiko source files folder and that you have activated a virtualenv where Tobiko
is, and its requirements are installed. Please refer to
:ref:`tobiko-installation-guide` and :ref:`tobiko-configuration-guide` to know
how to setup your system before running test cases.

Prepare some logging (Optional and recommended)
------------------------------------------------

To see if we are now being able to execute Tobiko test cases, please open
**a new terminal** and keep it open, where you could watch tobiko.log receive
logs on real time. Change directory to reach the directory where tobiko.log
file is and run the following command::

    tail -F tobiko.log

Prepare advanced image to be used by Tobiko (optional)
------------------------------------------------------

.. include:: _prepare_advanced_image.rst

.. _run-tobiko-test-cases:

Run Tobiko Test Cases
---------------------

.. run-tobiko-test-cases_label

Run Tobiko specific test cases
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _run_specific_tests.rst

Run Scenario Test Cases
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _run_scenario.rst

Running Disruptive Test Cases
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _run_faults.rst

Run the Tobiko Workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _run_workflow.rst

Running Tobiko Test Cases in the Podified environment using ci-framework
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _run_using_ci_framework.rst

Prepare Tobiko Test Pod to run Tobiko
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _prepare_tobiko_test_pod.rst

Test Cases Report Files
~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _test_cases_report_files.rst
