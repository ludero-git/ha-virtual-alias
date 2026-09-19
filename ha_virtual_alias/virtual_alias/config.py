import ipaddress
import json

from dataclasses import dataclass
from typing import Any

from .const import OPTIONS_PATH


@dataclass
class Alias:
    friendly_name: str
    mac: str
    virtual_ip: ipaddress.IPv4Address | None
    virtual_hostname: str | None


@dataclass
class ArpDiscoveryConfig:
    enabled: bool
    interval_seconds: int
    exclude_interfaces: tuple[str, ...]


@dataclass
class HomeAssistantDiscoveryConfig:
    enabled: bool
    include_zeroconf: bool


@dataclass
class WebUIConfig:
    log_lines: int
    humanize_datetime: bool


@dataclass
class Config:
    aliases: tuple[Alias, ...]
    arp_discovery: ArpDiscoveryConfig
    home_assistant_discovery: HomeAssistantDiscoveryConfig
    webui: WebUIConfig
    log_level: str


def parse_config(raw: dict[str, Any]) -> Config:
    arp_discovery = raw["arp_discovery"]
    home_assistant_discovery = raw["home_assistant_discovery"]
    webui = raw["webui"]

    aliases = tuple(
        Alias(
            friendly_name=item["friendly_name"],
            mac=item["mac"],
            virtual_ip=(
                ipaddress.IPv4Address(item["virtual_ip"])
                if item.get("virtual_ip")
                else None
            ),
            virtual_hostname=item.get("virtual_hostname"),
        )
        for item in raw["aliases"]
    )

    macs = [alias.mac.lower() for alias in aliases]

    if len(macs) != len(set(macs)):
        raise ValueError("Alias MAC addresses must be unique")

    return Config(
        aliases=aliases,
        arp_discovery=ArpDiscoveryConfig(
            enabled=arp_discovery["enabled"],
            interval_seconds=arp_discovery["interval_seconds"],
            exclude_interfaces=tuple(arp_discovery["exclude_interfaces"]),
        ),
        home_assistant_discovery=HomeAssistantDiscoveryConfig(
            enabled=home_assistant_discovery["enabled"],
            include_zeroconf=home_assistant_discovery["include_zeroconf"],
        ),
        webui=WebUIConfig(
            log_lines=webui["log_lines"],
            humanize_datetime=webui["humanize_datetime"],
        ),
        log_level=raw["log_level"],
    )


def load_config() -> Config:
    return parse_config(json.loads(OPTIONS_PATH.read_text(encoding="utf-8")))
