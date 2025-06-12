#!/bin/bash
# Script to clean up all resources created by setup_oasis.sh

set -e

# Default values
REGION=$(aws configure get region || echo "us-east-1")
DOMAIN_NAME="oasis-domain"
SECRET_NAME="oasis-configuration"
API_NAME="oasis-approval-api"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    --domain-name)
      DOMAIN_NAME="$2"
      shift 2
      ;;
    --secret-name)
      SECRET_NAME="$2"
      shift 2
      ;;
    --api-name)
      API_NAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

echo "Cleaning up OASIS resources in region $REGION..."

# Get API IDs (there might be multiple with the same name)
echo "Finding API Gateway..."
API_IDS=$(aws apigateway get-rest-apis --region $REGION --query "items[?name=='$API_NAME'].id" --output text)

# Delete each API with the specified name
for API_ID in $API_IDS; do
  if [ -n "$API_ID" ]; then
    echo "Deleting API Gateway: $API_NAME ($API_ID)"
    aws apigateway delete-rest-api --rest-api-id "$API_ID" --region $REGION
    echo "API Gateway $API_ID deleted"
    # Add delay to avoid TooManyRequestsException
    echo "Waiting 30 seconds before next deletion to avoid rate limiting..."
    sleep 30
  fi
done

if [ -z "$API_IDS" ]; then
  echo "API Gateway not found, skipping"
fi

# Delete Secret
echo "Finding Secret..."
SECRET_EXISTS=$(aws secretsmanager list-secrets --region $REGION --query "SecretList[?Name=='$SECRET_NAME'].ARN" --output text)

if [ -n "$SECRET_EXISTS" ]; then
  echo "Deleting Secret: $SECRET_NAME"
  aws secretsmanager delete-secret --secret-id $SECRET_NAME --force-delete-without-recovery --region $REGION
  echo "Secret deleted"
else
  echo "Secret not found, skipping"
fi

# Delete OpenSearch domain
echo "Finding OpenSearch domain..."
DOMAIN_EXISTS=$(aws opensearch describe-domain --domain-name $DOMAIN_NAME --region $REGION --query "DomainStatus.DomainName" --output text 2>/dev/null || echo "")

if [ -n "$DOMAIN_EXISTS" ]; then
  echo "Deleting OpenSearch domain: $DOMAIN_NAME"
  aws opensearch delete-domain --domain-name $DOMAIN_NAME --region $REGION
  echo "OpenSearch domain deletion initiated (this may take several minutes to complete)"
else
  echo "OpenSearch domain not found, skipping"
fi

echo "Cleanup complete!"
echo "Note: OpenSearch domain deletion may still be in progress. You can check the status with:"
echo "aws opensearch describe-domain --domain-name $DOMAIN_NAME --region $REGION"