#!/usr/bin/env python3
"""
Script to simulate a deployment incident and trigger the multi-agent workflow.
"""

import os
import sys
import yaml
import json
import random
import datetime
import requests
import time
import boto3
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.datetime_utils import get_utc_now, to_utc, format_iso

# Get configuration from AWS Secrets Manager
def get_secret() -> Dict[str, Any]:
    """Get configuration from AWS Secrets Manager."""
    secret_name = os.environ.get('OASIS_SECRET_NAME', 'oasis-configuration')
    secret_region = os.environ.get('OASIS_SECRET_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
    
    try:
        # Get secret from AWS Secrets Manager
        print(f"Getting configuration from Secrets Manager: {secret_name}")
        secrets_client = boto3.client('secretsmanager', region_name=secret_region)
        secret_response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(secret_response['SecretString'])
    except Exception as e:
        print(f"Error getting secret from Secrets Manager: {str(e)}")
        return None

# Load configuration from file (fallback)
def load_config() -> Dict[str, Any]:
    # Use the main config file in project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, 'config.yaml')
    
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading config file: {str(e)}")
        return {}

# Main function
def main():
    # Try to get configuration from Secrets Manager first
    secret = get_secret()
    
    if secret and 'opensearch' in secret:
        print("Using OpenSearch configuration from Secrets Manager")
        opensearch_config = secret['opensearch']
    
    # OpenSearch connection details
    endpoint = opensearch_config.get("endpoint", "")
    username = opensearch_config.get("username", "")
    password = opensearch_config.get("password", "")
    auth = (username, password) if username and password else None
    index_prefix = opensearch_config.get("index_prefix", "app-logs")
    
    if not endpoint:
        print("Error: OpenSearch endpoint not found in configuration")
        sys.exit(1)
    
    # Service to simulate deployment for
    service = "product-service"
    
    # Use current time for the simulation
    current_time = get_utc_now()
    
    # Set deployment time to 20 minutes ago
    now = current_time - datetime.timedelta(minutes=20)
    
    print(f"Simulating deployment incident for {service} at {format_iso(now)}")
    print(f"Deployment of {service} version 2.5.1 at {format_iso(now)}")
    
    # Ensure endpoint has proper URL format
    if not endpoint.startswith(('http://', 'https://')):
        endpoint = f"https://{endpoint}"
    
    # Step 1: Create a deployment log entry
    deployment_log = {
        "timestamp": format_iso(now),
        "service": service,
        "level": "INFO",
        "message": f"Deployed version 2.5.1 of {service}",
        "host": f"{service}-1",
        "container_id": f"{random.randint(10000000, 99999999):x}",
        "trace_id": f"{random.randint(10000000, 99999999):x}-{random.randint(10000000, 99999999):x}",
        "request_id": f"{random.randint(10000000, 99999999):x}",
        "deployment_id": f"deploy-{random.randint(10000000, 99999999):x}",
        "version": "2.5.1",
        "cpu_utilization": random.uniform(30, 50),
        "memory_utilization": random.uniform(40, 60)
    }
    
    # Send deployment log to OpenSearch
    response = requests.post(
        f"{endpoint}/{index_prefix}-logs/_doc",
        auth=auth,
        headers={"Content-Type": "application/json"},
        data=json.dumps(deployment_log),
        timeout=10
    )
    print(f"Deployment log sent: {response.status_code}")
    
    # Send baseline metrics before deployment
    baseline_metrics = [
        {
            "timestamp": format_iso(now),
            "service": service,
            "metric_name": "cpu_utilization",
            "metric_value": random.uniform(30, 50),
            "unit": "percent",
            "host": f"{service}-1"
        },
        {
            "timestamp": format_iso(now),
            "service": service,
            "metric_name": "memory_utilization",
            "metric_value": random.uniform(40, 60),
            "unit": "percent",
            "host": f"{service}-1"
        },
        {
            "timestamp": format_iso(now),
            "service": service,
            "metric_name": "latency_ms",
            "metric_value": random.uniform(50, 150),
            "unit": "milliseconds",
            "host": f"{service}-1"
        }
    ]
    
    # Send baseline metrics to OpenSearch
    for metric in baseline_metrics:
        response = requests.post(
            f"{endpoint}/{index_prefix}-metrics/_doc",
            auth=auth,
            headers={"Content-Type": "application/json"},
            data=json.dumps(metric),
            timeout=10
        )
        print(f"Baseline metric {metric['metric_name']} sent: {response.status_code}")
    
    # Step 2: Generate error logs that occur after deployment
    error_types = ["ConfigurationError", "DependencyFailure", "ServiceUnavailable"]
    error_messages = [
        "Failed to initialize new configuration",
        "Invalid routing configuration detected",
        "Connection pool exhausted after configuration change",
        "Timeout connecting to backend service with new settings"
    ]
    
    # Generate errors over a period of time after deployment
    for i in range(15):
        # Timestamp between deployment time and now (errors occurred in the last 20 minutes)
        error_time = now + datetime.timedelta(minutes=i)  # Errors every minute after deployment
        
        error_log = {
            "timestamp": format_iso(error_time),
            "service": service,
            "level": "ERROR",
            "error_type": random.choice(error_types),
            "message": random.choice(error_messages),
            "host": f"{service}-{random.randint(1, 5)}",
            "container_id": f"{random.randint(10000000, 99999999):x}",
            "trace_id": f"{random.randint(10000000, 99999999):x}-{random.randint(10000000, 99999999):x}",
            "request_id": f"{random.randint(10000000, 99999999):x}",
            "method": random.choice(["GET", "POST", "PUT"]),
            "path": f"/api/v1/{random.choice(['users', 'products', 'orders'])}/{random.randint(1000, 9999)}",
            "status_code": 500,
            "latency_ms": random.uniform(200, 500),  # Higher latency after deployment
            "cpu_utilization": random.uniform(70, 95),  # Higher CPU after deployment
            "memory_utilization": random.uniform(60, 85)  # Higher memory after deployment
        }
        
        # Send error log to OpenSearch
        response = requests.post(
            f"{endpoint}/{index_prefix}-logs/_doc",
            auth=auth,
            headers={"Content-Type": "application/json"},
            data=json.dumps(error_log),
            timeout=10
        )
        print(f"Error log {i+1} sent: {response.status_code}")
        
        # Generate corresponding metrics for the same time period
        metrics = [
            {
                "timestamp": format_iso(error_time),
                "service": service,
                "metric_name": "cpu_utilization",
                "metric_value": random.uniform(70, 95),
                "unit": "percent",
                "host": f"{service}-{random.randint(1, 5)}"
            },
            {
                "timestamp": format_iso(error_time),
                "service": service,
                "metric_name": "memory_utilization",
                "metric_value": random.uniform(60, 85),
                "unit": "percent",
                "host": f"{service}-{random.randint(1, 5)}"
            },
            {
                "timestamp": format_iso(error_time),
                "service": service,
                "metric_name": "latency_ms",
                "metric_value": random.uniform(200, 500),
                "unit": "milliseconds",
                "host": f"{service}-{random.randint(1, 5)}"
            }
        ]
        
        # Send metrics to OpenSearch
        for metric in metrics:
            response = requests.post(
                f"{endpoint}/{index_prefix}-metrics/_doc",
                auth=auth,
                headers={"Content-Type": "application/json"},
                data=json.dumps(metric),
                timeout=10
            )
            print(f"Metric {metric['metric_name']} sent: {response.status_code}")
    
    # Generate some recovery metrics after the errors
    print("\nGenerating recovery metrics...")
    recovery_time = current_time - datetime.timedelta(minutes=5)  # Recovery started 5 minutes ago
    print(f"Recovery metrics generated for period after {format_iso(recovery_time)}")
    
    recovery_metrics = []
    for i in range(5):
        recovery_time_point = recovery_time + datetime.timedelta(minutes=i*2)
        
        # CPU gradually decreasing
        recovery_metrics.append({
            "timestamp": format_iso(recovery_time_point),
            "service": service,
            "metric_name": "cpu_utilization",
            "metric_value": random.uniform(50, 70) - (i * 5),  # Decreasing CPU
            "unit": "percent",
            "host": f"{service}-{random.randint(1, 5)}"
        })
        
        # Memory gradually decreasing
        recovery_metrics.append({
            "timestamp": format_iso(recovery_time_point),
            "service": service,
            "metric_name": "memory_utilization",
            "metric_value": random.uniform(50, 70) - (i * 3),  # Decreasing memory
            "unit": "percent",
            "host": f"{service}-{random.randint(1, 5)}"
        })
        
        # Latency gradually improving
        recovery_metrics.append({
            "timestamp": format_iso(recovery_time_point),
            "service": service,
            "metric_name": "latency_ms",
            "metric_value": random.uniform(150, 250) - (i * 20),  # Improving latency
            "unit": "milliseconds",
            "host": f"{service}-{random.randint(1, 5)}"
        })
    
    # Send recovery metrics to OpenSearch
    for metric in recovery_metrics:
        response = requests.post(
            f"{endpoint}/{index_prefix}-metrics/_doc",
            auth=auth,
            headers={"Content-Type": "application/json"},
            data=json.dumps(metric),
            timeout=10
        )
        print(f"Recovery metric {metric['metric_name']} sent: {response.status_code}")
    
    print("\nSimulation complete!")
    print(f"Generated {15} error logs and {len(baseline_metrics) + len(metrics) * 15 + len(recovery_metrics)} metrics")
    print(f"Incident timeline: Deployment at {format_iso(now)}, errors for ~15 minutes, recovery starting at {format_iso(recovery_time)}")
    print("\nYou can now run the Smart Assistant to detect and analyze this incident.")

if __name__ == "__main__":
    main()