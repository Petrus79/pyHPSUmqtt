#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# config inf conf_file (defaults):
# [MQTT]
# BROKER = localhost
# PORT = 1883
# USERNAME = 
# PASSWORD = 
# CLIENTNAME = rotex_hpsu
# PREFIX = rotex
# SSL_ENABLED = False
# SSL_CA_CERT = 
# SSL_CERTFILE = 
# SSL_KEYFILE = 
# SSL_INSECURE = False

import configparser
import sys
import os
import paho.mqtt.client as mqtt
import ssl



class export():
    hpsu = None

    def __init__(self, hpsu=None, logger=None, config_file=None):
        self.hpsu = hpsu
        self.logger = logger
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        if os.path.isfile(self.config_file):
            self.config.read(self.config_file)
        else:
            sys.exit(os.EX_CONFIG)

        # object to store entire MQTT config section
        self.mqtt_config = self.config['MQTT']
        self.brokerhost = self.mqtt_config.get('BROKER', 'localhost')
        self.brokerport = self.mqtt_config.getint('PORT', 1883)
        self.clientname = self.mqtt_config.get('CLIENTNAME', 'rotex')
        self.username = self.mqtt_config.get('USERNAME', None)
        if self.username is None:
            self.logger.error("Username not set!!!!!")
        self.password = self.mqtt_config.get('PASSWORD', "NoPasswordSpecified")
        self.prefix = self.mqtt_config.get('PREFIX', "")
        self.qos = self.mqtt_config.getint('QOS', 0)
        # every other value implies false
        self.retain = self.mqtt_config.get('RETAIN', "NOT TRUE") == "True"
        # every other value implies false
        self.addtimestamp = self.mqtt_config.get('ADDTIMESTAMP', "NOT TRUE") == "True"
        
        # SSL/TLS Configuration
        self.ssl_enabled = self.mqtt_config.get('SSL_ENABLED', "False") == "True"
        self.ssl_ca_cert = self.mqtt_config.get('SSL_CA_CERT', None)
        self.ssl_certfile = self.mqtt_config.get('SSL_CERTFILE', None)
        self.ssl_keyfile = self.mqtt_config.get('SSL_KEYFILE', None)
        self.ssl_insecure = self.mqtt_config.get('SSL_INSECURE', "False") == "True"

        self.logger.info("configuration parsing complete")   

        # no need to create a different client name every time, because it only publish
        # so adding the PID at the end of the client name ensures every process have a
        # different client name only for readability on broker and troubleshooting
        self.clientname += "-" + str(os.getpid())

        self.logger.info("Creating new MQTT plugin client instance: " + self.clientname)
        # Use paho-mqtt v2 callback API
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.clientname
        )
        self.client.on_publish = self.on_publish
        if self.username:
           self.client.username_pw_set(self.username, password=self.password)
        self.client.enable_logger()
        
        # Configure SSL/TLS if enabled
        if self.ssl_enabled:
            self.logger.info("Configuring SSL/TLS for MQTT connection")
            context = ssl.create_default_context()
            
            if self.ssl_ca_cert:
                context.load_verify_locations(self.ssl_ca_cert)
                self.logger.info("Loaded CA certificate: " + self.ssl_ca_cert)
            
            if self.ssl_certfile and self.ssl_keyfile:
                context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
                self.logger.info("Loaded client certificate and key")
            
            if self.ssl_insecure:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.logger.warning("SSL verification disabled - insecure mode enabled")
            
            self.client.tls_set_context(context)

    
    def on_publish(self, client, userdata, mid, reason_code, properties):
        """paho-mqtt v2 on_publish callback with updated signature"""
        msg = f"mqtt output plugin data published, mid: {mid}, reason_code: {reason_code}"
        if reason_code != mqtt.MQTT_ERR_SUCCESS:
            self.logger.error(f"MQTT publish failed: mid={mid}, reason_code={reason_code}")
        else:
            self.hpsu.logger.debug(msg)

    def pushValues(self, vars=None):
        self.logger.info("connecting to broker: " + self.brokerhost + ", port: " + str(self.brokerport))
        
        # paho-mqtt v2: connect() returns None on success, raises exception on failure
        self.client.connect(self.brokerhost, port=self.brokerport)

        for r in vars:
            if self.prefix:
                self.client.publish(self.prefix + "/" + r['name'], payload=r['resp'], qos=int(self.qos))
            else:
                self.client.publish(r['name'], payload=r['resp'], qos=int(self.qos))

        self.client.disconnect()