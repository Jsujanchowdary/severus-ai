FROM alpine:3.19

RUN apk add --no-cache curl bash

WORKDIR /stress
COPY stress_pod.sh .

ENTRYPOINT ["sh", "stress_pod.sh"]