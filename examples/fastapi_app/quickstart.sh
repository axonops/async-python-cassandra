#!/bin/bash
# Quick start script for FastAPI + async-cassandra example

set -e

echo "🚀 FastAPI + async-cassandra Quick Start"
echo "========================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Function to run docker-compose
run_compose() {
    if command -v docker-compose &> /dev/null; then
        docker-compose "$@"
    else
        docker compose "$@"
    fi
}

# Stop any existing containers
echo "🛑 Stopping existing containers..."
run_compose down

# Start the services
echo "🐳 Starting Cassandra and FastAPI..."
run_compose up -d

# Wait for Cassandra to be ready
echo "⏳ Waiting for Cassandra to be ready (this may take a minute)..."
until docker exec fastapi-cassandra cqlsh -e "describe keyspaces" &> /dev/null; do
    printf "."
    sleep 5
done
echo " ✓"

# Wait for FastAPI to be ready
echo "⏳ Waiting for FastAPI to be ready..."
until curl -s http://localhost:8000/health > /dev/null; do
    printf "."
    sleep 2
done
echo " ✓"

# Check health
echo ""
echo "🏥 Checking application health..."
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo "✅ Application is ready!"
echo ""
echo "📚 Available endpoints:"
echo "  - API Documentation: http://localhost:8000/docs"
echo "  - ReDoc: http://localhost:8000/redoc"
echo "  - Health Check: http://localhost:8000/health"
echo ""
echo "🧪 To run tests:"
echo "  pytest test_fastapi_integration.py"
echo ""
echo "📊 To run performance tests:"
echo "  python3 performance_test.py"
echo ""
echo "🛑 To stop the application:"
echo "  docker-compose down"
echo ""
echo "📖 For more information, see README.md"