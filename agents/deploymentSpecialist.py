#!/usr/bin/env python3
"""
DeploymentSpecialist agent for handling deployment-related mitigation actions.
This agent is called by the SmartAssistant agent to take actions to resolve deployment issues.
"""

import json
import logging
import os
import boto3
from typing import Dict, Any, Optional, List
from strands import Agent
from strands.models import BedrockModel
from strands import tool
from agent_tools.deployment_mitigation import (
    rollback_deployment,
    restart_service,
    update_configuration,
    scale_service
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("deployment_specialist")

# Get configuration from AWS Secrets Manager
def get_secret():
    """Get configuration from AWS Secrets Manager."""
    secret_name = 'oasis-configuration'
    secret_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    try:
        # Get secret from AWS Secrets Manager
        logger.info(f"Getting configuration from Secrets Manager: {secret_name}")
        secrets_client = boto3.client('secretsmanager', region_name=secret_region)
        secret_response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(secret_response['SecretString'])
    except Exception as e:
        logger.error(f"Error getting secret from Secrets Manager: {str(e)}")
        raise ValueError(f"Failed to retrieve configuration from AWS Secrets Manager: {str(e)}")

# Initialize the agent with the deployment mitigation tools
secret = get_secret()
if secret and 'strands' in secret:
    model_id = secret['strands'].get('model_id', "amazon.nova-micro-v1:0")
    region = secret['strands'].get('region', 'us-east-1')
else:
    model_id = "amazon.nova-micro-v1:0"
    region = os.environ.get('AWS_REGION', 'us-east-1')

bedrock_model = BedrockModel(
    model_id=model_id,
    region_name=region
)

agent = Agent(
    model=bedrock_model,
    tools=[rollback_deployment, restart_service, update_configuration, scale_service]
)

@tool
def handle_deployment_issue(issue_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a deployment-related issue by taking appropriate mitigation actions.
    
    Args:
        issue_details: Dictionary containing details about the issue
                      Must include 'service', 'issue_type', and action-specific parameters
    
    Returns:
        Dictionary containing the result of the mitigation action
    """
    logger.info(f"DeploymentSpecialist received issue: {json.dumps(issue_details)}")
    
    service = issue_details.get('service')
    issue_type = issue_details.get('issue_type')
    
    if not service or not issue_type:
        return {
            "status": "error",
            "message": "Missing required parameters: service and issue_type"
        }
    
    # Construct a prompt for the agent based on the issue details
    prompt = f"""
    I need to mitigate a deployment issue for service '{service}'. The issue type is '{issue_type}'.
    
    Issue details:
    {json.dumps(issue_details, indent=2)}
    
    Based on this information, determine the best mitigation action to take. Consider:
    1. If a rollback is needed, what version to roll back to
    2. If a restart is sufficient, whether to restart specific instances or the entire service
    3. If configuration changes are needed, what specific parameters to adjust
    4. If scaling is required, how many replicas to scale to
    
    Take the appropriate action using the available tools and explain your reasoning.
    """
    
    try:
        # Let the agent decide the best action based on the issue details
        response = agent(prompt)
        
        # Return the agent's response
        return {
            "status": "success",
            "service": service,
            "issue_type": issue_type,
            "action_taken": response.message,
            "result": response.tool_results if hasattr(response, 'tool_results') else {}
        }
    except Exception as e:
        logger.error(f"Error handling deployment issue: {str(e)}")
        return {
            "status": "error",
            "service": service,
            "issue_type": issue_type,
            "message": f"Failed to handle deployment issue: {str(e)}"
        }

if __name__ == "__main__":
    # For local testing
    test_issue = {
        "service": "api-gateway",
        "issue_type": "high_error_rate",
        "error_count": 150,
        "recent_deployment": {
            "found": True,
            "version": "v2.1.0",
            "previous_version": "v2.0.5",
            "timestamp": "2023-04-01T10:15:00Z"
        },
        "metrics": {
            "cpu_utilization": 85,
            "memory_utilization": 92,
            "error_rate": 15.5
        }
    }
    
    result = handle_deployment_issue(test_issue)
    print(json.dumps(result, indent=2))