# One image plays every fleet role (web, app, db); the ROLE env var picks the service.
# SIMULATION ONLY: the SSH key is baked in, so never reuse this pattern for real hosts.
FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server python3 iproute2 procps nginx socat \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /data /srv \
    && useradd -m -s /bin/bash -p '*' ops \
    && mkdir -p /home/ops/.ssh

# Key-only SSH for the ops user. Dropped into sshd_config.d so it wins over the defaults.
RUN printf 'PasswordAuthentication no\nPermitRootLogin no\nAllowUsers ops\n' > /etc/ssh/sshd_config.d/10-fleet.conf

COPY ssh/id_fleet.pub /home/ops/.ssh/authorized_keys
RUN chown -R ops:ops /home/ops/.ssh && chmod 700 /home/ops/.ssh && chmod 600 /home/ops/.ssh/authorized_keys

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
