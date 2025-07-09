#!/bin/bash

# Deploy The Email Game to Google Cloud Platform
# Usage: ./scripts/deploy_to_gcp.sh [PROJECT_ID] [REGION]

set -e

# Configuration
PROJECT_ID=${1:-"inbox-arena-prod"}
REGION=${2:-"us-central1"}
SERVICE_NAME="inbox-arena"

echo "🚀 Deploying The Email Game to GCP"
echo "================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud"
    echo "Run: gcloud auth login"
    exit 1
fi

# Set project
echo "📋 Setting project..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com

# Generate secure JWT secret
echo "🔐 Generating JWT secret..."
JWT_SECRET=$(openssl rand -base64 32)

# Create or update secrets
echo "🔑 Managing secrets..."
if gcloud secrets describe jwt-secret --quiet >/dev/null 2>&1; then
    echo "   JWT secret already exists, updating..."
    echo -n "$JWT_SECRET" | gcloud secrets versions add jwt-secret --data-file=- --quiet
else
    echo "   Creating new JWT secret..."
    echo -n "$JWT_SECRET" | gcloud secrets create jwt-secret --data-file=- --quiet
fi

# Grant Cloud Run access to secrets
echo "🔐 Setting up IAM permissions for secrets..."
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "   Granting Secret Manager access to: $COMPUTE_SA"
gcloud secrets add-iam-policy-binding jwt-secret \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null || echo "   (Permission may already exist)"

# No Redis needed with in-memory architecture

# Build and deploy
echo "🏗️  Building application..."
gcloud builds submit --config cloudbuild.yaml

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/inbox-arena \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8000 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-secrets "JWT_SECRET=jwt-secret:latest"

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')

echo
echo "✅ Deployment complete!"
echo "🌐 Service URL: $SERVICE_URL"
echo "📊 Dashboard: $SERVICE_URL/"
echo "🏥 Health Check: $SERVICE_URL/health"
echo
echo "🎮 Players can connect using:"
echo "export INBOX_ARENA_SERVER=\"$SERVICE_URL\""
echo "export OPENAI_API_KEY=\"sk-...\"  # Players need their own OpenAI key"
echo "python scripts/connect_to_game.py"
echo
echo "📖 View logs: gcloud logs tail --follow --service=$SERVICE_NAME"