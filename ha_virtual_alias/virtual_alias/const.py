from pathlib import Path

OPTIONS_PATH = Path("/data/options.json")

DNSMASQ_CONFIG_PATH = Path("/etc/dnsmasq.conf")

NFT_TABLE = "virtual_ips"
NFT_TABLE_FAMILY = "ip"

REST_API_URL = "http://supervisor"
WS_API_URL = "ws://supervisor/core/websocket"

WEB_HOST = "0.0.0.0"
WEB_PORT = 8101

EXCLUDED_INTERFACES = {
    "lo",
    "docker0",
    "hassio",
}