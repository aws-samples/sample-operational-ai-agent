"""
Metrics generator module for creating realistic application metrics.
"""

import random
import logging
import datetime
from typing import Dict, List, Any

from faker import Faker

from .datetime_utils import get_utc_now, format_iso

logger = logging.getLogger("metrics_generator")
fake = Faker()

class MetricsGenerator:
    """Generates realistic application metrics for various services."""
    
    def __init__(self, services_config: List[Dict[str, Any]]):
        """Initialize the metrics generator with service configurations."""
        self.services = {service["name"]: service for service in services_config}
        
        # Define metric types by service type
        self.metric_types = {
            "gateway": [
                {"name": "request_count", "unit": "count"},
                {"name": "request_latency", "unit": "milliseconds"},
                {"name": "error_rate", "unit": "percent"},
                {"name": "status_2xx", "unit": "count"},
                {"name": "status_4xx", "unit": "count"},
                {"name": "status_5xx", "unit": "count"},
                {"name": "cpu_utilization", "unit": "percent"},
                {"name": "memory_utilization", "unit": "percent"},
                {"name": "active_connections", "unit": "count"}
            ],
            "microservice": [
                {"name": "request_count", "unit": "count"},
                {"name": "request_latency", "unit": "milliseconds"},
                {"name": "error_rate", "unit": "percent"},
                {"name": "cpu_utilization", "unit": "percent"},
                {"name": "memory_utilization", "unit": "percent"},
                {"name": "thread_count", "unit": "count"},
                {"name": "garbage_collection_time", "unit": "milliseconds"},
                {"name": "heap_usage", "unit": "megabytes"}
            ],
            "database": [
                {"name": "query_count", "unit": "count"},
                {"name": "query_latency", "unit": "milliseconds"},
                {"name": "connection_count", "unit": "count"},
                {"name": "cpu_utilization", "unit": "percent"},
                {"name": "memory_utilization", "unit": "percent"},
                {"name": "disk_usage", "unit": "percent"},
                {"name": "iops", "unit": "count"},
                {"name": "read_throughput", "unit": "bytes"},
                {"name": "write_throughput", "unit": "bytes"}
            ],
            "cache": [
                {"name": "hit_rate", "unit": "percent"},
                {"name": "miss_rate", "unit": "percent"},
                {"name": "eviction_count", "unit": "count"},
                {"name": "get_latency", "unit": "milliseconds"},
                {"name": "set_latency", "unit": "milliseconds"},
                {"name": "cpu_utilization", "unit": "percent"},
                {"name": "memory_utilization", "unit": "percent"},
                {"name": "item_count", "unit": "count"},
                {"name": "network_in", "unit": "bytes"},
                {"name": "network_out", "unit": "bytes"}
            ]
        }
    
    def _generate_base_metrics(self, service_name, service_type):
        """Generate base metrics for a service based on its type."""
        metrics = []
        timestamp = get_utc_now()
        
        # Get the metric types for this service type
        metric_types = self.metric_types.get(service_type, [])
        
        # Generate a value for each metric type
        for metric_type in metric_types:
            metric_name = metric_type["name"]
            unit = metric_type["unit"]
            
            # Generate a reasonable value based on metric name and unit
            value = self._generate_metric_value(metric_name, unit)
            
            # Create the metric entry
            metric = {
                "timestamp": timestamp,
                "service": service_name,
                "metric_name": metric_name,
                "metric_value": value,
                "unit": unit,
                "host": f"{service_name}-{fake.random_int(min=1, max=5)}",
                "container_id": fake.uuid4()[:8],
                "dimensions": {
                    "service_type": service_type,
                    "region": "us-east-1",
                    "environment": "production"
                }
            }
            
            metrics.append(metric)
        
        return metrics
    
    def _generate_metric_value(self, metric_name, unit):
        """Generate a reasonable metric value based on the metric name and unit."""
        if "utilization" in metric_name or "rate" in metric_name and unit == "percent":
            # Percentage values
            return round(random.uniform(5, 80), 2)
        
        elif "latency" in metric_name:
            # Latency values
            if "query" in metric_name:
                return round(random.uniform(1, 100), 2)
            else:
                return round(random.uniform(10, 500), 2)
        
        elif unit == "count":
            # Count values
            if "error" in metric_name or "status_5xx" in metric_name:
                return random.randint(0, 10)
            elif "status_4xx" in metric_name:
                return random.randint(5, 50)
            elif "status_2xx" in metric_name or "request_count" in metric_name:
                return random.randint(100, 1000)
            elif "connection" in metric_name:
                return random.randint(10, 200)
            elif "thread" in metric_name:
                return random.randint(10, 100)
            elif "eviction" in metric_name:
                return random.randint(0, 50)
            else:
                return random.randint(1, 100)
        
        elif unit == "bytes" or unit == "megabytes":
            # Size values
            if unit == "megabytes":
                return round(random.uniform(100, 2000), 2)
            else:
                return random.randint(10000, 10000000)
        
        else:
            # Default case
            return round(random.uniform(1, 100), 2)
    
    def _apply_anomalies(self, metrics, active_anomalies):
        """Apply anomaly effects to the metrics."""
        result_metrics = metrics.copy()  # Create a copy to avoid modifying while iterating
        restart_metrics = []  # Collect restart metrics separately
        
        for anomaly in active_anomalies.values():
            service_name = anomaly["service"]
            anomaly_type = anomaly["type"]
            
            # Find metrics for this service
            for metric in result_metrics:
                if metric["service"] != service_name:
                    continue
                
                metric_name = metric["metric_name"]
                
                # Apply anomaly effects based on type
                if anomaly_type == "error_rate" and "error_rate" in metric_name:
                    # Increase error rate
                    multiplier = anomaly.get("error_rate_multiplier", 10)
                    metric["metric_value"] = min(100, metric["metric_value"] * multiplier)
                
                elif anomaly_type == "latency" and "latency" in metric_name:
                    # Increase latency
                    multiplier = anomaly.get("latency_multiplier", 5)
                    metric["metric_value"] *= multiplier
                
                elif anomaly_type == "resource_exhaustion":
                    resource_type = anomaly.get("resource_type", "cpu")
                    
                    if resource_type == "cpu" and "cpu" in metric_name:
                        # High CPU utilization
                        max_util = anomaly.get("utilization_max", 95)
                        metric["metric_value"] = random.uniform(max_util - 10, max_util)
                    
                    elif resource_type == "memory" and "memory" in metric_name:
                        # Memory leak simulation
                        growth_rate = anomaly.get("growth_rate", 1.2)
                        # Calculate how far into the anomaly period we are (0 to 1)
                        start_time = anomaly["start_time"]
                        duration_minutes = anomaly["duration_minutes"]
                        elapsed = (datetime.datetime.now() - start_time).total_seconds() / 60
                        progress = min(1.0, elapsed / duration_minutes)
                        
                        # Apply exponential growth based on progress
                        metric["metric_value"] = min(95, 30 + 65 * (progress ** 2))
                
                elif anomaly_type == "crash_loop" and "restart" not in metric_name:
                    # Add a custom metric for restart count
                    restart_count = anomaly.get("restart_count", 5)
                    
                    # Find the timestamp from an existing metric
                    timestamp = metric["timestamp"]
                    
                    # Create a new restart count metric
                    restart_metric = {
                        "timestamp": timestamp,
                        "service": service_name,
                        "metric_name": "restart_count",
                        "metric_value": restart_count,
                        "unit": "count",
                        "host": metric["host"],
                        "container_id": metric["container_id"],
                        "dimensions": metric["dimensions"]
                    }
                    
                    # Add it to the separate list
                    restart_metrics.append(restart_metric)
                    break
        
        # Add all restart metrics at once after iteration
        result_metrics.extend(restart_metrics)
        return result_metrics
    
    def generate_metrics(self, active_anomalies):
        """Generate metrics for all services, applying any active anomalies."""
        all_metrics = []
        
        # Generate base metrics for each service
        for service_name, service in self.services.items():
            service_type = service["type"]
            metrics = self._generate_base_metrics(service_name, service_type)
            all_metrics.extend(metrics)
        
        # Apply anomaly effects
        all_metrics = self._apply_anomalies(all_metrics, active_anomalies)
        
        return all_metrics