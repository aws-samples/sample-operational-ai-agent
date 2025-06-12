#!/bin/bash
set -e

# Configuration
LAMBDA_NAME="oasis"
REGION=$(aws configure get region || echo "us-east-1")
ROLE_NAME="oasis-role"
STRANDS_LAYER_NAME="strands-layer-v1"
TIMEOUT=900
MEMORY_SIZE=1024

echo "Starting deployment of Smart Assistant Lambda..."

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    --function-name)
      LAMBDA_NAME="$2"
      shift 2
      ;;
    --memory-size)
      MEMORY_SIZE="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

# Create directory for deployment package
echo "Creating deployment package..."
DEPLOY_DIR="deployment_package"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

# Create and activate virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Check if required files exist
echo "Checking for required files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -f "$PROJECT_ROOT/agents/smartAssistant.py" ]; then
  echo "ERROR: smartAssistant.py not found at $PROJECT_ROOT/agents/smartAssistant.py"
  echo "Current directory: $(pwd)"
  echo "Script directory: $SCRIPT_DIR"
  echo "Project root: $PROJECT_ROOT"
  deactivate
  rm -rf venv
  exit 1
fi

# Copy Lambda function code
echo "Copying Lambda function code..."
mkdir -p $DEPLOY_DIR
cp "$PROJECT_ROOT/agents/smartAssistant.py" $DEPLOY_DIR/
cp "$PROJECT_ROOT/agents/deploymentSpecialist.py" $DEPLOY_DIR/
mkdir -p $DEPLOY_DIR/agent_tools
cp -r "$PROJECT_ROOT/agents/agent_tools/"* $DEPLOY_DIR/agent_tools/
mkdir -p $DEPLOY_DIR/lib
cp -r "$PROJECT_ROOT/lib/"* $DEPLOY_DIR/lib/

# Create minimal config.yaml for deployment
echo "Creating config.yaml for deployment..."
cat > $DEPLOY_DIR/config.yaml << EOL
# OpenSearch Configuration
opensearch:
  endpoint: "https://operational-ai-opensearch.us-east-1.es.amazonaws.com"
  region: "$REGION"
  auth_type: "aws_sigv4"
  index_prefix: "app-logs"
EOL

# Copy requirements.txt if it exists
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
  echo "Copying requirements.txt..."
  cp "$PROJECT_ROOT/requirements.txt" $DEPLOY_DIR/
fi

# Install dependencies directly in the package
echo "Installing dependencies..."
if [ -f "$DEPLOY_DIR/requirements.txt" ]; then
  echo "Installing dependencies from requirements.txt..."
  pip install -r $DEPLOY_DIR/requirements.txt -t $DEPLOY_DIR --platform manylinux2014_x86_64 --implementation cp --only-binary=:all: --upgrade
else
  echo "Installing dependencies manually..."
  pip install opensearch-py requests pyyaml requests-aws4auth faker python-dateutil schedule pydantic networkx -t $DEPLOY_DIR --platform manylinux2014_x86_64 --implementation cp --only-binary=:all: --upgrade
fi

# Ensure pydantic and its dependencies are properly installed
echo "Installing pydantic with binary dependencies..."
pip install pydantic==2.4.2 -t $DEPLOY_DIR --platform manylinux2014_x86_64 --implementation cp --only-binary=:all: --upgrade

# Create Strands Lambda layer
echo "Creating Strands Lambda layer..."
mkdir -p strands_layer/python

# Install only the minimal required packages
echo "Installing minimal Strands packages..."
pip install strands-agents -t strands_layer/python
# Remove unnecessary files to reduce size
find strands_layer -type d -name "__pycache__" -exec rm -rf {} +
find strands_layer -type d -name "*.dist-info" -exec rm -rf {} +
find strands_layer -type d -name "*.egg-info" -exec rm -rf {} +
find strands_layer -type f -name "*.pyc" -delete

# Create layer zip
cd strands_layer
zip -r ../strands_layer.zip . -x "*.git*" "*.pyc" "__pycache__/*" "*.so" "*.dist-info/*" "*.egg-info/*"
cd ..

# Create S3 bucket for layer if it doesn't exist
S3_BUCKET="lambda-layers-${REGION}-$(aws sts get-caller-identity --query 'Account' --output text)"
if ! aws s3api head-bucket --bucket $S3_BUCKET 2>/dev/null; then
  echo "Creating S3 bucket for layers: $S3_BUCKET"
  aws s3 mb s3://$S3_BUCKET --region $REGION
fi

# Upload layer to S3
echo "Uploading layer to S3..."
aws s3 cp strands_layer.zip s3://$S3_BUCKET/strands_layer.zip

