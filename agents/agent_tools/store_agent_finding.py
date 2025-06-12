"""
Store Agent Finding - Bedrock agent tool to store findings in OpenSearch.

This tool allows agents to store their findings and actions in a dedicated OpenSearch index
to support human-in-the-loop workflows.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

from .opensearch_client import OpenSearchClient
from .agent_findings_store import AgentFindingsStore
from strands import tool
logger = logging.getLogger("agent_tools.store_agent_finding")

@tool
def store_agent_finding(
    agent_id: str,
    finding_type: str,
    severity: str,
    title: str,
    description: str,
    actions_taken: Optional[str] = None,
    proposed_actions: Optional[str] = None,
    related_resources: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    status: str = "pending_review"
) -> Dict[str, Any]:
    """
    Store agent findings in OpenSearch for human review and workflow management.

    Use this tool when an agent needs to document important findings, anomalies, or incidents
    that require human attention or review. This tool creates structured records in OpenSearch
    that can be tracked, prioritized, and acted upon by human operators.

    This tool connects to OpenSearch, creates a properly formatted finding document with all
    required and optional fields, and returns a unique identifier that can be used to reference
    the finding in future operations.

    Example response:
        {
            "finding_id": "f8d7e9c3-5b1a-4e2f-9c8d-7e6f5a4b3c2d",
            "status": "success",
            "message": "Finding stored successfully with ID: f8d7e9c3-5b1a-4e2f-9c8d-7e6f5a4b3c2d"
        }

    Notes:
        - Findings are automatically timestamped when stored
        - The default status is "pending_review" unless otherwise specified
        - Severity levels should follow standard conventions: "low", "medium", "high", "critical"
        - Finding types help categorize the nature of the finding (e.g., "anomaly", "incident", "recommendation")
        - Optional fields provide additional context that helps human reviewers understand and act on the finding

    Args:
        agent_id (str): Identifier for the agent making the finding.
                      Example: "auto-monitor-agent" or "security-agent"
        finding_type (str): Type of finding.
                         Example: "anomaly", "incident", "recommendation", "security_alert"
        severity (str): Severity level of the finding.
                     Example: "low", "medium", "high", "critical"
        title (str): Short title describing the finding.
                  Example: "Unusual CPU spike detected in production cluster"
        description (str): Detailed description of the finding.
                        Example: "CPU utilization exceeded 90% for over 15 minutes..."
        actions_taken (str, optional): Actions already taken by the agent.
                                    Example: "Increased monitoring frequency and collected diagnostic data"
        proposed_actions (str, optional): Actions proposed but requiring human approval.
                                       Example: "Recommend scaling the cluster by adding 2 more nodes"
        related_resources (dict, optional): Dictionary of related resources.
                                         Example: {"logs": ["path/to/log1", "path/to/log2"], "metrics": ["cpu_util", "memory_usage"]}
        metadata (dict, optional): Additional metadata about the finding.
                                Example: {"source_ip": "192.168.1.1", "affected_services": ["api-gateway", "auth-service"]}
        tags (list, optional): List of tags for categorization.
                            Example: ["performance", "database", "critical-path"]
        status (str, optional): Initial status of the finding. Default is "pending_review".
                             Example: "pending_review", "in_progress", "resolved"

    Returns:
        Dict[str, Any]: Dictionary containing:
        - finding_id: Unique identifier for the stored finding
        - status: Operation status ("success" or "error")
        - message: Description of the operation result
    """
    try:
        # Initialize OpenSearch client
        opensearch_client = OpenSearchClient()
        
        # Initialize the agent findings store
        findings_store = AgentFindingsStore(opensearch_connector=opensearch_client)
        
        # Prepare the finding document
        finding = {
            "agent_id": agent_id,
            "finding_type": finding_type,
            "severity": severity,
            "title": title,
            "description": description,
            "status": status
        }
        
        # Add optional fields if provided
        if actions_taken:
            finding["actions_taken"] = actions_taken
        
        if proposed_actions:
            finding["proposed_actions"] = proposed_actions
        
        if related_resources:
            finding["related_resources"] = related_resources
        
        if metadata:
            finding["metadata"] = metadata
        
        if tags:
            finding["tags"] = tags
        
        # Store the finding
        finding_id = findings_store.store_finding(finding)
        
        return {
            "finding_id": finding_id,
            "status": "success",
            "message": f"Finding stored successfully with ID: {finding_id}"
        }
        
    except Exception as e:
        logger.error(f"Error storing agent finding: {e}")
        return {
            "status": "error",
            "message": f"Failed to store finding: {str(e)}"
        }

@tool
def get_agent_finding(finding_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific agent finding from OpenSearch by its unique ID.

    Use this tool when you need to access the complete details of a previously stored
    agent finding. This is useful for following up on findings, checking their current
    status, or retrieving the full context of a finding referenced by its ID.

    This tool connects to OpenSearch, queries for the specific finding document using
    its unique identifier, and returns the complete finding record with all its fields.

    Example response:
        {
            "status": "success",
            "finding": {
                "finding_id": "f8d7e9c3-5b1a-4e2f-9c8d-7e6f5a4b3c2d",
                "agent_id": "auto-monitor-agent",
                "finding_type": "anomaly",
                "severity": "high",
                "title": "Unusual CPU spike detected in production cluster",
                "description": "CPU utilization exceeded 90% for over 15 minutes...",
                "actions_taken": "Increased monitoring frequency and collected diagnostic data",
                "proposed_actions": "Recommend scaling the cluster by adding 2 more nodes",
                "status": "pending_review",
                "timestamp": "2023-11-15T14:30:00Z",
                "related_resources": {"logs": ["path/to/log1"], "metrics": ["cpu_util"]},
                "metadata": {"affected_services": ["api-gateway"]},
                "tags": ["performance", "critical-path"]
            }
        }

    Notes:
        - If the finding doesn't exist, an error response will be returned
        - The complete finding document includes all fields that were provided when it was created
        - The finding document includes system-generated fields like timestamps
        - Use this tool before taking actions on findings to ensure you have the most current data

    Args:
        finding_id (str): The unique ID of the finding to retrieve.
                       Example: "f8d7e9c3-5b1a-4e2f-9c8d-7e6f5a4b3c2d"

    Returns:
        Dict[str, Any]: Dictionary containing:
        - status: Operation status ("success" or "error")
        - finding: The complete finding document (when successful)
        - message: Error description (when unsuccessful)
    """
    try:
        # Initialize OpenSearch client
        opensearch_client = OpenSearchClient()
        
        # Initialize the agent findings store
        findings_store = AgentFindingsStore(opensearch_connector=opensearch_client)
        
        # Get the finding
        finding = findings_store.get_finding(finding_id)
        
        return {
            "status": "success",
            "finding": finding
        }
        
    except Exception as e:
        logger.error(f"Error retrieving agent finding: {e}")
        return {
            "status": "error",
            "message": f"Failed to retrieve finding: {str(e)}"
        }

