# Docker Hub Publishing Guide

This guide explains how to build and publish the AnyIDE Docker image to Docker Hub.

## Prerequisites

- Docker installed and running
- Docker Hub account
- Logged in to Docker Hub (`docker login`)

## Building the Image

### Standard Build

```bash
# Build with default tag
docker build -t anyide:latest .

# Build with specific version tag
docker build -t anyide:0.1.0 .
```

### Multi-platform Build (Recommended)

For compatibility with different architectures:

```bash
# Enable buildx for multi-platform builds
docker buildx create --use

# Build for multiple platforms
docker buildx build --platform linux/amd64,linux/arm64 -t anyide:latest .
```

## Tagging Convention

Use semantic versioning:

```bash
# Latest stable release
docker tag anyide:latest keyurgolani/anyide:latest

# Specific version
docker tag anyide:latest keyurgolani/anyide:0.1.0

# Version series
docker tag anyide:latest keyurgolani/anyide:0.1
```

## Publishing to Docker Hub

### Step 1: Login

```bash
docker login
```

### Step 2: Tag the Image

```bash
# Replace 'keyurgolani' with your Docker Hub username
docker tag anyide:latest keyurgolani/anyide:latest
docker tag anyide:latest keyurgolani/anyide:0.1.0
```

### Step 3: Push

```bash
docker push keyurgolani/anyide:latest
docker push keyurgolani/anyide:0.1.0
```

### One-liner

```bash
docker build -t keyurgolani/anyide:latest -t keyurgolani/anyide:0.1.0 . && \
docker push keyurgolani/anyide:latest && \
docker push keyurgolani/anyide:0.1.0
```

## GitHub Actions Automation

Create `.github/workflows/docker-publish.yml`:

```yaml
name: Docker Publish

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/anyide:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/anyide:${{ steps.version.outputs.VERSION }}
```

## Docker Hub Repository Setup

1. Create repository on Docker Hub:
   - Go to https://hub.docker.com/
   - Click "Create Repository"
   - Name: `anyide`
   - Description: "Unified MCP + OpenAPI Tool Server for Self-Hosted LLM Stacks"
   - Set visibility (public recommended)

2. Add repository description:
   ```markdown
   # AnyIDE

   Unified MCP + OpenAPI Tool Server for Self-Hosted LLM Stacks

   ## Quick Start

   ```bash
   docker run -d \
     -p 8080:8080 \
     -v ./workspace:/workspace \
     -v ./data:/data \
     -e ADMIN_PASSWORD=your_password \
     -e WORKSPACE_BASE_DIR=/workspace \
     keyurgolani/anyide:latest
   ```

   ## Features

   - Dual Protocol Support: MCP + OpenAPI
   - Filesystem, Shell, Git, Docker tools
   - Knowledge Graph Memory
   - DAG-based Plan Execution
   - HITL Approval System
   - Admin Dashboard

   ## Documentation

   - [GitHub Repository](https://github.com/keyurgolani/anyide)
   - [Documentation](https://github.com/keyurgolani/anyide#readme)
   ```

3. Configure webhooks (optional):
   - For automated deployments
   - For CI/CD integration

## Version Management

### Creating a Release

```bash
# 1. Update version in code
# 2. Commit changes
git commit -am "Release v0.1.0"

# 3. Create tag
git tag v0.1.0

# 4. Push tag
git push origin v0.1.0

# 5. GitHub Actions will build and publish automatically
```

### Rolling Back

```bash
# Re-tag a previous version as latest
docker pull keyurgolani/anyide:0.0.9
docker tag keyurgolani/anyide:0.0.9 keyurgolani/anyide:latest
docker push keyurgolani/anyide:latest
```

## Security Best Practices

1. **Never commit secrets** to the repository
2. Use GitHub secrets for Docker Hub credentials
3. Scan images for vulnerabilities:
   ```bash
   docker scout cves keyurgolani/anyide:latest
   ```
4. Sign images with Docker Content Trust
5. Use minimal base images for smaller attack surface

## Verification

After publishing, verify the image:

```bash
# Pull fresh image
docker pull keyurgolani/anyide:latest

# Run and test
docker run -d \
  --name anyide-verify \
  -p 8080:8080 \
  -e ADMIN_PASSWORD=test \
  -e WORKSPACE_BASE_DIR=/workspace \
  -v ./workspace:/workspace \
  -v ./data:/data \
  -v ./secrets:/secrets \
  -v ./skills:/skills \
  keyurgolani/anyide:latest

# Check health
curl http://localhost:8080/health

# Optional: quick MCP initialize check (requires explicit Accept header)
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1.0"}}}'

# Cleanup
docker rm -f anyide-verify
```
