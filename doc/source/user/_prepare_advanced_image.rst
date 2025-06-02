Some of the Tobiko tests, like e.g.
``tobiko/tests/scenario/neutron/test_network.py::BackgroundProcessTest``. In the
CI jobs, this is done by the `tobiko-download-images
<https://opendev.org/x/tobiko/src/branch/master/roles/tobiko-download-images/tasks/main.yaml>`_
Ansible role but if Tobiko tests are executed locally it may be needed to
prepare such image and upload it to Glance.
This can be done with simple script::

    $ wget https://download.fedoraproject.org/pub/fedora/linux/releases/40/Cloud/x86_64/images/Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2 \
        -O /tmp/Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2

    $ cat << EOF > /tmp/iperf3-server.service
    [Unit]
    Description=iperf3 server on port 5201
    After=syslog.target network.target
    [Service]
    ExecStart=/usr/bin/iperf3 -s -p 5201
    Restart=always
    User=root
    [Install]
    WantedBy=multi-user.target
    EOF

    $ cat << EOF > /tmp/nginx_id.conf
    server{
        listen 80;
        listen [::]:80;
        location /id { add_header Content-Type text/plain; return 200 '$hostname';}
    }
    EOF

    $ cat << EOF > /tmp/config
    SELINUX=permissive
    SELINUXTYPE=targeted
    EOF

    $ TMPPATH=$(mktemp)
    $ cp /tmp/Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2 $TMPPATH
    $ LIBGUESTFS_BACKEND=direct
    $ virt-customize -a $TMPPATH \
          --copy-in /tmp/config:/etc/selinux \
          --firstboot-command 'sh -c "nmcli connection add type vlan con-name vlan101 ifname vlan101 vlan.parent eth0 vlan.id 101 ipv6.addr-gen-mode default-or-eui64"' \
          --install iperf3,iputils,nmap-ncat,nginx \
          --copy-in /tmp/nginx_id.conf:/etc/nginx/conf.d \
          --run-command 'systemctl enable nginx' \
          --copy-in /tmp/iperf3-server.service:/etc/systemd/system \
          --run-command 'systemctl enable iperf3-server' \
          --root-password password:tobiko \
          --selinux-relabel

    $ mv TMPPATH /tmp/Fedora_customized.qcow2
    $ chmod a+r /tmp/Fedora_customized.qcow2

To use this image in Tobiko, it needs to be set in the Tobiko config file::

    $ cat tobiko.conf
    [advanced_vm]
    image_name = Fedora_customized
    image_url=file:///tmp/Fedora_customized.qcow2
    container_format=bare
    disk_format=qcow2
    username=fedora
