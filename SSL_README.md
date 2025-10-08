# MQTT SSL/TLS Configuration

This guide explains how to configure SSL/TLS encryption for all MQTT connections in pyHPSU.

## Configuration Options

Add the following SSL options to your `[MQTT]` section in `/etc/pyHPSU/pyhpsu.conf`:

```ini
[MQTT]
BROKER = your.mqtt.broker.com
PORT = 8883
USERNAME = your_username
PASSWORD = your_password
CLIENTNAME = rotex_hpsu
PREFIX = rotex
COMMANDTOPIC = command

# SSL/TLS Configuration
SSL_ENABLED = True
SSL_CA_CERT = /path/to/ca.crt
SSL_CERTFILE = /path/to/client.crt
SSL_KEYFILE = /path/to/client.key
SSL_INSECURE = False
```

## SSL Configuration Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `SSL_ENABLED` | Enable SSL/TLS encryption | `False` | Yes (for SSL) |
| `SSL_CA_CERT` | Path to CA certificate for server verification | `None` | Optional |
| `SSL_CERTFILE` | Path to client certificate for client authentication | `None` | Optional |
| `SSL_KEYFILE` | Path to client private key for client authentication | `None` | Optional |
| `SSL_INSECURE` | Disable SSL certificate verification (testing only) | `False` | Optional |

## Usage Examples

### Basic SSL Connection (Server Certificate Verification)
```ini
SSL_ENABLED = True
SSL_CA_CERT = /etc/ssl/certs/ca-certificates.crt
```

### SSL with Client Certificate Authentication
```ini
SSL_ENABLED = True
SSL_CA_CERT = /path/to/ca.crt
SSL_CERTFILE = /path/to/client.crt
SSL_KEYFILE = /path/to/client.key
```

### SSL without Certificate Verification (Testing Only)
```ini
SSL_ENABLED = True
SSL_INSECURE = True
```

## Important Notes

1. **Port Configuration**: When using SSL, typically change the port from `1883` to `8883`
2. **Certificate Paths**: Ensure all certificate files are readable by the user running pyHPSU
3. **Security Warning**: Never use `SSL_INSECURE = True` in production environments
4. **Compatibility**: SSL is supported for both the main MQTT daemon and the MQTT output plugin

## Affected Components

SSL configuration applies to:
- Main MQTT daemon client (pyHPSU.py --mqtt_daemon)
- MQTT output plugin (HPSU/plugins/mqtt.py)

All MQTT connections will automatically use SSL when `SSL_ENABLED = True`.