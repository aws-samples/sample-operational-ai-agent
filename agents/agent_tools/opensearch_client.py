"""
OpenSearch client for Bedrock agent tools.
"""

import os
import sys
import yaml
import json
import boto3
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Import datetime utilities
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.datetime_utils import get_utc_now, to_utc, format_iso, parse_iso

logger = logging.getLogger("agent_tools.opensearch_client")

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

class OpenSearchClient:
    """Client for interacting with OpenSearch from Bedrock agent tools."""
    
    def __init__(self, config_path: str = None):
        """Initialize the OpenSearch client with configuration from AWS Secrets Manager."""
        # Get configuration from Secrets Manager
        secret = get_secret()
        
        if not secret or 'opensearch' not in secret:
            raise ValueError("OpenSearch configuration not found in AWS Secrets Manager")
            
        self.config = {"opensearch": secret['opensearch']}
        self.client = self._create_client()
        self.index_prefix = self.config["opensearch"].get("index_prefix", "app-logs")
    
    def _create_client(self) -> OpenSearch:
        """Create and return an OpenSearch client."""
        endpoint = self.config["opensearch"]["endpoint"]
        region = self.config["opensearch"].get("region", "us-east-1")
        auth_type = self.config["opensearch"].get("auth_type", "basic_auth")
        
        # Ensure endpoint is not empty
        if not endpoint:
            raise ValueError("OpenSearch endpoint is empty or not defined in configuration")
        
        # Extract hostname from endpoint URL
        host = endpoint.replace('https://', '')
        if not host:
            raise ValueError(f"Invalid OpenSearch endpoint: {endpoint}")
        
        
        if auth_type == "aws_sigv4":
            # Use AWS SigV4 authentication
            credentials = boto3.Session().get_credentials()
            awsauth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                region,
                'es',
                session_token=credentials.token
            )
            
            client = OpenSearch(
                hosts=[{'host': host, 'port': 443}],
                http_auth=awsauth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection
            )
        elif auth_type == "basic_auth":
            # Use basic authentication
            username = self.config["opensearch"].get("username", "")
            password = self.config["opensearch"].get("password", "")
            
            if not username or not password:
                raise ValueError("Username or password not provided for basic authentication")
            
            client = OpenSearch(
                hosts=[{'host': host, 'port': 443}],
                http_auth=(username, password),
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection
            )
        else:
            raise ValueError(f"Unsupported auth_type: {auth_type}")
        
        return client
    
    def parse_timeframe(self, timeframe: str) -> Dict[str, datetime]:
        """Parse a timeframe string into start and end datetime objects.
        
        Supported formats:
        - "last_15m", "last_1h", "last_24h", "last_7d"
        - "today", "yesterday"
        - ISO format date range: "2023-01-01T00:00:00/2023-01-02T00:00:00"
        """
        now = get_utc_now()
        
        if timeframe.startswith("last_"):
            # Parse "last_15m", "last_1h", etc.
            value = timeframe[5:-1]  # Extract the number
            unit = timeframe[-1]     # Extract the unit (m, h, d)
            
            try:
                value = int(value)
            except ValueError:
                raise ValueError(f"Invalid timeframe format: {timeframe}")
            
            if unit == 'm':
                start_time = now - timedelta(minutes=value)
            elif unit == 'h':
                start_time = now - timedelta(hours=value)
            elif unit == 'd':
                start_time = now - timedelta(days=value)
            else:
                raise ValueError(f"Invalid timeframe unit: {unit}")
            
            return {"start_time": start_time, "end_time": now}
        
        elif timeframe == "today":
            start_time = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=datetime.timezone.utc)
            return {"start_time": start_time, "end_time": now}
        
        elif timeframe == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=datetime.timezone.utc)
            end_time = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, tzinfo=datetime.timezone.utc)
            return {"start_time": start_time, "end_time": end_time}
        
        elif "/" in timeframe:
            # Parse ISO format date range
            try:
                start_str, end_str = timeframe.split("/")
                start_time = parse_iso(start_str)
                end_time = parse_iso(end_str)
                return {"start_time": start_time, "end_time": end_time}
            except Exception as e:
                raise ValueError(f"Invalid ISO date range format: {timeframe}. Error: {e}")
        
        else:
            raise ValueError(f"Unsupported timeframe format: {timeframe}")
    
    def format_datetime(self, dt: datetime) -> str:
        """Format datetime object to ISO string for OpenSearch queries."""
        return format_iso(dt)
    
    def get_logs_index(self) -> str:
        """Get the logs index name."""
        return f"{self.index_prefix}-logs"
    
    def get_metrics_index(self) -> str:
        """Get the metrics index name."""
        return f"{self.index_prefix}-metrics"