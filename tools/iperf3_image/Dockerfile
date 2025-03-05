FROM quay.io/centos/centos:stream10

ENV INSTALL_PACKAGES="dnf install -y"

RUN ${INSTALL_PACKAGES} iperf3

ENTRYPOINT ["iperf3"]
