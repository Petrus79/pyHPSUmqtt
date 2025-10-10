#!/usr/bin/env python3
"""
MQTT Daemon Manager for pyHPSU
===============================

Home Assistant-style MQTT daemon management with robust reconnection logic.
Provides industrial-grade reliability for MQTT daemon mode.

Features:
- Exponential backoff reconnection
- Health monitoring with background thread
- Connection state management
- Clean shutdown procedures
- Thread-safe operations
- SSL/TLS support
"""

import time
import random
import threading
import logging
import signal
import ssl
from datetime import datetime
from enum import Enum
import paho.mqtt.client as mqtt


class MQTTConnectionState(Enum):
    """MQTT Connection state management (Home Assistant pattern)"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTION_LOST = "connection_lost"


class MQTTDaemon:
    """
    MQTT Daemon with robust reconnection capabilities.
    
    Implements Home Assistant-style connection management with:
    - Exponential backoff reconnection
    - Health monitoring
    - State management
    - Clean shutdown
    """
    
    def __init__(self, logger=None, **config):
        """
        Initialize MQTT Daemon
        
        Args:
            logger: Python logger instance
            **config: MQTT configuration parameters
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Configuration
        self.broker_host = config.get('broker_host', 'localhost')
        self.broker_port = config.get('broker_port', 1883)
        self.username = config.get('username')
        self.password = config.get('password')
        self.client_name = config.get('client_name', 'mqtt_client')
        self.prefix = config.get('prefix', '')
        self.command_topic = config.get('command_topic', 'command')
        self.status_topic = config.get('status_topic', 'status')
        self.qos = config.get('qos', 0)
        
        # SSL Configuration
        self.ssl_enabled = config.get('ssl_enabled', False)
        self.ssl_ca_cert = config.get('ssl_ca_cert')
        self.ssl_certfile = config.get('ssl_certfile')
        self.ssl_keyfile = config.get('ssl_keyfile')
        self.ssl_insecure = config.get('ssl_insecure', False)
        
        # Connection state management
        self.connection_state = MQTTConnectionState.DISCONNECTED
        self._connection_established = False  # Flag to prevent duplicate logging
        self.reconnect_delay = 5  # Initial delay in seconds
        self.max_reconnect_delay = 300  # Maximum delay (5 minutes)
        self.reconnect_attempts = 0
        self.last_connection_attempt = None
        
        # Threading
        self.connection_lock = threading.Lock()
        self.health_monitor_thread = None
        self.stop_health_monitor = False
        
        # MQTT Client
        self.client = None
        self.message_callback = None
        
    def setup_ssl_context(self):
        """Setup SSL context for MQTT connection"""
        if not self.ssl_enabled:
            return None
            
        self.logger.info("Configuring SSL/TLS for MQTT connection")
        context = ssl.create_default_context()
        
        if self.ssl_ca_cert:
            context.load_verify_locations(self.ssl_ca_cert)
            self.logger.info(f"Loaded CA certificate: {self.ssl_ca_cert}")
        
        if self.ssl_certfile and self.ssl_keyfile:
            context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
            self.logger.info("Loaded client certificate and key")
        
        if self.ssl_insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.logger.warning("SSL verification disabled - insecure mode enabled")
        
        return context
    
    def _schedule_reconnect(self):
        """Schedule MQTT reconnection with exponential backoff"""
        self.reconnect_attempts += 1
        
        # Exponential backoff with jitter
        jitter = random.uniform(0.8, 1.2)
        self.reconnect_delay = min(self.reconnect_delay * 2 * jitter, self.max_reconnect_delay)
        
        self.logger.info(f"Scheduling MQTT reconnection in {self.reconnect_delay:.1f} seconds (attempt {self.reconnect_attempts})")
        
        # Schedule reconnection
        threading.Timer(self.reconnect_delay, self._attempt_reconnect).start()
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to MQTT broker"""
        if self.stop_health_monitor:
            return
            
        with self.connection_lock:
            if self.connection_state == MQTTConnectionState.CONNECTED:
                return  # Already connected
                
            try:
                self.logger.info(f"Attempting MQTT reconnection to {self.broker_host}:{self.broker_port}")
                self.client.reconnect()
                
            except Exception as e:
                self.logger.warning(f"MQTT reconnection failed: {e}")
                self._schedule_reconnect()
    
    def _state_listener(self, state: MQTTConnectionState):
        """Handle MQTT connection state changes (Home Assistant pattern)"""
        # Only log and process if state actually changed
        if self.connection_state != state:
            self.logger.info(f"MQTT connection state changed to: {state.value}")
            self.connection_state = state
            
            if state == MQTTConnectionState.CONNECTION_LOST:
                self._schedule_reconnect()
            elif state == MQTTConnectionState.CONNECTED:
                # Reset reconnection parameters on successful connection
                self.reconnect_delay = 5
                self.reconnect_attempts = 0
    
    def _health_monitor(self):
        """Background thread to monitor MQTT connection health"""
        # Wait a bit before starting monitoring to avoid initial connection conflicts
        time.sleep(5)
        
        while not self.stop_health_monitor:
            try:
                # Only check connection if we expect to be connected
                if (self.client and self._connection_established and 
                    not self.client.is_connected() and 
                    self.connection_state not in [MQTTConnectionState.CONNECTION_LOST]):
                    
                    self.logger.info("MQTT connection lost, triggering reconnection...")
                    self._state_listener(MQTTConnectionState.CONNECTION_LOST)
                
                # Health check interval
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in MQTT health monitor: {e}")
                time.sleep(10)
        
        self.logger.info("MQTT health monitor stopped")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Enhanced MQTT connect callback with state management"""
        if rc == 0:
            # Only log if this is a new connection, not a duplicate callback
            if not self._connection_established:
                self.logger.info("Initial MQTT connection successful")
            
            self._state_listener(MQTTConnectionState.CONNECTED)
            
            # Subscribe to command topic
            command_topic = f"{self.prefix}/{self.command_topic}/+"
            self.logger.info(f"Subscribing to command topic: {command_topic}")
            try:
                result, mid = client.subscribe(command_topic, qos=self.qos)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.logger.info(f"Successfully subscribed to {command_topic}")
                else:
                    self.logger.error(f"Failed to subscribe to {command_topic}, result: {result}")
            except Exception as e:
                self.logger.error(f"Exception during subscription: {e}")
            
            # Reset reconnection parameters on successful connection
            self.reconnect_delay = 5
            self.reconnect_attempts = 0
            
            # Publish online status
            try:
                status_topic = f"{self.prefix}/{self.status_topic}"
                client.publish(status_topic, "online", qos=1, retain=True)
                # Set last will and testament
                client.will_set(status_topic, "offline", qos=1, retain=True)
            except Exception as e:
                self.logger.warning(f"Failed to publish online status: {e}")
        else:
            error_messages = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier", 
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            self.logger.error(f"MQTT daemon connection failed: {error_msg}")
            self._state_listener(MQTTConnectionState.DISCONNECTED)
    
    def _on_disconnect(self, client, userdata, rc):
        """Enhanced MQTT disconnect callback with state management"""
        if rc != 0:
            self.logger.warning(f"MQTT daemon disconnected unexpectedly (code: {rc})")
            self._state_listener(MQTTConnectionState.CONNECTION_LOST)
        else:
            self.logger.info("MQTT daemon disconnected gracefully")
            self._state_listener(MQTTConnectionState.DISCONNECTED)
        
        self._connection_established = False
    
    def _on_message(self, client, userdata, message):
        """MQTT message callback - delegates to external handler"""
        if self.message_callback:
            self.message_callback(client, userdata, message)
    
    def create_daemon_client(self, message_callback=None):
        """
        Create and configure MQTT daemon client
        
        Args:
            message_callback: Function to handle incoming messages
            
        Returns:
            Configured MQTT client instance
        """
        self.message_callback = message_callback
        
        # Create MQTT client with clean session for reliability
        client_name = f"{self.client_name}-mqttdaemon-{threading.current_thread().ident}"
        self.client = mqtt.Client(client_name, clean_session=True)
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Configure authentication
        if self.username:
            self.client.username_pw_set(self.username, password=self.password)
        
        # Enable logging
        self.client.enable_logger(self.logger)
        
        # Configure SSL if enabled
        ssl_context = self.setup_ssl_context()
        if ssl_context:
            self.client.tls_set_context(ssl_context)
        
        # Configure connection options for reliability
        self.client.reconnect_delay_set(min_delay=1, max_delay=self.max_reconnect_delay)
        self.client.max_inflight_messages_set(20)
        self.client.max_queued_messages_set(100)
        
        return self.client
    
    def connect(self):
        """
        Connect to MQTT broker with enhanced error handling
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.client.is_connected():
            self.logger.info("MQTT client already connected")
            return True
            
        try:
            self.logger.info(f"Connecting to MQTT broker: {self.broker_host}:{self.broker_port}")
            
            # Attempt connection
            result = self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            
            if result == mqtt.MQTT_ERR_SUCCESS:
                # Wait a moment for the connection to be established
                timeout = 5  # 5 second timeout
                start_time = time.time()
                
                while not self.client.is_connected() and (time.time() - start_time) < timeout:
                    self.client.loop(timeout=0.1)
                
                if self.client.is_connected():
                    self._connection_established = True
                    # Don't log here - let the callback handle logging
                    return True
                else:
                    self.logger.error("MQTT connection timeout")
                    self._state_listener(MQTTConnectionState.DISCONNECTED)
                    return False
            else:
                self.logger.error(f"MQTT connection failed with code: {result}")
                self._state_listener(MQTTConnectionState.DISCONNECTED)
                return False
                
        except Exception as e:
            self.logger.error(f"MQTT connection error: {e}")
            self._state_listener(MQTTConnectionState.DISCONNECTED)
            return False
    
    def start_health_monitor(self):
        """Start health monitor only if not already running"""
        if self.health_monitor_thread and self.health_monitor_thread.is_alive():
            self.logger.debug("MQTT health monitor already running")
            return
            
        self.stop_health_monitor = False
        self.health_monitor_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_monitor_thread.start()
        self.logger.info("MQTT health monitor started")
    
    def stop_daemon(self):
        """Clean shutdown of MQTT daemon"""
        self.logger.info("Shutting down MQTT daemon...")
        self.stop_health_monitor = True
        
        # Stop health monitor
        if self.health_monitor_thread and self.health_monitor_thread.is_alive():
            self.health_monitor_thread.join(timeout=5)
        
        # Clean disconnect
        if self.client and self.client.is_connected():
            try:
                status_topic = f"{self.prefix}/{self.status_topic}"
                self.client.publish(status_topic, "offline", qos=1, retain=True)
                self.client.loop_stop()
                self.client.disconnect()
                self.logger.info("MQTT daemon disconnected cleanly")
            except Exception as e:
                self.logger.warning(f"Error during MQTT disconnect: {e}")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for clean shutdown"""
        def signal_handler(sig, frame):
            self.logger.info(f"Received signal {sig}")
            self.stop_daemon()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        self.logger.info("Signal handlers configured")


