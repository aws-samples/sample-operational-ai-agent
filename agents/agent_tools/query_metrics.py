

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from strands import tool
from .opensearch_client import OpenSearchClient

logger = logging.getLogger("agent_tools.query_metrics")

@tool
def query_metrics(service: str, metric_name: str, timeframe: str, 
                  window: str = "1m", aggregation: str = "avg") -> Dict[str, Any]:
    """
    Query application metrics from OpenSearch for monitoring and analysis.

    Use this tool when you need to retrieve time-series metrics data from OpenSearch for
    specific services or across your entire application. This tool supports various metrics
    like CPU utilization, memory usage, error rates, and any other metrics stored in your
    OpenSearch instance.

    This tool connects to OpenSearch, executes a query with the specified parameters, and
    returns both the raw time-series data and summary statistics to help you quickly
    understand the metric behavior over the requested timeframe.

    Example response:
        {
            "time_series": [
                {
                    "timestamp": "2023-11-15T14:30:00Z",
                    "value": 42.5,
                    "services": {"api-service": 45.2, "auth-service": 38.7}
                },
                ...
            ],
            "summary": {
                "timeframe": {"start": "2023-11-15T14:00:00Z", "end": "2023-11-15T15:00:00Z"},
                "window": "1m",
                "aggregation": "avg",
                "metric_name": "cpu_utilization",
                "statistics": {
                    "min": 32.1,
                    "max": 78.6,
                    "avg": 45.3,
                    "latest": 42.5,
                    "data_points": 60
                }
            }
        }

    Notes:
        - The tool automatically handles time parsing for common formats like "last_15m", "last_1h"
        - You can query across all services or filter to a specific service
        - Multiple aggregation methods are supported (avg, max, min, sum, count)
        - The response includes both raw time-series data and calculated summary statistics
        - If no data is found, the statistics will contain null values with 0 data_points

    Args:
        service (str): The service name to query metrics for. Use "all" for all services.
                    Example: "api-gateway" or "authentication-service"
        metric_name (str): The name of the metric to query.
                        Example: "cpu_utilization", "error_rate", "memory_usage"
        timeframe (str): Time range for the query.
                        Example: "last_15m", "last_1h", "last_24h", "today"
        window (str, optional): Time window for aggregation. Default is "1m".
                            Example: "1m", "5m", "1h"
        aggregation (str, optional): Aggregation function to use. Default is "avg".
                                    Example: "avg", "max", "min", "sum", "count"

    Returns:
        Dict[str, Any]: Dictionary containing:
        - time_series: List of data points with timestamp, value, and per-service breakdown
        - summary: Statistics and metadata about the query including min, max, avg values
    """
    try:
        client = OpenSearchClient()
        
        # Parse timeframe
        time_range = client.parse_timeframe(timeframe)
        start_time = client.format_datetime(time_range["start_time"])
        end_time = client.format_datetime(time_range["end_time"])
        
        # Validate aggregation
        valid_aggregations = ["avg", "max", "min", "sum", "count"]
        if aggregation not in valid_aggregations:
            raise ValueError(f"Invalid aggregation: {aggregation}. Must be one of {valid_aggregations}")
        
        # Build query
        query = {
            "size": 0,  # We only want aggregations, not individual documents
            "query": {
                "bool": {
                    "must": [
                        {"range": {"timestamp": {"gte": start_time, "lte": end_time}}},
                        {"term": {"metric_name": metric_name}}
                    ]
                }
            },
            "aggs": {
                "metrics_over_time": {
                    "date_histogram": {
                        "field": "timestamp",
                        "fixed_interval": window,
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": start_time,
                            "max": end_time
                        }
                    },
                    "aggs": {
                        "metric_value": {
                            aggregation: {
                                "field": "metric_value"
                            }
                        },
                        "by_service": {
                            "terms": {
                                "field": "service",
                                "size": 10
                            },
                            "aggs": {
                                "metric_value": {
                                    aggregation: {
                                        "field": "metric_value"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        # Add service filter if not "all"
        if service.lower() != "all":
            query["query"]["bool"]["must"].append({"term": {"service": service}})
        
        # Execute query
        index = client.get_metrics_index()
        response = client.client.search(
            body=query,
            index=index
        )
        
        # Process results
        buckets = response["aggregations"]["metrics_over_time"]["buckets"]
        
        # Extract time series data
        time_series = []
        for bucket in buckets:
            timestamp = bucket["key_as_string"]
            value = bucket["metric_value"]["value"] if "value" in bucket["metric_value"] else None
            
            # Extract per-service values if available
            services = {}
            if "by_service" in bucket and "buckets" in bucket["by_service"]:
                for service_bucket in bucket["by_service"]["buckets"]:
                    service_name = service_bucket["key"]
                    service_value = service_bucket["metric_value"]["value"] if "value" in service_bucket["metric_value"] else None
                    services[service_name] = service_value
            
            time_series.append({
                "timestamp": timestamp,
                "value": value,
                "services": services
            })
        
        # Calculate summary statistics
        values = [point["value"] for point in time_series if point["value"] is not None]
        
        summary = {
            "timeframe": {
                "start": start_time,
                "end": end_time
            },
            "window": window,
            "aggregation": aggregation,
            "metric_name": metric_name
        }
        
        if values:
            summary["statistics"] = {
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1] if values else None,
                "data_points": len(values)
            }
        else:
            summary["statistics"] = {
                "min": None,
                "max": None,
                "avg": None,
                "latest": None,
                "data_points": 0
            }
        
        return {
            "time_series": time_series,
            "summary": summary
        }
    
    except Exception as e:
        logger.error(f"Error querying metrics: {e}")
        return {
            "error": str(e),
            "time_series": [],
            "summary": {
                "timeframe": {
                    "start": start_time if 'start_time' in locals() else None,
                    "end": end_time if 'end_time' in locals() else None
                },
                "statistics": {
                    "data_points": 0
                }
            }
        }