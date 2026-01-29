FROM ubuntu:22.04

ARG KUBECTL_VERSION=v1.29.0

RUN apt-get update && \
    apt-get install -y curl bash ca-certificates && \
    curl -LO https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm -rf /var/lib/apt/lists/* kubectl

WORKDIR /stress
COPY stress_pod.sh .
RUN chmod +x stress_pod.sh

ENTRYPOINT ["./stress_pod.sh"]
