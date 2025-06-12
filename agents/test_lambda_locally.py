#!/usr/bin/env python3
import json
import os
import sys
import boto3
import smartAssistant as smartAssistant

def load_from_secrets_manager():
    """Load configuration from AWS Secrets Manager."""
    secret_name = os.environ.get('OASIS_SECRET_NAME', 'oasis-configuration')
    region = os.environ.get('OASIS_SECRET_REGION', 'us-east-1')
    
    try:
        print(f"Loading configuration from Secrets Manager: {secret_name} in {region}")
        secrets_client = boto3.client('secretsmanager', region_name=region)
        secret_response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(secret_response['SecretString'])
        
        # Set environment variables from secret
        if 'opensearch' in secret:
            os_config = secret['opensearch']
            os.environ['OPENSEARCH_ENDPOINT'] = os_config.get('endpoint', '')
            os.environ['OPENSEARCH_USERNAME'] = os_config.get('username', '')
            os.environ['OPENSEARCH_PASSWORD'] = os_config.get('password', '')
            os.environ['AUTH_TYPE'] = 'basic_auth'
            os.environ['INDEX_PREFIX'] = os_config.get('index_prefix', 'app-logs')
            os.environ['REGION'] = os_config.get('region', 'us-east-1')
        
        if 'strands' in secret:
            strands_config = secret['strands']
            os.environ['REGION'] = strands_config.get('region', os.environ.get('REGION', 'us-east-1'))
        
        print("Successfully loaded configuration from Secrets Manager")
        return True
    except Exception as e:
        print(f"Error loading from Secrets Manager: {str(e)}")
        return False

os.environ['OASIS_SECRET_NAME'] = os.environ.get('OASIS_SECRET_NAME', 'oasis-configuration')
os.environ['OASIS_SECRET_REGION'] = os.environ.get('OASIS_SECRET_REGION', os.environ.get('REGION', 'us-east-1'))

# Create a simple mock context
class MockContext:
    def __init__(self):
        self.function_name = 'auto_monitor_lambda'
        self.function_version = '$LATEST'
        self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:auto_monitor_lambda'
        self.memory_limit_in_mb = 256

def test_normal_execution():
    """Test normal execution flow without API Gateway parameters."""
    print("\n=== Testing normal execution ===")
    # Create a mock event with check_interval parameter
    event = {
        'check_interval': 30  # Set check_interval to 30 minutes
    }
    
    # Call the lambda handler
    response = smartAssistant.lambda_handler(event, MockContext())
     
    # Extract finding_id if available
    finding_id = None
    try:
        body = json.loads(response.get('body', '{}'))
        finding_id = body.get('finding_id')
        if finding_id:
            print(f"Found finding_id: {finding_id}")
    except:
        pass
    
    return finding_id

def test_api_gateway_approve():
    """Test API Gateway approval flow."""
    print("\n=== Testing API Gateway approval flow ===")
    # Create a mock event with queryStringParameters for approval
    event = {
        'queryStringParameters': {
            'finding_id': '74fc470a-0cb6-4cce-acd7-4612adf169c3',
            'action': 'approve'
        }
    }
    
    try:
        # Call the lambda handler
        response = smartAssistant.lambda_handler(event, MockContext())
        

        print("✓ API Gateway approval process is completed")
    except Exception as e:
        print(f"✗ API Gateway approval test failed: {str(e)}")

def test_api_gateway_reject():
    """Test API Gateway rejection flow."""
    print("\n=== Testing API Gateway rejection flow ===")
    # Create a mock event with queryStringParameters for rejection
    event = {
        'queryStringParameters': {
            'finding_id': 'test-finding-123',
            'action': 'reject'
        }
    }
    
    try:
        # Call the lambda handler
        response = smartAssistant.lambda_handler(event, MockContext())
        
        # Print the response
        
        # Validate response
        assert response.get('statusCode') == 200, "Response should have 200 status code"
        assert 'body' in response, "Response should have a body field"
        assert 'Action' in response['body'], "Response body should contain 'Action'"
        print("✓ API Gateway rejection test passed")
    except Exception as e:
        print(f"✗ API Gateway rejection test failed: {str(e)}")

def test_api_gateway_approve_with_finding():
    """Test API Gateway approval flow with a specific finding_id."""
    print("\n=== Testing API Gateway approval flow with finding_id ===")
    # Create a mock event with queryStringParameters for approval
    event = {
        'queryStringParameters': {
            'finding_id': "13887db0-b779-4d8a-8999-b6a9d4dfc255",
            'action': 'approve'
        }
    }
    
    try:
        # Call the lambda handler
        response = smartAssistant.lambda_handler(event, MockContext())
        
        # Print the response
        print(json.dumps(response, indent=2))
        

    except Exception as e:
        print(f"✗ API Gateway approval test failed: {str(e)}")

if __name__ == "__main__":
    # Run tests sequentially
    test_normal_execution()
    #test_api_gateway_approve_with_finding()
    