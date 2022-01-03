FROM python:3.10 as base

ENV TOBIKO_DIR=/tobiko
ENV WHEEL_DIR=/wheel

ENV INSTALL_PACKAGES="apt install -y"

# Install binary dependencies
RUN apt update && \
    ${INSTALL_PACKAGES} git

RUN python3 -m ensurepip --upgrade && \
    python3 -m pip install --upgrade setuptools wheel


FROM base as source

# Populate tobiko source dir
# RUN mkdir -p ${TOBIKO_DIR}

ADD .gitignore \
    extra-requirements.txt \
    requirements.txt \
    README.rst \
    setup.cfg \
    setup.py \
    test-requirements.txt \
    upper-constraints.txt \
    ${TOBIKO_DIR}/

ADD .git ${TOBIKO_DIR}/.git/
ADD tobiko/ ${TOBIKO_DIR}/tobiko/


FROM source as build

# Install binary dependencies
# RUN ${INSTALL_PACKAGES} gcc python3-devel

# Build wheel files
RUN python3 -m pip wheel -w ${WHEEL_DIR} \
    -c ${TOBIKO_DIR}/upper-constraints.txt \
    -r ${TOBIKO_DIR}/requirements.txt \
    -r ${TOBIKO_DIR}/test-requirements.txt \
    -r ${TOBIKO_DIR}/extra-requirements.txt \
    --src ${TOBIKO_DIR}/


FROM base as install

# Install wheels
RUN mkdir -p ${WHEEL_DIR}
COPY --from=build ${WHEEL_DIR} ${WHEEL_DIR}
RUN python3 -m pip install ${WHEEL_DIR}/*.whl


FROM source as tobiko

# Install packages
RUN ${INSTALL_PACKAGES} iperf3 iputils-ping ncat

# Run tests variables
ENV PYTHONWARNINGS=ignore::Warning
ENV OS_TEST_PATH=${TOBIKO_DIR}/tobiko/tests/unit
ENV TOX_REPORT_DIR=/report
ENV TOX_REPORT_NAME=tobiko_results
ENV TOBIKO_PREVENT_CREATE=false

# Write log files to report directory
RUN mkdir -p /etc/tobiko
RUN printf "[DEFAULT]\nlog_dir=${TOBIKO_REPORT_DIR}" > /etc/tobiko/tobiko.conf

# Copy python pacakges
COPY --from=install /usr/local /usr/local/

# Copy tobiko tools
ADD tools/ ${TOBIKO_DIR}/tools/

WORKDIR ${TOBIKO_DIR}
CMD tools/run_tests.py ${OS_TEST_PATH}
