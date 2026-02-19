#!/bin/bash
set -e

# Configuration
PROJECT_ID="YOUR_PROJECT_ID_HERE" # TODO: Replace with your Project ID
REGION="us-central1"
REPO_NAME="aegis-repo"
IMAGE_TAG="latest" # You can use specific version tags or git commit hash
ARTIFACT_REGISTRY_HOST="$REGION-docker.pkg.dev"

echo "🚀 Starting Deployment to GCP for Project: $PROJECT_ID"

# 1. Authenticate Docker with GCP
echo "🔐 Configuring Docker authentication..."
gcloud auth configure-docker $ARTIFACT_REGISTRY_HOST

# 2. Build and Push Backend
echo "🔨 Building Backend..."
docker build -t $ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/backend:$IMAGE_TAG ./backend
echo "fw Pushing Backend..."
docker push $ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/backend:$IMAGE_TAG

# 3. Build and Push Frontend
echo "🔨 Building Frontend..."
docker build -t $ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/frontend:$IMAGE_TAG ./frontend
echo "fw Pushing Frontend..."
docker push $ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/frontend:$IMAGE_TAG

# 4. Deploy with Helm
echo "☸️  Deploying to GKE..."
# Ensure you are connected to the cluster:
# gcloud container clusters get-credentials aegis-cluster --region $REGION

helm upgrade --install aegis ./helm/aegis \
  -f ./helm/aegis/values-prod.yaml \
  --set backend.image.repository=$ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/backend \
  --set backend.image.tag=$IMAGE_TAG \
  --set frontend.image.repository=$ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/frontend \
  --set frontend.image.tag=$IMAGE_TAG \
  --namespace aegis-system \
  --create-namespace

echo "✅ Deployment pipeline finished!"
