"""
Bedrock agent tool for checking recent deployments and their impact.
"""

import json
import logging
import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from strands import tool
from .opensearch_client import OpenSearchClient

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.datetime_utils import parse_iso

logger = logging.getLogger("agent_tools.check_recent_deployment")

@tool
def check_recent_deployment(service: str = None, timeframe: str = "last_24h") -> Dict[str, Any]:
    """
    Check for recent deployments and analyze their impact on service health.

    Use this tool when you need to investigate if recent deployments might be causing
    service issues or performance degradation. This tool analyzes logs before and after
    deployments to identify potential correlations between deployments and error rates.

    This tool queries OpenSearch for deployment-related log entries and compares error
    rates in the periods before and after each deployment to determine if the deployment
    had a positive, negative, or neutral impact on service health.

    Example response:
        {
            "summary": {
                "timeframe": {"start": "2023-04-01T00:00:00Z", "end": "2023-04-02T00:00:00Z"},
                "total_deployments": 3,
                "services_with_deployments": 2,
                "deployments_with_negative_impact": 1,
                "deployments_with_positive_impact": 0,
                "deployments_with_no_impact": 2
            },
            "deployments": [...],
            "impact_analysis": [...]
        }

    Notes:
        - Analyzes error rates 1 hour before and after each deployment
        - Considers a deployment to have negative impact if error rate increases by >20%
        - Considers a deployment to have positive impact if error rate decreases by >20%
        - Provides detailed status code distribution for error analysis
        - Returns all deployments within the specified timeframe for the given service

    Args:
        service (str, optional): The service name to check. If None, checks all services.
                                Example: "api-gateway" or "authentication-service"
        timeframe (str, optional): Time range for the check. Default is "last_24h".
                                  Example: "last_24h", "last_7d", or "2023-04-01,2023-04-02"
    
    Returns:
        Dict[str, Any]: Dictionary containing:
        - summary: Overview of deployments and their impact
        - deployments: List of all deployments found
        - impact_analysis: Detailed analysis of each deployment's impact
    """
    try:
        client = OpenSearchClient()
        
        # Parse timeframe
        time_range = client.parse_timeframe(timeframe)
        start_time = client.format_datetime(time_range["start_time"])
        end_time = client.format_datetime(time_range["end_time"])
        
        # In a real system, we would query a deployment tracking system or CI/CD logs
        # For this simulator, we'll check for deployment-related log messages
        
        # Build query for deployment logs
        deployment_query = {
            "size": 100,
            "query": {
                "bool": {
                    "must": [
                        {"range": {"timestamp": {"gte": start_time, "lte": end_time}}},
                        {"bool": {
                            "should": [
                                {"match_phrase": {"message": "deployment"}},
                                {"match_phrase": {"message": "deployed"}},
                                {"match_phrase": {"message": "version"}},
                                {"match_phrase": {"message": "update"}},
                                {"match_phrase": {"message": "upgraded"}},
                                {"match_phrase": {"message": "rollout"}},
                                {"match_phrase": {"message": "release"}}
                            ],
                            "minimum_should_match": 1
                        }}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}]
        }
        
        # Add service filter if specified
        if service:
            deployment_query["query"]["bool"]["must"].append({"term": {"service": service}})
        
        # Execute query for deployment logs
        index = client.get_logs_index()
        deployment_response = client.client.search(
            body=deployment_query,
            index=index
        )
        
        # Process deployment logs
        deployment_hits = deployment_response["hits"]["hits"]
        deployments = []
        
        for hit in deployment_hits:
            source = hit["_source"]
            deployments.append({
                "timestamp": source.get("timestamp"),
                "service": source.get("service"),
                "message": source.get("message"),
                "level": source.get("level"),
                "host": source.get("host")
            })
        
        # Group deployments by service
        deployments_by_service = {}
        for deployment in deployments:
            service_name = deployment["service"]
            if service_name not in deployments_by_service:
                deployments_by_service[service_name] = []
            deployments_by_service[service_name].append(deployment)
        
        # For each service with deployments, analyze error rates before and after
        impact_analysis = []
        
        for service_name, service_deployments in deployments_by_service.items():
            for deployment in service_deployments:
                deployment_time = parse_iso(deployment["timestamp"])
                
                # Define before and after windows (1 hour each)
                before_start = deployment_time - timedelta(hours=1)
                before_end = deployment_time
                after_start = deployment_time
                after_end = deployment_time + timedelta(hours=1)
                
                # Query for errors before deployment
                before_query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {"range": {"timestamp": {
                                    "gte": client.format_datetime(before_start),
                                    "lt": client.format_datetime(before_end)
                                }}},
                                {"term": {"service": service_name}},
                                {"term": {"level": "ERROR"}}
                            ]
                        }
                    },
                    "aggs": {
                        "status_codes": {
                            "terms": {
                                "field": "status_code",
                                "size": 10
                            }
                        }
                    }
                }
                
                # Query for errors after deployment
                after_query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {"range": {"timestamp": {
                                    "gte": client.format_datetime(after_start),
                                    "lt": client.format_datetime(after_end)
                                }}},
                                {"term": {"service": service_name}},
                                {"term": {"level": "ERROR"}}
                            ]
                        }
                    },
                    "aggs": {
                        "status_codes": {
                            "terms": {
                                "field": "status_code",
                                "size": 10
                            }
                        }
                    }
                }
                
                # Execute queries
                before_response = client.client.search(body=before_query, index=index)
                after_response = client.client.search(body=after_query, index=index)
                
                # Extract error counts
                before_error_count = before_response["hits"]["total"]["value"]
                after_error_count = after_response["hits"]["total"]["value"]
                
                # Extract status code distribution
                before_status_codes = {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in before_response["aggregations"]["status_codes"]["buckets"]
                } if "aggregations" in before_response else {}
                
                after_status_codes = {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in after_response["aggregations"]["status_codes"]["buckets"]
                } if "aggregations" in after_response else {}
                
                # Calculate error rate change
                error_change = after_error_count - before_error_count
                error_change_percent = (
                    (after_error_count - before_error_count) / max(1, before_error_count)
                ) * 100
                
                # Determine impact
                impact = "none"
                if error_change > 0 and error_change_percent > 20:
                    impact = "negative"
                elif error_change < 0 and abs(error_change_percent) > 20:
                    impact = "positive"
                
                # Add to impact analysis
                impact_analysis.append({
                    "service": service_name,
                    "deployment_time": deployment["timestamp"],
                    "deployment_message": deployment["message"],
                    "before_window": {
                        "start": client.format_datetime(before_start),
                        "end": client.format_datetime(before_end),
                        "error_count": before_error_count,
                        "status_codes": before_status_codes
                    },
                    "after_window": {
                        "start": client.format_datetime(after_start),
                        "end": client.format_datetime(after_end),
                        "error_count": after_error_count,
                        "status_codes": after_status_codes
                    },
                    "error_change": error_change,
                    "error_change_percent": round(error_change_percent, 2),
                    "impact": impact
                })
        
        # Generate summary
        summary = {
            "timeframe": {
                "start": start_time,
                "end": end_time
            },
            "total_deployments": len(deployments),
            "services_with_deployments": len(deployments_by_service),
            "deployments_with_negative_impact": sum(1 for item in impact_analysis if item["impact"] == "negative"),
            "deployments_with_positive_impact": sum(1 for item in impact_analysis if item["impact"] == "positive"),
            "deployments_with_no_impact": sum(1 for item in impact_analysis if item["impact"] == "none")
        }
        
        return {
            "summary": summary,
            "deployments": deployments,
            "impact_analysis": impact_analysis
        }
    
    except Exception as e:
        logger.error(f"Error checking recent deployments: {e}")
        return {
            "error": str(e),
            "summary": {
                "timeframe": {
                    "start": start_time if 'start_time' in locals() else None,
                    "end": end_time if 'end_time' in locals() else None
                },
                "total_deployments": 0
            },
            "deployments": [],
            "impact_analysis": []
        }