# Publish layer from S3
echo "Publishing layer from S3..."
aws lambda publish-layer-version \
    --layer-name $STRANDS_LAYER_NAME \
    --description "Strands agents for Lambda functions" \
    --content S3Bucket=$S3_BUCKET,S3Key=strands_layer.zip \
    --compatible-runtimes python3.12 \
    --region $REGION

STRANDS_LAYER_ARN=$(aws lambda list-layer-versions --layer-name $STRANDS_LAYER_NAME --region $REGION --query 'LayerVersions[0].LayerVersionArn' --output text)

# Create IAM role for Lambda
echo "Creating IAM role..."
ASSUME_ROLE_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}'

ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
  aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document "$ASSUME_ROLE_POLICY" \
    --region $REGION
  
  # Create custom policy for OpenSearch access
  OPENSEARCH_POLICY_NAME="oasis-opensearch-policy"
  OPENSEARCH_POLICY_DOCUMENT='{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "es:ESHttpGet",
          "es:ESHttpPost",
          "es:ESHttpPut",
          "es:ESHttpDelete"
        ],
        "Resource": "*"
      }
    ]
  }'
  
  # Create custom policy for Bedrock access
  BEDROCK_POLICY_NAME="oasis-bedrock-policy"
  BEDROCK_POLICY_DOCUMENT='{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        "Resource": "*"
      }
    ]
  }'
  
  # Create custom policy for SES access
  SES_POLICY_NAME="oasis-ses-policy"
  SES_POLICY_DOCUMENT='{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ],
        "Resource": "*"
      }
    ]
  }'
  
  # Create custom policy for Secrets Manager access
  SECRETS_POLICY_NAME="oasis-secrets-policy"
  SECRETS_POLICY_DOCUMENT='{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ],
        "Resource": "*"
      }
    ]
  }'
  
  # Create policies
  aws iam create-policy \
    --policy-name $OPENSEARCH_POLICY_NAME \
    --policy-document "$OPENSEARCH_POLICY_DOCUMENT" \
    --region $REGION 2>/dev/null || echo "OpenSearch policy already exists"
    
  aws iam create-policy \
    --policy-name $BEDROCK_POLICY_NAME \
    --policy-document "$BEDROCK_POLICY_DOCUMENT" \
    --region $REGION 2>/dev/null || echo "Bedrock policy already exists"
    
  aws iam create-policy \
    --policy-name $SES_POLICY_NAME \
    --policy-document "$SES_POLICY_DOCUMENT" \
    --region $REGION 2>/dev/null || echo "SES policy already exists"
    
  aws iam create-policy \
    --policy-name $SECRETS_POLICY_NAME \
    --policy-document "$SECRETS_POLICY_DOCUMENT" \
    --region $REGION 2>/dev/null || echo "Secrets Manager policy already exists"
  
  # Get account ID
  ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
  
  # Attach policies
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --region $REGION
  
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/$OPENSEARCH_POLICY_NAME \
    --region $REGION
    
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/$BEDROCK_POLICY_NAME \
    --region $REGION
    
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/$SES_POLICY_NAME \
    --region $REGION
    
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/$SECRETS_POLICY_NAME \
    --region $REGION
    
  # Wait for role to propagate
  echo "Waiting for IAM role to propagate..."
  sleep 10
  
  ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)
fi

# Create deployment package
echo "Creating Lambda deployment package..."
cd $DEPLOY_DIR
zip -r ../lambda_package.zip .
cd ..

# Check if Lambda function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name $LAMBDA_NAME --region $REGION 2>/dev/null || echo "")

# Get the secret name from environment or use default
SECRET_NAME=${OASIS_SECRET_NAME:-"oasis-configuration"}

if [ -z "$FUNCTION_EXISTS" ]; then
  # Create Lambda function
  echo "Creating Lambda function..."
  aws lambda create-function \
    --function-name $LAMBDA_NAME \
    --runtime python3.12 \
    --handler smartAssistant.lambda_handler \
    --role $ROLE_ARN \
    --zip-file fileb://lambda_package.zip \
    --timeout $TIMEOUT \
    --memory-size $MEMORY_SIZE \
    --layers $STRANDS_LAYER_ARN \
    --environment "Variables={ERROR_THRESHOLD=1,OASIS_SECRET_NAME=$SECRET_NAME,OASIS_SECRET_REGION=$REGION}" \
    --region $REGION
else
  # Update Lambda function
  echo "Updating Lambda function..."
  aws lambda update-function-code \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda_package.zip \
    --region $REGION
  
  aws lambda update-function-configuration \
    --function-name $LAMBDA_NAME \
    --timeout $TIMEOUT \
    --memory-size $MEMORY_SIZE \
    --layers $STRANDS_LAYER_ARN \
    --environment "Variables={ERROR_THRESHOLD=1,OASIS_SECRET_NAME=$SECRET_NAME,OASIS_SECRET_REGION=$REGION}" \
    --region $REGION
