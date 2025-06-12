#!/bin/bash
# Script to create an OpenSearch domain, set up required indices, and store all configuration in AWS Secrets Manager

set -e

# Default values
DOMAIN_NAME="oasis-domain"
INSTANCE_TYPE="r7g.large.search"
INSTANCE_COUNT=1
VOLUME_SIZE=50
REGION=$(aws configure get region || echo "us-east-1")
INDEX_PREFIX="app-logs"
MASTER_USER="admin"
MASTER_PASSWORD="Admin$(openssl rand -base64 8)!2"
SECRET_NAME="oasis-configuration"
MODEL_ID="us.anthropic.claude-sonnet-4-20250514-v1:0"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --domain-name)
      DOMAIN_NAME="$2"
      shift 2
      ;;
    --instance-type)
      INSTANCE_TYPE="$2"
      shift 2
      ;;
    --instance-count)
      INSTANCE_COUNT="$2"
      shift 2
      ;;
    --volume-size)
      VOLUME_SIZE="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --index-prefix)
      INDEX_PREFIX="$2"
      shift 2
      ;;
    --master-user)
      MASTER_USER="$2"
      shift 2
      ;;
    --master-password)
      MASTER_PASSWORD="$2"
      shift 2
      ;;
    --secret-name)
      SECRET_NAME="$2"
      shift 2
      ;;
    --model-id)
      MODEL_ID="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Prompt for email settings
read -p "Enter sender email address: " SENDER_EMAIL
read -p "Enter recipient email address: " RECIPIENT_EMAIL

echo "Creating OpenSearch domain: $DOMAIN_NAME"
echo "Region: $REGION"
echo "Sender email: $SENDER_EMAIL"
echo "Recipient email: $RECIPIENT_EMAIL"

# Create OpenSearch domain with fine-grained access control
aws opensearch create-domain \
  --domain-name "$DOMAIN_NAME" \
  --engine-version "OpenSearch_2.19" \
  --cluster-config "InstanceType=$INSTANCE_TYPE,InstanceCount=$INSTANCE_COUNT" \
  --ebs-options "EBSEnabled=true,VolumeType=gp3,VolumeSize=$VOLUME_SIZE" \
  --node-to-node-encryption-options "Enabled=true" \
  --encryption-at-rest-options "Enabled=true" \
  --domain-endpoint-options "EnforceHTTPS=true" \
  --advanced-security-options "Enabled=true,InternalUserDatabaseEnabled=true,MasterUserOptions={MasterUserName=$MASTER_USER,MasterUserPassword=$MASTER_PASSWORD}" \
  --access-policies '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"*"},"Action":"es:*","Resource":"arn:aws:es:'$REGION':'"$(aws sts get-caller-identity --query Account --output text)"':domain/'$DOMAIN_NAME'/*"}]}' \
  --region "$REGION"


echo "Waiting for OpenSearch domain to become active (this may take 15-20 minutes)..."
# Wait for domain to be active by polling the status
while true; do
  STATUS=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query "DomainStatus.Processing" --output text)
  if [ "$STATUS" == "False" ]; then
    echo "Domain is now active"
    break
  fi
  echo "Domain is still processing... waiting 60 seconds"
  sleep 60
done

# Get domain endpoint with retry logic
MAX_RETRIES=10
RETRY_COUNT=0
VALID_ENDPOINT=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$VALID_ENDPOINT" = false ]; do
  DOMAIN_ENDPOINT=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query "DomainStatus.Endpoint" --output text)
  
  if [ -z "$DOMAIN_ENDPOINT" ] || [ "$DOMAIN_ENDPOINT" = "None" ]; then
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo "Invalid domain endpoint received. Retrying in 30 seconds... (Attempt $RETRY_COUNT of $MAX_RETRIES)"
    sleep 30
  else
    VALID_ENDPOINT=true
    echo "OpenSearch domain endpoint: https://$DOMAIN_ENDPOINT"
  fi
done

if [ "$VALID_ENDPOINT" = false ]; then
  echo "Failed to get a valid domain endpoint after $MAX_RETRIES attempts. Exiting."
  exit 1
fi

echo "Setting up required indices..."

# Create the required indices
echo "Creating logs index..."
curl -XPUT -k -u "$MASTER_USER:$MASTER_PASSWORD" "https://$DOMAIN_ENDPOINT/${INDEX_PREFIX}-logs" \
  -H 'Content-Type: application/json' \
  -d '{
    "mappings": {
      "properties": {
        "timestamp": { "type": "date" },
        "service": { "type": "keyword" },
        "level": { "type": "keyword" },
        "message": { "type": "text" },
        "error_type": { "type": "keyword" },
        "status_code": { "type": "integer" }
      }
    }
  }'

echo "Creating metrics index..."
curl -XPUT -k -u "$MASTER_USER:$MASTER_PASSWORD" "https://$DOMAIN_ENDPOINT/${INDEX_PREFIX}-metrics" \
  -H 'Content-Type: application/json' \
  -d '{
    "mappings": {
      "properties": {
        "timestamp": { "type": "date" },
        "service": { "type": "keyword" },
        "metric_name": { "type": "keyword" },
        "value": { "type": "float" },
        "unit": { "type": "keyword" }
      }
    }
  }'

