#!/bin/bash
# Start Cassandra using Docker or Podman

set -e

# Detect container runtime
if command -v docker &> /dev/null; then
    CONTAINER_RUNTIME="docker"
elif command -v podman &> /dev/null; then
    CONTAINER_RUNTIME="podman"
else
    echo "❌ Neither Docker nor Podman is installed. Please install one of them."
    exit 1
fi

echo "🐳 Using container runtime: $CONTAINER_RUNTIME"

# Stop any existing Cassandra container
echo "🛑 Stopping existing Cassandra container if any..."
$CONTAINER_RUNTIME stop cassandra-test 2>/dev/null || true
$CONTAINER_RUNTIME rm cassandra-test 2>/dev/null || true

# Start Cassandra
echo "🚀 Starting Apache Cassandra 5.0..."
$CONTAINER_RUNTIME run -d \
    --name cassandra-test \
    -p 9042:9042 \
    -e CASSANDRA_CLUSTER_NAME=TestCluster \
    -e CASSANDRA_DC=datacenter1 \
    -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch \
    -e HEAP_NEWSIZE=128M \
    -e MAX_HEAP_SIZE=512M \
    cassandra:latest

# Wait for Cassandra to be ready
echo "⏳ Waiting for Cassandra to be ready (this may take 30-60 seconds)..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if $CONTAINER_RUNTIME exec cassandra-test cqlsh -e "describe keyspaces" &> /dev/null; then
        echo "✅ Cassandra is ready!"
        break
    fi
    echo -n "."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Cassandra failed to start in time"
    $CONTAINER_RUNTIME logs cassandra-test
    exit 1
fi

echo ""
echo "📊 Cassandra container info:"
$CONTAINER_RUNTIME ps | grep cassandra-test

echo ""
echo "🔍 To check logs: $CONTAINER_RUNTIME logs -f cassandra-test"
echo "🛑 To stop: $CONTAINER_RUNTIME stop cassandra-test"
echo "🧹 To remove: $CONTAINER_RUNTIME rm cassandra-test"