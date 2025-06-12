"""
Bedrock agent tool for correlating errors across services.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import networkx as nx
from strands import Agent, tool
from .opensearch_client import OpenSearchClient

logger = logging.getLogger("agent_tools.correlate_errors")

@tool
def correlate_errors_across_services(timeframe: str, error_threshold: int = 5, 
                                     include_warnings: bool = False) -> Dict[str, Any]:
    """
    Correlate errors across services to identify potential cascading failures.

    Use this tool when you need to analyze error patterns across multiple services to
    determine if failures in one service are causing problems in dependent services.
    This tool helps identify root causes and cascading failures in a microservice
    architecture.

    This tool analyzes error logs across all services within the specified timeframe,
    builds a dependency graph, and identifies services that may be the root cause of
    failures as well as services experiencing cascading failures.

    Example response:
        {
            "correlation_summary": {
                "timeframe": {"start": "2023-04-01T00:00:00Z", "end": "2023-04-01T01:00:00Z"},
                "total_services_analyzed": 12,
                "problematic_services_count": 3,
                "potential_root_causes_count": 1,
                "cascading_failures_count": 2
            },
            "problematic_services": ["database-service", "api-gateway", "auth-service"],
            "potential_root_causes": [...],
            "cascading_failures": [...]
        }

    Notes:
        - Uses service dependency information to build a directed graph
        - Identifies services with error counts above the specified threshold
        - Distinguishes between root causes and cascading failures
        - Provides error timelines to help visualize the propagation of failures
        - Can optionally include warnings in addition to errors

    Args:
        timeframe (str): Time range for the correlation.
                        Example: "last_15m", "last_1h", "last_24h"
        error_threshold (int, optional): Minimum number of errors to consider a service problematic.
                                        Default is 5.
        include_warnings (bool, optional): Whether to include warnings in the correlation.
                                          Default is False.
    
    Returns:
        Dict[str, Any]: Dictionary containing:
        - correlation_summary: Overview of the analysis results
        - service_errors: Error counts and types for each service
        - problematic_services: List of services with errors above threshold
        - potential_root_causes: Services likely causing the failures
        - cascading_failures: Services failing due to dependencies
        - service_dependencies: Map of service dependency relationships
    """
    try:
        client = OpenSearchClient()
        
        # Parse timeframe
        time_range = client.parse_timeframe(timeframe)
        start_time = client.format_datetime(time_range["start_time"])
        end_time = client.format_datetime(time_range["end_time"])
        
        # Get service dependencies from config
        services_config = client.config.get("services", [])
        service_dependencies = {
            service["name"]: service.get("dependencies", [])
            for service in services_config
        }
        
        # Build dependency graph
        dependency_graph = nx.DiGraph()
        for service, dependencies in service_dependencies.items():
            dependency_graph.add_node(service)
            for dep in dependencies:
                dependency_graph.add_edge(service, dep)
        
        # Query for errors in each service
        levels = ["ERROR"]
        if include_warnings:
            levels.append("WARN")
        
        # Build query to get error counts by service
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"range": {"timestamp": {"gte": start_time, "lte": end_time}}},
                        {"terms": {"level": levels}}
                    ]
                }
            },
            "aggs": {
                "by_service": {
                    "terms": {
                        "field": "service",
                        "size": 100
                    },
                    "aggs": {
                        "by_level": {
                            "terms": {
                                "field": "level",
                                "size": 10
                            }
                        },
                        "by_error_type": {
                            "terms": {
                                "field": "error_type",
                                "size": 10,
                                "missing": "Unknown"
                            }
                        },
                        "error_timeline": {
                            "date_histogram": {
                                "field": "timestamp",
                                "fixed_interval": "1m"
                            }
                        }
                    }
                }
            }
        }
        
        # Execute query
        index = client.get_logs_index()
        response = client.client.search(
            body=query,
            index=index
        )
        
        # Process results
        service_buckets = response["aggregations"]["by_service"]["buckets"]
        
        # Extract error counts by service
        service_errors = {}
        for bucket in service_buckets:
            service_name = bucket["key"]
            error_count = bucket["doc_count"]
            
            # Extract error types
            error_types = {}
            for error_type_bucket in bucket["by_error_type"]["buckets"]:
                error_type = error_type_bucket["key"]
                error_types[error_type] = error_type_bucket["doc_count"]
            
            # Extract timeline
            timeline = []
            for time_bucket in bucket["error_timeline"]["buckets"]:
                if time_bucket["doc_count"] > 0:
                    timeline.append({
                        "timestamp": time_bucket["key_as_string"],
                        "count": time_bucket["doc_count"]
                    })
            
            service_errors[service_name] = {
                "error_count": error_count,
                "error_types": error_types,
                "timeline": timeline
            }
        
        # Identify problematic services (those with errors above threshold)
        problematic_services = {
            service: data
            for service, data in service_errors.items()
            if data["error_count"] >= error_threshold
        }
        
        # Analyze potential cascading failures
        cascading_failures = []
        root_causes = []
        
        # For each problematic service, check if its dependencies also have errors
        for service in problematic_services:
            # Get all dependencies (direct and indirect)
            try:
                all_deps = list(nx.descendants(dependency_graph, service))
            except nx.NetworkXError:
                # Service might not be in the graph
                all_deps = []
            
            # Check if any dependencies have errors
            failing_deps = [dep for dep in all_deps if dep in problematic_services]
            
            if failing_deps:
                # This service has failing dependencies, likely a cascading failure
                cascading_failures.append({
                    "service": service,
                    "error_count": problematic_services[service]["error_count"],
                    "failing_dependencies": [
                        {
                            "service": dep,
                            "error_count": problematic_services[dep]["error_count"],
                            "error_types": problematic_services[dep]["error_types"]
                        }
                        for dep in failing_deps
                    ]
                })
            else:
                # This service has no failing dependencies, might be a root cause
                root_causes.append({
                    "service": service,
                    "error_count": problematic_services[service]["error_count"],
                    "error_types": problematic_services[service]["error_types"],
                    "dependent_services": [
                        s for s in service_dependencies if service in service_dependencies[s]
                    ]
                })
        
        # Generate correlation summary
        correlation_summary = {
            "timeframe": {
                "start": start_time,
                "end": end_time
            },
            "total_services_analyzed": len(service_errors),
            "problematic_services_count": len(problematic_services),
            "potential_root_causes_count": len(root_causes),
            "cascading_failures_count": len(cascading_failures)
        }
        
        return {
            "correlation_summary": correlation_summary,
            "service_errors": service_errors,
            "problematic_services": list(problematic_services.keys()),
            "potential_root_causes": root_causes,
            "cascading_failures": cascading_failures,
            "service_dependencies": service_dependencies
        }
    
    except Exception as e:
        logger.error(f"Error correlating errors: {e}")
        return {
            "error": str(e),
            "correlation_summary": {
                "timeframe": {
                    "start": start_time if 'start_time' in locals() else None,
                    "end": end_time if 'end_time' in locals() else None
                },
                "total_services_analyzed": 0,
                "problematic_services_count": 0
            }
        }

# OpenAPI schema for the Bedrock agent tool
SCHEMA = {
    "openapi": "3.0.0",
    "info": {
        "title": "Correlate Errors API",
        "version": "1.0.0",
        "description": "API for correlating errors across services"
    },
    "paths": {
        "/correlate_errors_across_services": {
            "post": {
                "summary": "Correlate errors across services",
                "description": "Correlate errors across services to identify potential cascading failures",
                "operationId": "CorrelateErrors",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["timeframe"],
                                "properties": {
                                    "timeframe": {
                                        "type": "string",
                                        "description": "Time range for the correlation (e.g., 'last_15m', 'last_1h', 'last_24h')."
                                    },
                                    "error_threshold": {
                                        "type": "integer",
                                        "default": 5,
                                        "description": "Minimum number of errors to consider a service problematic."
                                    },
                                    "include_warnings": {
                                        "type": "boolean",
                                        "default": False,
                                        "description": "Whether to include warnings in the correlation."
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "correlation_summary": {
                                            "type": "object",
                                            "properties": {
                                                "timeframe": {
                                                    "type": "object",
                                                    "properties": {
                                                        "start": {
                                                            "type": "string",
                                                            "description": "Start time of the correlation"
                                                        },
                                                        "end": {
                                                            "type": "string",
                                                            "description": "End time of the correlation"
                                                        }
                                                    }
                                                },
                                                "total_services_analyzed": {
                                                    "type": "integer",
                                                    "description": "Total number of services analyzed"
                                                },
                                                "problematic_services_count": {
                                                    "type": "integer",
                                                    "description": "Number of services with errors above threshold"
                                                },
                                                "potential_root_causes_count": {
                                                    "type": "integer",
                                                    "description": "Number of potential root cause services"
                                                },
                                                "cascading_failures_count": {
                                                    "type": "integer",
                                                    "description": "Number of cascading failure patterns"
                                                }
                                            }
                                        },
                                        "problematic_services": {
                                            "type": "array",
                                            "items": {
                                                "type": "string"
                                            },
                                            "description": "List of services with errors above threshold"
                                        },
                                        "potential_root_causes": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "service": {
                                                        "type": "string",
                                                        "description": "Service name"
                                                    },
                                                    "error_count": {
                                                        "type": "integer",
                                                        "description": "Number of errors"
                                                    },
                                                    "error_types": {
                                                        "type": "object",
                                                        "description": "Error types and counts"
                                                    },
                                                    "dependent_services": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "string"
                                                        },
                                                        "description": "Services that depend on this service"
                                                    }
                                                }
                                            },
                                            "description": "Potential root cause services"
                                        },
                                        "cascading_failures": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "service": {
                                                        "type": "string",
                                                        "description": "Service name"
                                                    },
                                                    "error_count": {
                                                        "type": "integer",
                                                        "description": "Number of errors"
                                                    },
                                                    "failing_dependencies": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "object",
                                                            "properties": {
                                                                "service": {
                                                                    "type": "string",
                                                                    "description": "Dependency service name"
                                                                },
                                                                "error_count": {
                                                                    "type": "integer",
                                                                    "description": "Number of errors"
                                                                },
                                                                "error_types": {
                                                                    "type": "object",
                                                                    "description": "Error types and counts"
                                                                }
                                                            }
                                                        },
                                                        "description": "Dependencies that are failing"
                                                    }
                                                }
                                            },
                                            "description": "Cascading failure patterns"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "description": "Bad request",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "error": {
                                            "type": "string",
                                            "description": "Error message"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}