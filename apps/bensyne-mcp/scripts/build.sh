#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Get version from pyproject.toml
VERSION=$(python3.12 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

# Docker config
REPO="${DOCKER_REPO:-tuiteraz}"
IMAGE_NAME="${DOCKER_IMAGE:-bensyne}"

# Tags: numeric (X.X.X) and latest
TAGS=("${VERSION}" "latest")

IMAGE_FULL="${REPO}/${IMAGE_NAME}:${VERSION}"

# Build image
echo "Building Docker image: $IMAGE_FULL"
docker build -t "$IMAGE_FULL" .

# Tag image
for tag in "${TAGS[@]}"; do
    docker tag "$IMAGE_FULL" "${REPO}/${IMAGE_NAME}:${tag}"
done
echo "Tagged: ${REPO}/${IMAGE_NAME} with ${TAGS[*]}"

# Push to DockerHub (use PUSH_TO_REGISTRY=true or pass --push flag)
PUSH="${PUSH_TO_REGISTRY:-${1:-false}}"
if [ "$PUSH" = "true" ] || [ "$PUSH" = "--push" ]; then
    echo "Pushing to DockerHub..."
    docker push "$IMAGE_FULL"
    for tag in "${TAGS[@]}"; do
        docker push "${REPO}/${IMAGE_NAME}:${tag}"
    done
    echo "Push complete!"
else
    echo "Build complete! (use PUSH_TO_REGISTRY=true ./scripts/build.sh or ./scripts/build.sh --push)"
fi