fi

# Create CloudWatch Events rule to trigger Lambda
echo "Creating CloudWatch Events rule..."
RULE_NAME="oasis-trigger"
aws events put-rule \
  --name $RULE_NAME \
  --schedule-expression "rate(15 minutes)" \
  --state ENABLED \
  --region $REGION

aws events put-targets \
  --rule $RULE_NAME \
  --targets "Id"="1","Arn"="arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query 'Account' --output text):function:$LAMBDA_NAME" \
  --region $REGION

aws lambda add-permission \
  --function-name $LAMBDA_NAME \
  --statement-id "AllowCloudWatchEventsInvoke" \
  --action "lambda:InvokeFunction" \
  --principal "events.amazonaws.com" \
  --source-arn "arn:aws:events:$REGION:$(aws sts get-caller-identity --query 'Account' --output text):rule/$RULE_NAME" \
  --region $REGION

# Get API Gateway ID from setup_oasis.sh if it exists
API_NAME="oasis-approval-api"
API_ID=$(aws apigateway get-rest-apis --region $REGION --query "items[?name=='$API_NAME'].id" --output text)

if [ -n "$API_ID" ]; then
  echo "Found existing API Gateway: $API_ID"
  
  # Get Lambda function ARN
  LAMBDA_ARN=$(aws lambda get-function \
    --function-name $LAMBDA_NAME \
    --region $REGION \
    --query 'Configuration.FunctionArn' --output text)
  
  # Get the root resource ID
  ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id $API_ID \
    --region $REGION \
    --query 'items[?path==`/`].id' --output text)
  
  # Check if approve resource exists
  APPROVE_RESOURCE=$(aws apigateway get-resources \
    --rest-api-id $API_ID \
    --region $REGION \
    --query 'items[?path==`/approve`].id' --output text)
  
  if [ -z "$APPROVE_RESOURCE" ]; then
    echo "Creating /approve resource..."
    APPROVE_RESOURCE=$(aws apigateway create-resource \
      --rest-api-id $API_ID \
      --parent-id $ROOT_ID \
      --path-part "approve" \
      --region $REGION \
      --query 'id' --output text)
  fi
  
  # Check if GET method exists
  GET_METHOD=$(aws apigateway get-method \
    --rest-api-id $API_ID \
    --resource-id $APPROVE_RESOURCE \
    --http-method GET \
    --region $REGION 2>/dev/null || echo "")
  
  if [ -z "$GET_METHOD" ]; then
    echo "Creating GET method..."
    aws apigateway put-method \
      --rest-api-id $API_ID \
      --resource-id $APPROVE_RESOURCE \
      --http-method GET \
      --authorization-type NONE \
      --region $REGION
  fi
  
  # Create or update Lambda integration
  echo "Setting up Lambda integration..."
  aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $APPROVE_RESOURCE \
    --http-method GET \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" \
    --region $REGION
  
  # Set up method response
  aws apigateway put-method-response \
    --rest-api-id $API_ID \
    --resource-id $APPROVE_RESOURCE \
    --http-method GET \
    --status-code 200 \
    --response-models '{"application/json": "Empty"}' \
    --region $REGION 2>/dev/null || echo "Method response already exists"
  
  # Deploy API
  echo "Deploying API Gateway..."
  aws apigateway create-deployment \
    --rest-api-id $API_ID \
    --stage-name prod \
    --region $REGION
  
  # Add Lambda permission for API Gateway
  ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
  
  # Add permission (ignore error if already exists)
  aws lambda add-permission \
    --function-name $LAMBDA_NAME \
    --statement-id "apigateway-approval-$API_ID" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*/approve" \
    --region $REGION 2>/dev/null || echo "Lambda permission already exists"
  
  # Get API URL
  API_URL="https://$API_ID.execute-api.$REGION.amazonaws.com/prod/approve"
  echo "API Gateway URL: $API_URL"
else
  echo "No existing API Gateway found. API Gateway should be created using setup_oasis.sh"
fi

# Clean up
echo "Cleaning up temporary files..."
rm -rf $DEPLOY_DIR lambda_package.zip strands_layer strands_layer.zip

# Deactivate and remove virtual environment
echo "Removing virtual environment..."
deactivate
rm -rf venv

echo "Deployment completed successfully!"
echo "Lambda function: $LAMBDA_NAME"
echo "Region: $REGION"
echo "IMPORTANT: The Lambda function is using AWS Secrets Manager for configuration"
echo "Secret name: $SECRET_NAME"