echo "Creating agent findings index..."
curl -XPUT -k -u "$MASTER_USER:$MASTER_PASSWORD" "https://$DOMAIN_ENDPOINT/${INDEX_PREFIX}-agent-findings" \
  -H 'Content-Type: application/json' \
  -d '{
    "mappings": {
      "properties": {
        "timestamp": { "type": "date" },
        "finding_id": { "type": "keyword" },
        "title": { "type": "text" },
        "description": { "type": "text" },
        "severity": { "type": "keyword" },
        "status": { "type": "keyword" },
        "related_resources": { "type": "object" },
        "proposed_actions": { "type": "text" },
        "human_approved": { "type": "boolean" },
        "human_feedback": { "type": "text" },
        "updated_at": { "type": "date" }
      }
    }
  }'

# Create API Gateway for approval workflow
echo "Creating API Gateway..."
API_NAME="oasis-approval-api"
API_ID=$(aws apigateway create-rest-api \
  --name "$API_NAME" \
  --description "API for OASIS approval workflow" \
  --region "$REGION" \
  --query "id" --output text)

# Get the root resource ID
ROOT_RESOURCE_ID=$(aws apigateway get-resources \
  --rest-api-id "$API_ID" \
  --region "$REGION" \
  --query "items[?path=='/'].id" --output text)

# Create a resource
RESOURCE_ID=$(aws apigateway create-resource \
  --rest-api-id "$API_ID" \
  --parent-id "$ROOT_RESOURCE_ID" \
  --path-part "approve" \
  --region "$REGION" \
  --query "id" --output text)

# Create a GET method
aws apigateway put-method \
  --rest-api-id "$API_ID" \
  --resource-id "$RESOURCE_ID" \
  --http-method GET \
  --authorization-type NONE \
  --region "$REGION"

# Create a mock integration for the API
aws apigateway put-integration \
  --rest-api-id "$API_ID" \
  --resource-id "$RESOURCE_ID" \
  --http-method GET \
  --type MOCK \
  --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
  --region "$REGION"

# Set up the integration response
aws apigateway put-integration-response \
  --rest-api-id "$API_ID" \
  --resource-id "$RESOURCE_ID" \
  --http-method GET \
  --status-code 200 \
  --response-templates '{"application/json": "{\"message\": \"Approval request received\"}"}' \
  --region "$REGION"

# Set up the method response
aws apigateway put-method-response \
  --rest-api-id "$API_ID" \
  --resource-id "$RESOURCE_ID" \
  --http-method GET \
  --status-code 200 \
  --response-models '{"application/json": "Empty"}' \
  --region "$REGION"

# Deploy the API
aws apigateway create-deployment \
  --rest-api-id "$API_ID" \
  --stage-name prod \
  --region "$REGION"

# Get the API Gateway URL
API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/approve"
echo "API Gateway URL: $API_URL"

# Store all configuration in AWS Secrets Manager
echo "Storing configuration in AWS Secrets Manager..."

# Create JSON for secret value
SECRET_JSON=$(cat << EOF
{
  "opensearch": {
    "endpoint": "https://$DOMAIN_ENDPOINT",
    "username": "$MASTER_USER",
    "password": "$MASTER_PASSWORD",
    "region": "$REGION",
    "index_prefix": "$INDEX_PREFIX"
  },
  "api_gateway": {
    "approval_url": "$API_URL"
  },
  "email": {
    "sender": "$SENDER_EMAIL",
    "recipient": "$RECIPIENT_EMAIL"
  },
  "strands": {
    "model_id": "$MODEL_ID",
    "region": "$REGION"
  }
}
EOF
)

# Check if secret already exists
SECRET_ARN=$(aws secretsmanager list-secrets --query "SecretList[?Name=='$SECRET_NAME'].ARN" --output text --region "$REGION")

if [ -z "$SECRET_ARN" ]; then
  # Create new secret
  SECRET_ARN=$(aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --description "OASIS configuration and credentials" \
    --secret-string "$SECRET_JSON" \
    --region "$REGION" \
    --query "ARN" --output text)
  
  echo "Created new secret: $SECRET_ARN"
else
  # Update existing secret
  aws secretsmanager update-secret \
    --secret-id "$SECRET_ARN" \
    --secret-string "$SECRET_JSON" \
    --region "$REGION"
  
  echo "Updated existing secret: $SECRET_ARN"
fi

echo "Setup complete!"
echo "OpenSearch domain: $DOMAIN_NAME (https://$DOMAIN_ENDPOINT)"
echo "API Gateway URL: $API_URL"
echo "All configuration stored in AWS Secrets Manager: $SECRET_NAME"
echo ""
echo "To use this configuration in your application, set these environment variables:"
echo "export OASIS_SECRET_NAME=$SECRET_NAME"
echo "export OASIS_SECRET_REGION=$REGION"