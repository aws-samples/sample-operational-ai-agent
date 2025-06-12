#!/bin/bash
set -e

# Configuration
LAMBDA_NAME="oasis"
REGION="us-east-1"
ROLE_NAME="oasis-role"
STRANDS_LAYER_NAME="strands-layer"
RULE_NAME="oasis-trigger"
API_NAME="${LAMBDA_NAME}-approval-api"
S3_BUCKET="lambda-layers-${REGION}-$(aws sts get-caller-identity --query 'Account' --output text)"

echo "Starting cleanup of Smart Assistant resources..."

# Remove CloudWatch Events rule and targets
echo "Removing CloudWatch Events rule..."
aws events remove-targets --rule $RULE_NAME --ids "1" --region $REGION || echo "No targets to remove"
aws events delete-rule --name $RULE_NAME --region $REGION || echo "No rule to delete"

# Remove Lambda function
echo "Removing Lambda function..."
aws lambda delete-function --function-name $LAMBDA_NAME --region $REGION || echo "No Lambda function to delete"

# Remove Lambda layers
echo "Removing Lambda layers..."
LAYER_VERSIONS=$(aws lambda list-layer-versions --layer-name $STRANDS_LAYER_NAME --region $REGION --query 'LayerVersions[*].Version' --output text)
for VERSION in $LAYER_VERSIONS; do
  echo "Deleting layer version $VERSION..."
  aws lambda delete-layer-version --layer-name $STRANDS_LAYER_NAME --version-number $VERSION --region $REGION
done

# Remove IAM role and policies
echo "Removing IAM role and policies..."
# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# Detach policies
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --region $REGION || echo "No Lambda basic execution policy to detach"
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-opensearch-policy --region $REGION || echo "No OpenSearch policy to detach"
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-bedrock-policy --region $REGION || echo "No Bedrock policy to detach"
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-secrets-policy --region $REGION || echo "No Secrets policy to detach"
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-ses-policy --region $REGION || echo "No SES policy to detach"

# Delete policies
aws iam delete-policy --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-opensearch-policy --region $REGION || echo "No OpenSearch policy to delete"
aws iam delete-policy --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-bedrock-policy --region $REGION || echo "No Bedrock policy to delete"
aws iam delete-policy --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-secrets-policy --region $REGION || echo "No Secrets policy to delete"
aws iam delete-policy --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/oasis-ses-policy --region $REGION || echo "No SES policy to delete"

aws iam delete-role --role-name $ROLE_NAME --region $REGION || echo "No role to delete"

# Clean S3 bucket
echo "Cleaning S3 bucket..."
aws s3 rm s3://$S3_BUCKET/strands_layer.zip --region $REGION || echo "No S3 object to delete"

# Optional: Delete S3 bucket (uncomment if needed)
# echo "Deleting S3 bucket..."
# aws s3 rb s3://$S3_BUCKET --force --region $REGION || echo "No S3 bucket to delete"

echo "Cleanup completed successfully!"