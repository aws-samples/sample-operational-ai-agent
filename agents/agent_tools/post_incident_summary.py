"""
Bedrock agent tool for generating post-incident summaries.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .opensearch_client import OpenSearchClient
from .query_logs import query_logs
from .query_metrics import query_metrics
from .correlate_errors import correlate_errors_across_services
from .check_recent_deployment import check_recent_deployment
from strands import tool
logger = logging.getLogger("agent_tools.post_incident_summary")

@tool
def post_incident_summary(service: str, incident_start: str, incident_end: str, 
                          include_metrics: bool = True) -> Dict[str, Any]:
    """
    Generate a comprehensive post-incident summary for a service outage or degradation.

    Use this tool when you need to analyze an incident after it has been resolved to
    understand what happened, why it happened, and how to prevent similar incidents in
    the future. This tool is valuable for post-mortem meetings, incident reports, and
    improving system reliability.

    This tool collects and analyzes logs, metrics, service correlations, and deployment
    data from the incident period to identify potential root causes, impact, and provide
    actionable recommendations for preventing similar incidents.

    Example response:
        {
            "summary": {
                "incident_period": {
                    "start": "2023-04-01T10:15:00Z",
                    "end": "2023-04-01T11:45:00Z",
                    "duration_minutes": 90,
                    "duration_hours": 1.5
                },
                "affected_service": "payment-service",
                "error_statistics": {
                    "error_count": 1245,
                    "warning_count": 89,
                    "error_types": {"ConnectionError": 987, "TimeoutError": 258},
                    "status_codes": {"500": 1156, "503": 89}
                },
                "potential_causes": [
                    {
                        "type": "deployment",
                        "description": "Deployment at 2023-04-01T10:05:00Z may have caused the incident",
                        "confidence": "high"
                    }
                ]
            },
            "recommendations": [
                {
                    "type": "rollback",
                    "description": "Consider rolling back the recent deployment",
                    "priority": "high"
                },
                {
                    "type": "process",
                    "description": "Review deployment procedures and add more pre-deployment testing",
                    "priority": "medium"
                }
            ]
        }

    Notes:
        - Analyzes error logs, warning logs, and metrics during the incident period
        - Checks for recent deployments that may have caused the incident
        - Identifies potential cascading failures from dependent services
        - Provides actionable recommendations based on the identified causes
        - Includes sample error logs to help with troubleshooting
        - Generates metrics summaries to understand performance impact

    Args:
        service (str): The service that experienced the incident.
                      Example: "payment-service" or "api-gateway"
        incident_start (str): Start time of the incident in ISO format.
                             Example: "2023-04-01T10:15:00Z"
        incident_end (str): End time of the incident in ISO format.
                           Example: "2023-04-01T11:45:00Z"
        include_metrics (bool, optional): Whether to include metrics in the summary.
                                         Default is True.
    
    Returns:
        Dict[str, Any]: Dictionary containing:
        - summary: Overview of the incident including timing, affected service, and error statistics
        - error_logs: Sample of error logs from the incident period
        - warning_logs: Sample of warning logs from the incident period
        - metrics_summary: Statistical summary of key metrics during the incident
        - correlations: Analysis of related service failures and potential root causes
        - deployment_impact: Analysis of recent deployments and their impact
        - recommendations: Actionable recommendations to prevent similar incidents
    """
    try:
        client = OpenSearchClient()
        
        # Create a custom timeframe string for the incident period
        incident_timeframe = f"{incident_start}/{incident_end}"
        
        # Calculate incident duration
        try:
            start_dt = datetime.fromisoformat(incident_start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(incident_end.replace('Z', '+00:00'))
            duration_seconds = (end_dt - start_dt).total_seconds()
            duration_minutes = duration_seconds / 60
            duration_hours = duration_minutes / 60
        except Exception as e:
            logger.error(f"Error calculating incident duration: {e}")
            duration_seconds = 0
            duration_minutes = 0
            duration_hours = 0
        
        # Get error logs during the incident
        error_logs = query_logs(
            service=service,
            timeframe=incident_timeframe,
            level="ERROR",
            limit=100
        )
        
        # Get warning logs during the incident
        warning_logs = query_logs(
            service=service,
            timeframe=incident_timeframe,
            level="WARN",
            limit=50
        )
        
        # Get metrics if requested
        metrics_data = {}
        if include_metrics:
            # CPU utilization
            cpu_metrics = query_metrics(
                service=service,
                metric_name="cpu_utilization",
                timeframe=incident_timeframe,
                window="1m",
                aggregation="avg"
            )
            
            # Memory utilization
            memory_metrics = query_metrics(
                service=service,
                metric_name="memory_utilization",
                timeframe=incident_timeframe,
                window="1m",
                aggregation="avg"
            )
            
            # Error rate
            error_rate_metrics = query_metrics(
                service=service,
                metric_name="error_rate",
                timeframe=incident_timeframe,
                window="1m",
                aggregation="avg"
            )
            
            # Request latency
            latency_metrics = query_metrics(
                service=service,
                metric_name="request_latency",
                timeframe=incident_timeframe,
                window="1m",
                aggregation="avg"
            )
            
            metrics_data = {
                "cpu_utilization": cpu_metrics,
                "memory_utilization": memory_metrics,
                "error_rate": error_rate_metrics,
                "request_latency": latency_metrics
            }
        
        # Check for correlations with other services
        correlations = correlate_errors_across_services(
            timeframe=incident_timeframe,
            error_threshold=3,
            include_warnings=True
        )
        
        # Check for recent deployments
        # Look at a wider window (3 hours before incident)
        deployment_start = start_dt - timedelta(hours=3)
        deployment_timeframe = f"{deployment_start.isoformat()}/{incident_end}"
        
        deployments = check_recent_deployment(
            service=service,
            timeframe=deployment_timeframe
        )
        
        # Extract key information for the summary
        error_count = error_logs.get("summary", {}).get("total_logs", 0)
        warning_count = warning_logs.get("summary", {}).get("total_logs", 0)
        
        # Extract error types
        error_types = {}
        for log in error_logs.get("logs", []):
            if "error_type" in log:
                error_type = log["error_type"]
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Extract status codes
        status_codes = {}
        for log in error_logs.get("logs", []):
            if "status_code" in log:
                status_code = log["status_code"]
                status_codes[status_code] = status_codes.get(status_code, 0) + 1
        
        # Identify potential root causes
        potential_causes = []
        
        # Check for deployment-related issues
        for analysis in deployments.get("impact_analysis", []) or []:
            if analysis and analysis.get("service") == service and analysis.get("impact") == "negative":
                deployment_time = analysis.get("deployment_time")
                # Check if deployment was close to incident start (within 30 minutes)
                try:
                    if deployment_time:  # Check if deployment_time is not None
                        deployment_dt = datetime.fromisoformat(deployment_time.replace('Z', '+00:00'))
                        if abs((start_dt - deployment_dt).total_seconds()) < 1800:  # 30 minutes
                            potential_causes.append({
                                "type": "deployment",
                                "description": f"Deployment at {deployment_time} may have caused the incident",
                                "confidence": "high"
                            })
                except Exception:
                    pass
        
        # Check for dependency failures
        for failure in correlations.get("cascading_failures", []) or []:
            if failure and failure.get("service") == service:
                for dep in failure.get("failing_dependencies", []) or []:
                    if dep and "service" in dep and "error_count" in dep:
                        potential_causes.append({
                            "type": "dependency_failure",
                            "description": f"Dependency {dep['service']} failed with {dep['error_count']} errors",
                            "confidence": "medium"
                        })
        
        # Check for resource exhaustion
        if include_metrics:
            cpu_stats = metrics_data.get("cpu_utilization", {}).get("summary", {}).get("statistics", {})
            memory_stats = metrics_data.get("memory_utilization", {}).get("summary", {}).get("statistics", {})
            
            if cpu_stats.get("max", 0) > 90:
                potential_causes.append({
                    "type": "resource_exhaustion",
                    "description": f"CPU utilization peaked at {cpu_stats.get('max')}%",
                    "confidence": "medium"
                })
            
            if memory_stats.get("max", 0) > 90:
                potential_causes.append({
                    "type": "resource_exhaustion",
                    "description": f"Memory utilization peaked at {memory_stats.get('max')}%",
                    "confidence": "medium"
                })
        
        # Generate summary
        summary = {
            "incident_period": {
                "start": incident_start,
                "end": incident_end,
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_minutes,
                "duration_hours": duration_hours
            },
            "affected_service": service,
            "error_statistics": {
                "error_count": error_count,
                "warning_count": warning_count,
                "error_types": error_types,
                "status_codes": status_codes
            },
            "potential_causes": potential_causes,
            "related_services": correlations.get("problematic_services", []),
            "recent_deployments": len(deployments.get("deployments", [])),
            "metrics_analyzed": list(metrics_data.keys()) if include_metrics else []
        }
        
        # Generate recommendations based on findings
        recommendations = []
        
        if any(cause["type"] == "deployment" for cause in potential_causes):
            recommendations.append({
                "type": "rollback",
                "description": "Consider rolling back the recent deployment",
                "priority": "high"
            })
            recommendations.append({
                "type": "process",
                "description": "Review deployment procedures and add more pre-deployment testing",
                "priority": "medium"
            })
        
        if any(cause["type"] == "dependency_failure" for cause in potential_causes):
            recommendations.append({
                "type": "resilience",
                "description": "Implement circuit breakers for failing dependencies",
                "priority": "high"
            })
            recommendations.append({
                "type": "monitoring",
                "description": "Enhance monitoring for critical dependencies",
                "priority": "medium"
            })
        
        if any(cause["type"] == "resource_exhaustion" for cause in potential_causes):
            recommendations.append({
                "type": "scaling",
                "description": "Increase resource limits or implement auto-scaling",
                "priority": "high"
            })
            recommendations.append({
                "type": "optimization",
                "description": "Review code for potential optimizations",
                "priority": "medium"
            })
        
        # Add general recommendations
        recommendations.append({
            "type": "monitoring",
            "description": "Set up alerts for similar error patterns",
            "priority": "medium"
        })
        
        recommendations.append({
            "type": "documentation",
            "description": "Update runbooks with resolution steps from this incident",
            "priority": "medium"
        })
        
        return {
            "summary": summary,
            "error_logs": error_logs.get("logs", [])[:10],  # Include only first 10 logs
            "warning_logs": warning_logs.get("logs", [])[:5],  # Include only first 5 logs
            "metrics_summary": {
                metric: data.get("summary", {}).get("statistics", {})
                for metric, data in metrics_data.items()
            } if include_metrics else {},
            "correlations": {
                "potential_root_causes": correlations.get("potential_root_causes", []),
                "cascading_failures": correlations.get("cascading_failures", [])
            },
            "deployment_impact": deployments.get("impact_analysis", []),
            "recommendations": recommendations
        }
    
    except Exception as e:
        logger.error(f"Error generating post-incident summary: {e}")
        return {
            "error": str(e),
            "summary": {
                "incident_period": {
                    "start": incident_start,
                    "end": incident_end
                },
                "affected_service": service
            }
        }