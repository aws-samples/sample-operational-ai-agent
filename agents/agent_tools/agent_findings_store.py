"""
Agent Findings Store - Tool to store agent findings and actions in OpenSearch.

This module provides functionality to store agent findings and actions in a separate
OpenSearch index with unique IDs to support human-in-the-loop workflows.
"""

import json
import logging
import uuid
import datetime
from typing import Dict, List, Any, Optional

from opensearchpy import OpenSearch
from .opensearch_client import OpenSearchClient

logger = logging.getLogger("agent_findings_store")

class AgentFindingsStore:
    """Store for agent findings and actions to support human-in-the-loop workflows."""
    
    def __init__(self, opensearch_connector: Optional[OpenSearchClient] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize the agent findings store.
        
        Args:
            opensearch_connector: An existing OpenSearchConnector instance to reuse
            config: Configuration for creating a new OpenSearchConnector if one isn't provided
        """
        if opensearch_connector:
            self.opensearch_connector = opensearch_connector
            self.client = opensearch_connector.client
        elif config:
            self.opensearch_connector = OpenSearchClient(config)
            self.client = self.opensearch_connector.client
        else:
            # Create a new OpenSearchClient with default config path
            try:
                self.opensearch_connector = OpenSearchClient()
                self.client = self.opensearch_connector.client
            except Exception as e:
                raise ValueError(f"Failed to create OpenSearchClient with default config: {e}")
        
        self.index_name = f"{self.opensearch_connector.index_prefix}-agent-findings"
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize the agent findings index if it doesn't exist."""
        try:
            if not self.client.indices.exists(index=self.index_name):
                logger.info(f"Creating agent findings index: {self.index_name}")
                self.client.indices.create(
                    index=self.index_name,
                    body={
                        "mappings": {
                            "properties": {
                                "id": {"type": "keyword"},
                                "timestamp": {"type": "date"},
                                "agent_id": {"type": "keyword"},
                                "finding_type": {"type": "keyword"},
                                "severity": {"type": "keyword"},
                                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                                "description": {"type": "text"},
                                "actions_taken": {"type": "text"},
                                "proposed_actions": {"type": "text"},
                                "status": {"type": "keyword"},
                                "human_feedback": {"type": "text"},
                                "human_approved": {"type": "boolean"},
                                "related_resources": {"type": "object"},
                                "metadata": {"type": "object"},
                                "tags": {"type": "keyword"}
                            }
                        },
                        "settings": {
                            "number_of_shards": 3,
                            "number_of_replicas": 1
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Error initializing agent findings index: {e}")
            raise
    
    def store_finding(self, finding: Dict[str, Any]) -> str:
        """Store an agent finding in OpenSearch.
        
        Args:
            finding: Dictionary containing the finding details
                Required fields:
                - agent_id: Identifier for the agent
                - finding_type: Type of finding (e.g., "anomaly", "incident", "recommendation")
                - severity: Severity level (e.g., "low", "medium", "high", "critical")
                - title: Short title describing the finding
                - description: Detailed description of the finding
                
                Optional fields:
                - actions_taken: Actions already taken by the agent
                - proposed_actions: Actions proposed but requiring human approval
                - related_resources: Dictionary of related resources (e.g., logs, metrics)
                - metadata: Additional metadata about the finding
                - tags: List of tags for categorization
                
        Returns:
            str: The unique ID of the stored finding
        """
        if not finding:
            raise ValueError("Finding cannot be empty")
        
        # Validate required fields
        required_fields = ["agent_id", "finding_type", "severity", "title", "description"]
        for field in required_fields:
            if field not in finding:
                raise ValueError(f"Required field '{field}' missing from finding")
        
        # Generate a unique ID if not provided
        if "id" not in finding:
            finding["id"] = str(uuid.uuid4())
        
        # Add timestamp if not provided
        if "timestamp" not in finding:
            finding["timestamp"] = datetime.datetime.now().isoformat()
        elif isinstance(finding["timestamp"], datetime.datetime):
            finding["timestamp"] = finding["timestamp"].isoformat()
        
        # Set initial status if not provided
        if "status" not in finding:
            finding["status"] = "pending_review"
        
        try:
            # Index the finding
            self.client.index(
                index=self.index_name,
                body=finding,
                id=finding["id"],
                refresh=True  # Ensure the document is immediately searchable
            )
            logger.info(f"Stored agent finding with ID: {finding['id']}")
            return finding["id"]
        except Exception as e:
            logger.error(f"Error storing agent finding: {e}")
            raise
    
    def get_finding(self, finding_id: str) -> Dict[str, Any]:
        """Retrieve a specific finding by ID.
        
        Args:
            finding_id: The unique ID of the finding
            
        Returns:
            Dict: The finding document
        """
        try:
            response = self.client.get(
                index=self.index_name,
                id=finding_id
            )
            return response["_source"]
        except Exception as e:
            logger.error(f"Error retrieving finding {finding_id}: {e}")
            raise
    
    def update_finding(self, finding_id: str, updates: Dict[str, Any]) -> bool:
        """Update a finding with new information.
        
        Args:
            finding_id: The unique ID of the finding
            updates: Dictionary containing the fields to update
            
        Returns:
            bool: True if update was successful
        """
        try:
            self.client.update(
                index=self.index_name,
                id=finding_id,
                body={"doc": updates},
                refresh=True
            )
            logger.info(f"Updated finding {finding_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating finding {finding_id}: {e}")
            raise
    
    def add_human_feedback(self, finding_id: str, feedback: str, approved: bool = None) -> bool:
        """Add human feedback to a finding.
        
        Args:
            finding_id: The unique ID of the finding
            feedback: Human feedback text
            approved: Whether the finding/actions are approved
            
        Returns:
            bool: True if update was successful
        """
        updates = {"human_feedback": feedback}
        
        if approved is not None:
            updates["human_approved"] = approved
            updates["status"] = "approved" if approved else "rejected"
        
        return self.update_finding(finding_id, updates)
    
    def search_findings(self, query: Dict[str, Any], size: int = 100) -> List[Dict[str, Any]]:
        """Search for findings based on a query.
        
        Args:
            query: OpenSearch query DSL
            size: Maximum number of results to return
            
        Returns:
            List: List of matching findings
        """
        try:
            response = self.client.search(
                index=self.index_name,
                body=query,
                size=size
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Error searching findings: {e}")
            raise
    
    def get_pending_findings(self, agent_id: str = None) -> List[Dict[str, Any]]:
        """Get findings pending human review.
        
        Args:
            agent_id: Optional filter by agent ID
            
        Returns:
            List: List of findings pending review
        """
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"status": "pending_review"}}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}]
        }
        
        if agent_id:
            query["query"]["bool"]["must"].append({"term": {"agent_id": agent_id}})
        
        return self.search_findings(query)