"""
Bedrock agent tool for querying application logs from OpenSearch.
"""

import json
import logging
from typing import Dict, List, Any, Optional

from .opensearch_client import OpenSearchClient
from strands import tool
logger = logging.getLogger("agent_tools.query_logs")

@tool
def query_logs(service: str, timeframe: str, level: str = None, error_type: str = None, 
               status_code: int = None, limit: int = 100) -> Dict[str, Any]:
    """
    Query application logs from OpenSearch based on service and timeframe.

    Use this tool when you need to retrieve and analyze raw log entries for troubleshooting,
    debugging, or investigating specific issues. This tool provides flexible filtering
    options to narrow down log searches to relevant entries.

    This tool queries OpenSearch for log entries matching the specified criteria and
    returns both the raw logs and a summary of the results, including statistics about
    error counts and status code distribution.

    Example response:
        {
            "logs": [
                {
                    "timestamp": "2023-04-01T12:34:56Z",
                    "service": "api-gateway",
                    "level": "ERROR",
                    "message": "Connection refused to database",
                    "error_type": "ConnectionError",
                    "status_code": 500,
                    "request_id": "req-123456"
                },
                {...}
            ],
            "summary": {
                "total_logs": 1245,
                "returned_logs": 100,
                "timeframe": {
                    "start": "2023-04-01T00:00:00Z",
                    "end": "2023-04-01T23:59:59Z"
                },
                "error_count": 37,
                "status_code_distribution": {
                    "200": 845,
                    "404": 125,
                    "500": 37
                }
            }
        }

    Notes:
        - Returns logs sorted by timestamp in descending order (newest first)
        - Provides a summary with statistics about the returned logs
        - Can filter by service, log level, error type, and status code
        - Use "all" as service name to query logs across all services
        - Limit parameter controls the maximum number of logs returned

    Args:
        service (str): The service name to query logs for. Use "all" for all services.
                      Example: "api-gateway" or "all"
        timeframe (str): Time range for the query.
                        Example: "last_15m", "last_1h", "last_24h", "today"
        level (str, optional): Filter by log level (INFO, WARN, ERROR, DEBUG).
                              Example: "ERROR"
        error_type (str, optional): Filter by error type.
                                   Example: "ConnectionError"
        status_code (int, optional): Filter by HTTP status code.
                                    Example: 500
        limit (int, optional): Maximum number of logs to return. Default is 100.
    
    Returns:
        Dict[str, Any]: Dictionary containing:
        - logs: List of log entries matching the query criteria
        - summary: Statistics about the query results including total count,
                  timeframe, and distributions of errors and status codes
    """
    try:
        client = OpenSearchClient()
        
        # Parse timeframe
        time_range = client.parse_timeframe(timeframe)
        start_time = client.format_datetime(time_range["start_time"])
        end_time = client.format_datetime(time_range["end_time"])
        
        # Build query
        query = {
            "size": limit,
            "sort": [{"timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [
                        {"range": {"timestamp": {"gte": start_time, "lte": end_time}}}
                    ]
                }
            }
        }
        
        # Add service filter if not "all"
        if service.lower() != "all":
            query["query"]["bool"]["must"].append({"term": {"service": service}})
        
        # Add optional filters
        if level:
            query["query"]["bool"]["must"].append({"term": {"level": level.upper()}})
        
        if error_type:
            query["query"]["bool"]["must"].append({"term": {"error_type": error_type}})
        
        if status_code:
            query["query"]["bool"]["must"].append({"term": {"status_code": status_code}})
        
        # Execute query
        index = client.get_logs_index()
        response = client.client.search(
            body=query,
            index=index
        )
        
        # Process results
        hits = response["hits"]["hits"]
        total_hits = response["hits"]["total"]["value"]
        
        logs = []
        for hit in hits:
            source = hit["_source"]
            logs.append(source)
        
        # Generate summary statistics
        summary = {
            "total_logs": total_hits,
            "returned_logs": len(logs),
            "timeframe": {
                "start": start_time,
                "end": end_time
            }
        }
        
        # Add error count if available
        if level == "ERROR" or any(log.get("level") == "ERROR" for log in logs):
            error_count = sum(1 for log in logs if log.get("level") == "ERROR")
            summary["error_count"] = error_count
        
        # Add status code distribution if available
        status_codes = {}
        for log in logs:
            if "status_code" in log:
                status_code = log["status_code"]
                status_codes[status_code] = status_codes.get(status_code, 0) + 1
        
        if status_codes:
            summary["status_code_distribution"] = status_codes
        
        return {
            "logs": logs,
            "summary": summary
        }
    
    except Exception as e:
        logger.error(f"Error querying logs: {e}")
        return {
            "error": str(e),
            "logs": [],
            "summary": {
                "total_logs": 0,
                "returned_logs": 0
            }
        }