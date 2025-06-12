#!/usr/bin/env python3
"""
Tool for sending post-incident summary emails using Amazon SES.
"""

import os
import json
import boto3
import logging
from typing import Dict, Any
from strands import tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("send_incident_email")

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

@tool
def send_incident_email(incident_summary: str, service_name: str) -> Dict[str, Any]:
    """
    Send a post-incident summary email using Amazon SES.

    Use this tool when you need to notify stakeholders about an incident that has been
    detected and analyzed. This tool formats the incident information into a professional
    email and sends it to the configured recipients using Amazon SES.

    Args:
        incident_summary: Detail Incident Analysis Report
        service_name: The name of the affected service.
                     Example: "api-gateway" or "authentication-service"
 
    Returns:
        A dictionary containing:
        - status: Result of the operation ("success", "skipped", or "error")
        - message: Detailed information about the result
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
    
    # Clean up whitespace in incident summary
    cleaned_summary = incident_summary.strip()
    
    logger.info(f"Sending incident summary email for service {service_name}")
    
    # Create the email HTML body
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ background-color: #232f3e; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f8f8f8; }}
            .summary {{ margin: 20px 0; padding: 20px; background-color: #fff; border: 1px solid #ddd; }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
            pre {{ white-space: pre-wrap; background-color: #f1f1f1; padding: 10px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Incident Summary Report</h1>
            </div>
            <div class="content">
                <p>Please find below the summary of the recent incident affecting the {service_name} service:</p>
                
                <div class="summary">
                    <h2>Incident Details</h2>
                    <pre>{cleaned_summary}</pre>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from the OASIS system.</p>
                    <p>Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create the email text body (fallback for email clients that don't support HTML)
    text_body = f"""
    Incident Summary Report
    
    Please find below the summary of the recent incident affecting the {service_name} service:
    
    {cleaned_summary}
    
    This is an automated message from the OASIS system.
    Please do not reply to this email.
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
                    'Data': f"Incident Summary: {service_name} Service"
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
            "service": service_name
        }
    
    except Exception as e:
        logger.error(f"Error sending incident email: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send incident email: {str(e)}",
            "recipient": recipient_email,
            "service": service_name
        }

if __name__ == "__main__":
    # For local testing
    test_summary = """
    Incident Summary:
    - Service: api-gateway
    - Start Time: 2023-05-01T14:30:00
    - End Time: 2023-05-01T15:45:00
    - Root Cause: Configuration error after deployment
    - Impact: 500 errors affecting 15% of users
    """
    
    result = send_incident_email(test_summary, "api-gateway")
    print(json.dumps(result, indent=2))