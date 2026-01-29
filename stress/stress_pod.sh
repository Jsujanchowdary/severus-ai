#!/bin/sh

TARGET="$1"
REQUESTS=500
CONCURRENCY=30

echo "🔥 Stress testing target: $TARGET"

i=0
while [ $i -lt $REQUESTS ]; do
  curl -s --max-time 5 "$TARGET" >/dev/null &
  i=$((i+1))

  if [ $((i % CONCURRENCY)) -eq 0 ]; then
    wait
  fi
done

wait
echo "✅ Stress test completed"