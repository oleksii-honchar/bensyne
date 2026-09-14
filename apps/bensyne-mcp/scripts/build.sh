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

# Buildx platforms (multi-arch; default: linux/amd64 + linux/arm64)
PLATFORMS="${DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"
# Optional explicit builder; default is to use the current buildx builder
BUILDER="${DOCKER_BUILDER:-}"

# Build + push image (buildx multi-platform so amd64 and arm64 both get a manifest)
PUSH="${PUSH_TO_REGISTRY:-${1:-false}}"
if [ "$PUSH" = "true" ] || [ "$PUSH" = "--push" ]; then
    echo "Building + pushing multi-platform image: $PLATFORMS"
    TAGS_ARGS=()
    for tag in "${TAGS[@]}"; do
        TAGS_ARGS+=("-t" "${REPO}/${IMAGE_NAME}:${tag}")
    done
    BUILDER_ARGS=()
    if [ -n "$BUILDER" ]; then
        docker buildx build \
            --builder "$BUILDER" \
            --platform "$PLATFORMS" \
            "${TAGS_ARGS[@]}" \
            --push \
            .
    else
        docker buildx build \
            --platform "$PLATFORMS" \
            "${TAGS_ARGS[@]}" \
            --push \
            .
    fi
    echo "Push complete! (platforms: $PLATFORMS, tags: ${TAGS[*]})"
else
    echo "Building Docker image (host platform): $IMAGE_FULL"
    docker build -t "$IMAGE_FULL" .
    echo "Build complete! (use PUSH_TO_REGISTRY=true ./scripts/build.sh or ./scripts/build.sh --push)"
fi
