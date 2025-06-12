"""
OpenSearch connector module for sending logs and metrics to Amazon OpenSearch.
"""

import json
import logging
import datetime
from typing import Dict, List, Any

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk
from requests_aws4auth import AWS4Auth

from .datetime_utils import to_utc, format_iso

logger = logging.getLogger("opensearch_connector")

class OpenSearchConnector:
    """Handles connections and data ingestion to Amazon OpenSearch."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the OpenSearch connector with the given configuration."""
        self.config = config
        self.client = self._create_client()
        self.index_prefix = config.get("index_prefix", "app-logs")
        
    def _create_client(self) -> OpenSearch:
        """Create and return an OpenSearch client."""
        endpoint = self.config["endpoint"]
        region = self.config["region"]
        auth_type = self.config.get("auth_type", "aws_sigv4")
        
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
                hosts=[{'host': endpoint.replace('https://', ''), 'port': 443}],
                http_auth=awsauth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection
            )
        elif auth_type == "basic_auth":
            # Use basic authentication
            username = self.config.get("username", "")
            password = self.config.get("password", "")
            
            client = OpenSearch(
                hosts=[{'host': endpoint.replace('https://', ''), 'port': 443}],
                http_auth=(username, password),
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection
            )
        else:
            raise ValueError(f"Unsupported auth_type: {auth_type}")
        
        return client
    
    def initialize_indices(self):
        """Initialize OpenSearch indices if they don't exist."""
        try:
            # Create logs index if it doesn't exist
            logs_index = f"{self.index_prefix}-logs"
            if not self.client.indices.exists(index=logs_index):
                logger.info(f"Creating logs index: {logs_index}")
                self.client.indices.create(
                    index=logs_index,
                    body={
                        "mappings": {
                            "properties": {
                                "timestamp": {"type": "date"},
                                "service": {"type": "keyword"},
                                "level": {"type": "keyword"},
                                "message": {"type": "text"},
                                "trace_id": {"type": "keyword"},
                                "request_id": {"type": "keyword"},
                                "latency_ms": {"type": "float"},
                                "status_code": {"type": "integer"},
                                "method": {"type": "keyword"},
                                "path": {"type": "keyword"},
                                "user_id": {"type": "keyword"},
                                "error_type": {"type": "keyword"},
                                "error_message": {"type": "text"},
                                "host": {"type": "keyword"},
                                "container_id": {"type": "keyword"}
                            }
                        },
                        "settings": {
                            "number_of_shards": 3,
                            "number_of_replicas": 1
                        }
                    }
                )
            
            # Create metrics index if it doesn't exist
            metrics_index = f"{self.index_prefix}-metrics"
            if not self.client.indices.exists(index=metrics_index):
                logger.info(f"Creating metrics index: {metrics_index}")
                self.client.indices.create(
                    index=metrics_index,
                    body={
                        "mappings": {
                            "properties": {
                                "timestamp": {"type": "date"},
                                "service": {"type": "keyword"},
                                "metric_name": {"type": "keyword"},
                                "metric_value": {"type": "float"},
                                "unit": {"type": "keyword"},
                                "dimensions": {"type": "object"},
                                "host": {"type": "keyword"},
                                "container_id": {"type": "keyword"}
                            }
                        },
                        "settings": {
                            "number_of_shards": 3,
                            "number_of_replicas": 1
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Error initializing indices: {e}")
            raise
    
    def send_logs(self, logs: List[Dict[str, Any]]):
        """Send logs to OpenSearch."""
        if not logs:
            return
        
        try:
            actions = []
            index_name = f"{self.index_prefix}-logs"
            
            for log in logs:
                # Ensure timestamp is in ISO format with UTC timezone
                if isinstance(log.get("timestamp"), datetime.datetime):
                    log["timestamp"] = format_iso(log["timestamp"])
                
                actions.append({
                    "_index": index_name,
                    "_source": log
                })
            
            if actions:
                success, failed = bulk(self.client, actions)
                logger.debug(f"Indexed {success} logs, {len(failed)} failed")
        except Exception as e:
            logger.error(f"Error sending logs to OpenSearch: {e}")
    
    def send_metrics(self, metrics: List[Dict[str, Any]]):
        """Send metrics to OpenSearch."""
        if not metrics:
            return
        
        try:
            actions = []
            index_name = f"{self.index_prefix}-metrics"
            
            for metric in metrics:
                # Ensure timestamp is in ISO format with UTC timezone
                if isinstance(metric.get("timestamp"), datetime.datetime):
                    metric["timestamp"] = format_iso(metric["timestamp"])
                
                actions.append({
                    "_index": index_name,
                    "_source": metric
                })
            
            if actions:
                success, failed = bulk(self.client, actions)
                logger.debug(f"Indexed {success} metrics, {len(failed)} failed")
        except Exception as e:
            logger.error(f"Error sending metrics to OpenSearch: {e}")