@tool
def get_pending_findings(agent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve all findings with "pending_review" status from OpenSearch.

    Use this tool when you need to get a list of all findings that require human attention
    and have not yet been addressed. This is particularly useful for prioritizing work,
    creating summaries of pending issues, or following up on previously reported findings.

    This tool connects to OpenSearch, queries for all findings with "pending_review" status,
    and optionally filters them by the specified agent ID. It returns a collection of
    finding documents along with a count of the total number of pending findings.

    Example response:
        {
            "status": "success",
            "count": 2,
            "findings": [
                {
                    "finding_id": "f8d7e9c3-5b1a-4e2f-9c8d-7e6f5a4b3c2d",
                    "agent_id": "auto-monitor-agent",
                    "finding_type": "anomaly",
                    "severity": "high",
                    "title": "Unusual CPU spike detected in production cluster",
                    "description": "CPU utilization exceeded 90% for over 15 minutes...",
                    "status": "pending_review",
                    "timestamp": "2023-11-15T14:30:00Z"
                },
                {
                    "finding_id": "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890",
                    "agent_id": "security-agent",
                    "finding_type": "security_alert",
                    "severity": "critical",
                    "title": "Multiple failed login attempts detected",
                    "description": "10 failed login attempts from IP 203.0.113.42...",
                    "status": "pending_review",
                    "timestamp": "2023-11-15T15:45:00Z"
                }
            ]
        }

    Notes:
        - Results are typically sorted by timestamp with newest findings first
        - The response includes a count of total findings for easy reference
        - Each finding in the list contains the core fields but may not include all optional fields
        - For complete details on a specific finding, use the get_agent_finding tool with the finding_id
        - If no pending findings exist, an empty list will be returned with count: 0

    Args:
        agent_id (str, optional): Filter findings by agent ID.
                               Example: "auto-monitor-agent" or "security-agent"
                               If not provided, findings from all agents will be returned.

    Returns:
        Dict[str, Any]: Dictionary containing:
        - status: Operation status ("success" or "error")
        - count: Number of pending findings
        - findings: List of pending finding documents (when successful)
        - message: Error description (when unsuccessful)
    """
    try:
        # Initialize OpenSearch client
        opensearch_client = OpenSearchClient()
        
        # Initialize the agent findings store
        findings_store = AgentFindingsStore(opensearch_connector=opensearch_client)
        
        # Get pending findings
        findings = findings_store.get_pending_findings(agent_id)
        
        return {
            "status": "success",
            "count": len(findings),
            "findings": findings
        }
        
    except Exception as e:
        logger.error(f"Error retrieving pending findings: {e}")
        return {
            "status": "error",
            "message": f"Failed to retrieve pending findings: {str(e)}"
        }