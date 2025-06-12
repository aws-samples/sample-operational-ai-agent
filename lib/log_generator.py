"""
Log generator module for creating realistic application logs.
"""

import random
import logging
import datetime
import uuid
from typing import Dict, List, Any

from faker import Faker

from .datetime_utils import get_utc_now, format_iso

logger = logging.getLogger("log_generator")
fake = Faker()

class LogGenerator:
    """Generates realistic application logs for various services."""
    
    def __init__(self, services_config: List[Dict[str, Any]]):
        """Initialize the log generator with service configurations."""
        self.services = {service["name"]: service for service in services_config}
        self.service_dependencies = {
            service["name"]: service.get("dependencies", [])
            for service in services_config
        }
        
        # HTTP methods and paths for API-like services
        self.http_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        self.api_paths = [
            "/api/v1/users",
            "/api/v1/users/{user_id}",
            "/api/v1/products",
            "/api/v1/products/{product_id}",
            "/api/v1/orders",
            "/api/v1/orders/{order_id}",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/refresh",
            "/health",
            "/metrics",
            "/status"
        ]
        
        # Error types by service type
        self.error_types = {
            "gateway": [
                "RouteNotFound", "InvalidRequest", "AuthenticationFailure", 
                "RateLimitExceeded", "ServiceUnavailable"
            ],
            "microservice": [
                "InternalServerError", "DependencyTimeout", "ValidationError",
                "ResourceNotFound", "ConcurrencyConflict"
            ],
            "database": [
                "ConnectionFailure", "QueryTimeout", "DeadlockDetected",
                "DuplicateKey", "TransactionRollback"
            ],
            "cache": [
                "CacheEviction", "KeyNotFound", "MemoryLimitExceeded",
                "SerializationError", "ConnectionRefused"
            ]
        }
        
        # Log levels with weighted probabilities
        self.log_levels = {
            "INFO": 0.7,
            "WARN": 0.15,
            "ERROR": 0.1,
            "DEBUG": 0.05
        }
    
    def _generate_trace_context(self):
        """Generate a trace context with trace ID and span ID."""
        return {
            "trace_id": str(uuid.uuid4()),
            "request_id": fake.uuid4()
        }
    
    def _generate_api_context(self, service_type):
        """Generate API context with method, path, and status code."""
        if service_type not in ["gateway", "microservice"]:
            return {}
        
        method = random.choice(self.http_methods)
        path = random.choice(self.api_paths)
        
        # Replace path parameters with random values
        if "{user_id}" in path:
            path = path.replace("{user_id}", str(random.randint(1000, 9999)))
        if "{product_id}" in path:
            path = path.replace("{product_id}", str(random.randint(1000, 9999)))
        if "{order_id}" in path:
            path = path.replace("{order_id}", str(random.randint(1000, 9999)))
        
        # Default to successful status codes most of the time
        status_code = random.choices(
            [200, 201, 204, 400, 401, 403, 404, 500],
            weights=[0.7, 0.1, 0.05, 0.05, 0.03, 0.02, 0.03, 0.02]
        )[0]
        
        return {
            "method": method,
            "path": path,
            "status_code": status_code
        }
    
    def _calculate_latency(self, service_name, active_anomalies):
        """Calculate latency for a service, considering any active anomalies."""
        service = self.services[service_name]
        base_latency = service.get("latency_base_ms", 10)
        variance = service.get("latency_variance_ms", 5)
        
        # Start with normal latency distribution
        latency = max(1, random.normalvariate(base_latency, variance / 3))
        
        # Apply latency anomalies if active
        for anomaly in active_anomalies.values():
            if anomaly["service"] == service_name and anomaly["type"] == "latency":
                multiplier = anomaly.get("latency_multiplier", 5)
                latency *= multiplier
                # Add some jitter to make it more realistic
                latency += random.uniform(0, latency * 0.2)
        
        return round(latency, 2)
    
    def _should_generate_error(self, service_name, active_anomalies):
        """Determine if an error should be generated based on probabilities and anomalies."""
        service = self.services[service_name]
        base_error_prob = service.get("error_probability", 0.01)
        
        # Increase error probability if there are active error anomalies
        for anomaly in active_anomalies.values():
            if anomaly["service"] == service_name:
                if anomaly["type"] == "error_rate":
                    multiplier = anomaly.get("error_rate_multiplier", 10)
                    base_error_prob *= multiplier
                elif anomaly["type"] == "connection_failure":
                    base_error_prob = max(base_error_prob, 0.8)  # High probability of error
                elif anomaly["type"] == "crash_loop":
                    base_error_prob = max(base_error_prob, 0.9)  # Very high probability of error
        
        return random.random() < base_error_prob
    
    def _generate_error_context(self, service_name, service_type, active_anomalies):
        """Generate error context if an error should occur."""
        if not self._should_generate_error(service_name, active_anomalies):
            return {}
        
        # Select an error type based on service type
        error_types = self.error_types.get(service_type, ["UnknownError"])
        
        # Check if there's a specific error message from an anomaly
        error_message = None
        for anomaly in active_anomalies.values():
            if anomaly["service"] == service_name and "error_message" in anomaly:
                error_type = anomaly.get("error_type", random.choice(error_types))
                error_message = anomaly["error_message"]
                break
        
        if error_message is None:
            error_type = random.choice(error_types)
            
            # Generate appropriate error message based on error type
            if "Timeout" in error_type:
                error_message = f"Operation timed out after {random.randint(3000, 10000)}ms"
            elif "NotFound" in error_type:
                error_message = f"Resource with ID '{fake.uuid4()}' not found"
            elif "Authentication" in error_type or "Auth" in error_type:
                error_message = "Invalid credentials or token expired"
            elif "RateLimit" in error_type:
                error_message = f"Rate limit of {random.randint(100, 1000)} requests per minute exceeded"
            elif "Connection" in error_type:
                # Fix: Handle case when service has no dependencies
                dependencies = self.service_dependencies.get(service_name, [])
                if dependencies:
                    dependency = random.choice(dependencies)
                else:
                    dependency = "unknown"
                error_message = f"Failed to connect to {dependency} service"
            else:
                error_message = f"An unexpected error occurred: {fake.sentence()}"
        
        return {
            "error_type": error_type,
            "error_message": error_message,
            "level": "ERROR"
        }
    
    def _generate_resource_metrics(self, service_name, active_anomalies):
        """Generate resource utilization metrics for a service."""
        # Default resource utilization
        cpu_utilization = random.uniform(10, 40)  # percentage
        memory_utilization = random.uniform(20, 60)  # percentage
        
        # Apply resource exhaustion anomalies if active
        for anomaly in active_anomalies.values():
            if anomaly["service"] == service_name and anomaly["type"] == "resource_exhaustion":
                resource_type = anomaly.get("resource_type", "cpu")
                
                if resource_type == "cpu":
                    max_util = anomaly.get("utilization_max", 95)
                    cpu_utilization = random.uniform(max_util - 10, max_util)
                
                elif resource_type == "memory":
                    # Simulate memory leak with exponential growth
                    growth_rate = anomaly.get("growth_rate", 1.2)
                    # Calculate how far into the anomaly period we are (0 to 1)
                    start_time = anomaly["start_time"]
                    duration_minutes = anomaly["duration_minutes"]
                    elapsed = (datetime.datetime.now() - start_time).total_seconds() / 60
                    progress = min(1.0, elapsed / duration_minutes)
                    
                    # Apply exponential growth based on progress
                    memory_utilization = min(95, 30 + 65 * (progress ** 2))
        
        return {
            "cpu_utilization": round(cpu_utilization, 2),
            "memory_utilization": round(memory_utilization, 2)
        }
    
    def _generate_log_message(self, service_name, service_type, context):
        """Generate a log message based on service type and context."""
        if context.get("error_message"):
            return context["error_message"]
        
        if service_type == "gateway":
            return f"Processed {context.get('method', 'REQUEST')} {context.get('path', '/api')} in {context.get('latency_ms', 0)}ms with status {context.get('status_code', 200)}"
        
        elif service_type == "microservice":
            if random.random() < 0.7:  # 70% API-like logs
                return f"Handled {context.get('method', 'REQUEST')} {context.get('path', '/api')} in {context.get('latency_ms', 0)}ms"
            else:  # 30% processing logs
                actions = ["Processed", "Completed", "Executed", "Finished", "Handled"]
                objects = ["request", "task", "job", "operation", "transaction"]
                return f"{random.choice(actions)} {random.choice(objects)} in {context.get('latency_ms', 0)}ms"
        
        elif service_type == "database":
            operations = ["query", "transaction", "update", "insert", "delete", "select"]
            return f"Database {random.choice(operations)} completed in {context.get('latency_ms', 0)}ms"
        
        elif service_type == "cache":
            operations = ["get", "set", "delete", "update", "expire"]
            return f"Cache {random.choice(operations)} operation completed in {context.get('latency_ms', 0)}ms"
        
        else:
            return f"Operation completed in {context.get('latency_ms', 0)}ms"
    
    def _select_log_level(self, context):
        """Select a log level based on context and weighted probabilities."""
        if context.get("error_type"):
            return "ERROR"
        
        if context.get("status_code", 200) >= 400:
            return "WARN" if context.get("status_code") < 500 else "ERROR"
        
        # Use weighted random selection for normal logs
        levels = list(self.log_levels.keys())
        weights = list(self.log_levels.values())
        return random.choices(levels, weights=weights)[0]
    
    def generate_logs(self, rate_per_second, active_anomalies):
        """Generate logs for all services based on the specified rate."""
        logs = []
        num_logs = max(1, int(random.normalvariate(rate_per_second, rate_per_second / 5)))
        
        timestamp = get_utc_now()
        
        # Ensure we have services to generate logs for
        if not self.services:
            logger.warning("No services configured for log generation")
            return []
        
        for _ in range(num_logs):
            # Select a service weighted by importance (gateway and microservices generate more logs)
            service_weights = {
                name: 3 if self.services[name]["type"] in ["gateway", "microservice"] else 1
                for name in self.services
            }
            
            # Ensure we have services with weights
            if not service_weights:
                logger.warning("No services with weights for log generation")
                continue
                
            service_name = random.choices(
                list(service_weights.keys()),
                weights=list(service_weights.values())
            )[0]
            
            service = self.services[service_name]
            service_type = service["type"]
            
            # Generate trace context (for distributed tracing)
            trace_context = self._generate_trace_context()
            
            # Generate API context for API-like services
            api_context = self._generate_api_context(service_type)
            
            # Calculate latency
            latency_ms = self._calculate_latency(service_name, active_anomalies)
            
            # Generate error context if applicable
            error_context = self._generate_error_context(service_name, service_type, active_anomalies)
            
            # Combine all context
            context = {
                **trace_context,
                **api_context,
                "latency_ms": latency_ms,
                **error_context
            }
            
            # Generate resource metrics
            resource_metrics = self._generate_resource_metrics(service_name, active_anomalies)
            
            # Select log level
            level = context.get("level") or self._select_log_level(context)
            
            # Generate log message
            message = self._generate_log_message(service_name, service_type, context)
            
            # Create the log entry
            log_entry = {
                "timestamp": timestamp,
                "service": service_name,
                "level": level,
                "message": message,
                "host": f"{service_name}-{fake.random_int(min=1, max=5)}",
                "container_id": fake.uuid4()[:8],
                **context,
                **resource_metrics
            }
            
            logs.append(log_entry)
            
            # Add slight timestamp variation for more realistic logs
            timestamp = timestamp + datetime.timedelta(milliseconds=random.randint(1, 100))
        
        return logs