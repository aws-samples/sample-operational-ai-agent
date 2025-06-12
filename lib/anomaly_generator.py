"""
Anomaly generator module for creating realistic application anomalies.
"""

import random
import logging
import datetime
from typing import Dict, List, Any

from .datetime_utils import get_utc_now, format_iso

logger = logging.getLogger("anomaly_generator")

class AnomalyGenerator:
    """Generates realistic application anomalies based on configured patterns."""
    
    def __init__(self, anomaly_patterns: List[Dict[str, Any]], services_config: List[Dict[str, Any]]):
        """Initialize the anomaly generator with anomaly patterns and service configurations."""
        self.anomaly_patterns = anomaly_patterns or []  # Ensure it's not None
        self.services = {service["name"]: service for service in services_config} if services_config else {}
        self.last_check_time = get_utc_now()
        
        # Validate anomaly patterns
        self._validate_anomaly_patterns()
    
    def _validate_anomaly_patterns(self):
        """Validate that anomaly patterns reference valid services."""
        valid_patterns = []
        for pattern in self.anomaly_patterns:
            service = pattern.get("service")
            if service not in self.services:
                logger.warning(f"Anomaly pattern '{pattern.get('name')}' references unknown service '{service}'")
            else:
                valid_patterns.append(pattern)
        
        # Update anomaly_patterns to only include valid ones
        self.anomaly_patterns = valid_patterns
    
    def check_for_anomalies(self) -> List[Dict[str, Any]]:
        """Check if any anomalies should be triggered based on their probabilities."""
        current_time = get_utc_now()
        time_since_last_check = (current_time - self.last_check_time).total_seconds()
        self.last_check_time = current_time
        
        # Only check for anomalies every few seconds to avoid too many checks
        if time_since_last_check < 1.0:
            return []
        
        # If no valid anomaly patterns, return empty list
        if not self.anomaly_patterns:
            return []
        
        triggered_anomalies = []
        
        for pattern in self.anomaly_patterns:
            # Get the trigger probability and adjust it based on time since last check
            base_probability = pattern.get("trigger_probability", 0.01)
            
            # Scale probability based on time since last check (more time = higher chance)
            # but cap it to avoid too high probabilities
            adjusted_probability = min(base_probability * time_since_last_check / 10.0, base_probability * 2)
            
            # Check if this anomaly should be triggered
            if random.random() < adjusted_probability:
                # Create a copy of the pattern to avoid modifying the original
                anomaly = pattern.copy()
                
                # Add any additional runtime information
                if "duration_minutes" not in anomaly:
                    anomaly["duration_minutes"] = random.randint(3, 15)
                
                triggered_anomalies.append(anomaly)
                
                logger.info(f"Triggered anomaly: {anomaly['name']} on {anomaly['service']}")
        
        return triggered_anomalies
    
    def generate_correlated_anomalies(self, primary_anomaly):
        """Generate correlated anomalies based on a primary anomaly."""
        # This is a more advanced feature that could be implemented to simulate
        # cascading failures across service dependencies
        correlated_anomalies = []
        
        # If no services or invalid primary anomaly, return empty list
        if not self.services or not primary_anomaly or "service" not in primary_anomaly:
            return []
        
        # Get the service that has the primary anomaly
        service_name = primary_anomaly["service"]
        
        # Find services that depend on this service
        dependent_services = []
        for name, service in self.services.items():
            dependencies = service.get("dependencies", [])
            if service_name in dependencies:
                dependent_services.append(name)
        
        # If no dependent services, return empty list
        if not dependent_services:
            return []
        
        # For each dependent service, there's a chance to create a correlated anomaly
        for dep_service in dependent_services:
            if random.random() < 0.3:  # 30% chance for each dependent service
                # Create a latency or error anomaly in the dependent service
                anomaly_type = random.choice(["latency", "error_rate"])
                
                correlated_anomaly = {
                    "name": f"correlated_{anomaly_type}_{dep_service}",
                    "service": dep_service,
                    "type": anomaly_type,
                    "trigger_probability": 1.0,  # Always trigger this one
                    "duration_minutes": primary_anomaly.get("duration_minutes", 5) * 0.7,  # Shorter duration
                }
                
                if anomaly_type == "latency":
                    correlated_anomaly["latency_multiplier"] = random.uniform(1.5, 3.0)
                else:
                    correlated_anomaly["error_rate_multiplier"] = random.uniform(2.0, 5.0)
                
                correlated_anomalies.append(correlated_anomaly)
                
                logger.info(f"Generated correlated anomaly: {correlated_anomaly['name']} on {correlated_anomaly['service']}")
        
        return correlated_anomalies