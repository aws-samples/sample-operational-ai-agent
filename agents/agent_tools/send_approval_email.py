#!/usr/bin/env python3
"""
Tool for sending approval emails with links to approve or reject proposed actions.
"""

import boto3
import json
import logging
import os
from typing import Dict, Any, Optional

from strands import tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("send_approval_email")

def get_secret():
    """Get configuration from AWS Secrets Manager."""
    secret_name = 'oasis-configuration'
    secret_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    try:
        # Get secret from AWS Secrets Manager
        secrets_client = boto3.client('secretsmanager', region_name=secret_region)
        secret_response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(secret_response['SecretString'])
    except Exception as e:
        logger.error(f"Error getting secret from Secrets Manager: {str(e)}")
        raise ValueError(f"Failed to retrieve configuration from AWS Secrets Manager: {str(e)}")

@tool
def send_approval_email(
    finding_id: str,
    subject: str,
    proposed_actions: str,
    incident_summary: str
) -> Dict[str, Any]:
    """
    Send an email with approve/reject links for proposed actions.
    
    Args:
        finding_id: Unique identifier for the finding
        subject: Email subject line
        proposed_actions: Description of the actions that need approval
        incident_summary: Summary of the incident
    
    Returns:
        Dictionary containing the result of the email sending operation
    """
    # Get configuration from Secrets Manager
    secret = get_secret()
    
    if not secret:
        return {
            "status": "error",
            "message": "Failed to get configuration from Secrets Manager"
        }
    
    # Get email configuration
    email_config = secret.get('email', {})
    sender_email = email_config.get('sender')
    recipient_email = email_config.get('recipient')
    
    if not sender_email or not recipient_email:
        return {
            "status": "error",
            "message": "Email configuration not found in secrets"
        }
    
    # Get API Gateway URL
    api_config = secret.get('api_gateway', {})
    approval_url_base = api_config.get('approval_url')
    
    if not approval_url_base:
        return {
            "status": "error",
            "message": "Approval URL not configured"
        }
    
    logger.info(f"Sending approval email for finding {finding_id}")
    
    # Create the approve/reject URLs
    approve_url = f"{approval_url_base}?finding_id={finding_id}&action=approve"
    reject_url = f"{approval_url_base}?finding_id={finding_id}&action=reject"
    
    # Create the email HTML body
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ background-color: #232f3e; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f8f8f8; }}
            .actions {{ margin: 20px 0; padding: 20px; background-color: #fff; border: 1px solid #ddd; }}
            .summary {{ margin: 20px 0; padding: 20px; background-color: #fff; border: 1px solid #ddd; }}
            .button {{ display: inline-block; padding: 10px 20px; margin: 10px; text-decoration: none; border-radius: 4px; font-weight: bold; }}
            .approve {{ background-color: #1E8E3E; color: white; }}
            .reject {{ background-color: #D93025; color: white; }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
            pre {{ white-space: pre-wrap; background-color: #f1f1f1; padding: 10px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Action Approval Required</h1>
            </div>
            <div class="content">
                <p>An incident has been detected and requires your approval for remediation actions.</p>
                
                <div class="summary">
                    <h2>Incident Summary</h2>
                    <pre>{incident_summary}</pre>
                </div>
                
                <div class="actions">
                    <h2>Proposed Actions</h2>
                    <pre>{proposed_actions}</pre>
                </div>
                
                <p>Please review the proposed actions and approve or reject:</p>
                
                <div style="text-align: center;">
                    <a href="{approve_url}" class="button approve">Approve Actions</a>
                    <a href="{reject_url}" class="button reject">Reject Actions</a>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from the OASIS system. Finding ID: {finding_id}</p>
                    <p>If you're unable to click the buttons above, you can copy and paste these URLs into your browser:</p>
                    <p>Approve: {approve_url}</p>
                    <p>Reject: {reject_url}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create the email text body (fallback for email clients that don't support HTML)
    text_body = f"""
    Action Approval Required
    
    An incident has been detected and requires your approval for remediation actions.
    
    Incident Summary:
    {incident_summary}
    
    Proposed Actions:
    {proposed_actions}
    
    Please review the proposed actions and approve or reject by visiting one of these links:
    
    Approve: {approve_url}
    Reject: {reject_url}
    
    This is an automated message from the OASIS system. Finding ID: {finding_id}
    """
    
    try:
        # Get region from secret
        region = secret.get('strands', {}).get('region', 'us-east-1')
        
        # Create SES client
        ses_client = boto3.client('ses', region_name=region)
        
        # Send the email
        response = ses_client.send_email(
            Source=sender_email,
            Destination={
                'ToAddresses': [recipient_email]
            },
            Message={
                'Subject': {
                    'Data': subject
                },
                'Body': {
                    'Text': {
                        'Data': text_body
                    },
                    'Html': {
                        'Data': html_body
                    }
                }
            }
        )
        
        logger.info(f"Email sent successfully: {response['MessageId']}")
        
        return {
            "status": "success",
            "message_id": response['MessageId'],
            "recipient": recipient_email,
            "finding_id": finding_id
        }
    
    except Exception as e:
        logger.error(f"Error sending approval email: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send approval email: {str(e)}",
            "recipient": recipient_email,
            "finding_id": finding_id
        }

if __name__ == "__main__":
    # For local testing
    result = send_approval_email(
        finding_id="test-finding-123",
        subject="Action Required: System Incident Detected",
        proposed_actions="1. Restart the api-gateway service\n2. Scale up the cache service to 3 replicas",
        incident_summary="High error rate detected in api-gateway service. Error rate: 15.5/min (baseline: 2.3/min)"
    )
