#!/usr/bin/env python3
"""
OpenSearch Application Log Simulator
-----------------------------------
Simulates application logs and metrics for anomaly detection using Amazon OpenSearch.
"""

import os
import sys
import time
import yaml
import random
import logging
import argparse
import datetime
import threading
import schedule
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.datetime_utils import get_utc_now, to_utc, format_iso

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import simulator modules
from lib.opensearch_connector import OpenSearchConnector
from lib.log_generator import LogGenerator
from lib.metrics_generator import MetricsGenerator
from lib.anomaly_generator import AnomalyGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("simulator")

class Simulator:
    """Main simulator class that orchestrates the log and metrics generation."""
    
    def __init__(self, config_path: str):
        """Initialize the simulator with the given configuration."""
        self.config = self._load_config(config_path)
        self.running = False
        self.simulation_start_time = None
        self.active_anomalies = {}
        
        # Try to get configuration from Secrets Manager first
        secret = self._get_secret()
        
        if secret and 'opensearch' in secret:
            logger.info("Using OpenSearch configuration from Secrets Manager")
            opensearch_config = secret['opensearch']
            # Ensure auth_type is set to basic_auth
            opensearch_config["auth_type"] = "basic_auth"


        self.opensearch = OpenSearchConnector(opensearch_config)
        self.log_generator = LogGenerator(self.config["services"])
        self.metrics_generator = MetricsGenerator(self.config["services"])
        self.anomaly_generator = AnomalyGenerator(
            self.config["anomaly_patterns"],
            self.config["services"]
        )
        
    def _get_secret(self):
        """Get configuration from AWS Secrets Manager."""
        secret_name = os.environ.get('OASIS_SECRET_NAME', 'oasis-configuration')
        secret_region = os.environ.get('OASIS_SECRET_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
        
        try:
            # Get secret from AWS Secrets Manager
            import boto3
            import json
            logger.info(f"Getting configuration from Secrets Manager: {secret_name}")
            secrets_client = boto3.client('secretsmanager', region_name=secret_region)
            secret_response = secrets_client.get_secret_value(SecretId=secret_name)
            return json.loads(secret_response['SecretString'])
        except Exception as e:
            logger.error(f"Error getting secret from Secrets Manager: {e}")
            return None
        self.running = False
        self.active_anomalies = {}
        self.simulation_start_time = None
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Configuration loaded from {config_path}")
                return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)
    
    def _generate_and_send_logs(self):
        """Generate and send logs to OpenSearch."""
        try:
            # Check for new anomalies to trigger
            self._check_anomalies()
            
            # Generate logs based on current state (including active anomalies)
            logs = self.log_generator.generate_logs(
                self.config["simulation"]["log_rate_per_second"],
                self.active_anomalies
            )
            
            # Send logs to OpenSearch
            if logs:
                self.opensearch.send_logs(logs)
                logger.debug(f"Sent {len(logs)} logs to OpenSearch")
        except Exception as e:
            logger.error(f"Error generating or sending logs: {e}")
    
    def _generate_and_send_metrics(self):
        """Generate and send metrics to OpenSearch."""
        try:
            # Generate metrics based on current state (including active anomalies)
            metrics = self.metrics_generator.generate_metrics(self.active_anomalies)
            
            # Send metrics to OpenSearch
            if metrics:
                self.opensearch.send_metrics(metrics)
                logger.debug(f"Sent {len(metrics)} metrics to OpenSearch")
        except Exception as e:
            logger.error(f"Error generating or sending metrics: {e}")
    
    def _check_anomalies(self):
        """Check if new anomalies should be triggered and update active anomalies."""
        # Check if existing anomalies should be ended
        current_time = get_utc_now()
        ended_anomalies = []
        
        for anomaly_id, anomaly_info in self.active_anomalies.items():
            end_time = anomaly_info["start_time"] + datetime.timedelta(
                minutes=anomaly_info["duration_minutes"]
            )
            if current_time >= end_time:
                ended_anomalies.append(anomaly_id)
                logger.info(f"Anomaly ended: {anomaly_info['name']} on {anomaly_info['service']}")
        
        # Remove ended anomalies
        for anomaly_id in ended_anomalies:
            del self.active_anomalies[anomaly_id]
        
        # Check for new anomalies to trigger
        new_anomalies = self.anomaly_generator.check_for_anomalies()
        for anomaly in new_anomalies:
            anomaly_id = f"{anomaly['name']}_{int(time.time())}"
            anomaly["start_time"] = current_time
            self.active_anomalies[anomaly_id] = anomaly
            logger.info(f"Anomaly started: {anomaly['name']} on {anomaly['service']}")
    
    def _check_simulation_duration(self):
        """Check if the simulation duration has been reached."""
        if self.config["simulation"]["duration_minutes"] > 0:
            elapsed_minutes = (get_utc_now() - self.simulation_start_time).total_seconds() / 60
            if elapsed_minutes >= self.config["simulation"]["duration_minutes"]:
                logger.info(f"Simulation duration of {self.config['simulation']['duration_minutes']} minutes reached")
                self.stop()
    
    def start(self):
        """Start the simulation."""
        if self.running:
            logger.warning("Simulation is already running")
            return
        
        logger.info("Starting simulation...")
        self.running = True
        self.simulation_start_time = get_utc_now()
        
        # Initialize OpenSearch indices if needed
        self.opensearch.initialize_indices()
        
        # Schedule log generation
        log_interval = 1.0 / self.config["simulation"]["log_rate_per_second"]
        schedule.every(log_interval).seconds.do(self._generate_and_send_logs)
        
        # Schedule metrics generation
        metrics_interval = self.config["simulation"]["metrics_interval_seconds"]
        schedule.every(metrics_interval).seconds.do(self._generate_and_send_metrics)
        
        # Schedule duration check
        schedule.every(1).minutes.do(self._check_simulation_duration)
        
        # Run the scheduler in a separate thread
        def run_scheduler():
            while self.running:
                schedule.run_pending()
                # Required delay for scheduler efficiency
                pass
        
        self.scheduler_thread = threading.Thread(target=run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        logger.info("Simulation started")
    
    def stop(self):
        """Stop the simulation."""
        if not self.running:
            logger.warning("Simulation is not running")
            return
        
        logger.info("Stopping simulation...")
        self.running = False
        
        # Wait for scheduler thread to finish
        if hasattr(self, 'scheduler_thread') and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        # Clear all scheduled jobs
        schedule.clear()
        
        logger.info("Simulation stopped")

def main():
    """Main entry point for the simulator."""
    parser = argparse.ArgumentParser(description="OpenSearch Application Log Simulator")
    parser.add_argument("-c", "--config", default="config.yaml", 
                        help="Path to configuration file (default: config.yaml)")
    args = parser.parse_args()
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "../.."))
    
    # If config path is not absolute, first check project root, then script directory
    if not os.path.isabs(args.config):
        config_path = os.path.join(project_root, args.config)
        if not os.path.exists(config_path):
            config_path = os.path.join(script_dir, args.config)
    else:
        config_path = args.config
        
    # Check if config file exists
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        logger.info(f"Checking for config in project root: {project_root}/config.yaml")
        config_path = os.path.join(project_root, "config.yaml")
        if not os.path.exists(config_path):
            logger.error(f"Config file not found in project root either")
            sys.exit(1)
    
    simulator = Simulator(config_path)
    
    try:
        simulator.start()
        
        # Keep the main thread alive
        while simulator.running:
            # Required delay for main thread to prevent CPU spinning
            pass
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        simulator.stop()

if __name__ == "__main__":
    main()