def create_mqtt_daemon_config(options, logger):
    """
    Create MQTT daemon configuration dictionary from pyHPSU options
    
    Args:
        options: pyHPSU options object
        logger: Logger instance
        
    Returns:
        dict: MQTT configuration
    """
    # These would be populated from your existing MQTT configuration variables
    # You'll need to map these from your current global variables
    config = {
        'broker_host': getattr(options, 'mqtt_brokerhost', 'localhost'),
        'broker_port': getattr(options, 'mqtt_brokerport', 1883),
        'username': getattr(options, 'mqtt_username', None),
        'password': getattr(options, 'mqtt_password', None),
        'client_name': getattr(options, 'mqtt_clientname', 'rotex_hpsu'),
        'prefix': getattr(options, 'mqtt_prefix', 'rotex'),
        'command_topic': getattr(options, 'mqttdaemon_command_topic', 'command'),
        'status_topic': getattr(options, 'mqttdaemon_status_topic', 'status'),
        'qos': getattr(options, 'mqtt_qos', 0),
        'ssl_enabled': getattr(options, 'mqtt_ssl_enabled', False),
        'ssl_ca_cert': getattr(options, 'mqtt_ssl_ca_cert', None),
        'ssl_certfile': getattr(options, 'mqtt_ssl_certfile', None),
        'ssl_keyfile': getattr(options, 'mqtt_ssl_keyfile', None),
        'ssl_insecure': getattr(options, 'mqtt_ssl_insecure', False),
    }
    
    return config


# Example usage for integration with pyHPSU.py:
"""
from mqtt_daemon import MQTTDaemon, create_mqtt_daemon_config

# In your main function where you setup MQTT daemon:
if options.mqtt_daemon:
    # Create MQTT configuration
    mqtt_config = create_mqtt_daemon_config(options, logger)
    
    # Create MQTT daemon
    mqtt_daemon = MQTTDaemon(logger=logger, **mqtt_config)
    
    # Create and configure client
    mqtt_client = mqtt_daemon.create_daemon_client(message_callback=on_mqtt_message)
    
    # Connect and start monitoring
    if mqtt_daemon.connect():
        mqtt_daemon.start_health_monitor()
        mqtt_daemon.setup_signal_handlers()
        
        if options.auto:
            mqtt_client.loop_start()
    else:
        logger.warning("Initial connection failed, but health monitor will keep trying")
        mqtt_daemon.start_health_monitor()

# At the end of your main function:
if mqtt_client is not None:
    try:
        logger.info("Starting MQTT daemon event loop")
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        mqtt_daemon.stop_daemon()
"""