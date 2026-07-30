#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Get version from project.yaml
VERSION=$(yq '.version' project.yaml)
REPO=$(yq '.docker.repository' project.yaml)
IMAGE_NAME=$(yq '.docker.image_name' project.yaml)

# Set tags
TAGS=("latest" "v${VERSION}" "dev")

# Build image
echo "Building Docker image..."
docker build -t "${REPO}/${IMAGE_NAME}:${VERSION}" .

# Tag image
for tag in "${TAGS[@]}"; do
    docker tag "${REPO}/${IMAGE_NAME}:${VERSION}" "${REPO}/${IMAGE_NAME}:${tag}"
done

# Push to DockerHub
if [ "${PUSH_TO_REGISTRY:-false}" = "true" ]; then
    echo "Pushing to DockerHub..."
    docker push "${REPO}/${IMAGE_NAME}:${VERSION}"
    for tag in "${TAGS[@]}"; do
        docker push "${REPO}/${IMAGE_NAME}:${tag}"
    done
fi

echo "Build complete!"
