import asyncio
import logging
import ipaddress
import psutil
import socket

from scapy.all import ARP, Ether, srp
from dataclasses import dataclass
from datetime import datetime, timezone

from .api import WebsocketAPI
from .const import EXCLUDED_INTERFACES

LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    mac: str
    ip: str
    hostname: str | None

    last_updated: datetime
    last_confirmed: datetime


class Discovery:
    def __init__(self, macs, arp_config, home_assistant_config, on_update):
        self.macs = {mac.lower() for mac in macs}
        self.arp_config = arp_config
        self.home_assistant_config = home_assistant_config
        self.on_update = on_update

        self.networks = []
        self.devices = {}
        self.tasks = []

        self.ws_api = WebsocketAPI()

    async def start(self):
        self.networks = self._get_networks()

        LOGGER.debug("Detected networks: %s", self.networks)
        LOGGER.debug("Monitoring MAC addresses: %s", self.macs)

        if self.arp_config.enabled:
            self.tasks.append(asyncio.create_task(self.arp_discovery_loop()))

        if self.home_assistant_config.enabled:
            await self.ws_api.connect()

            self.tasks.append(asyncio.create_task(self.home_assistant_discovery_loop()))

    async def stop(self):
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )

        self.tasks.clear()

        if self.ws_api.ws is not None:
            await self.ws_api.close()

    async def found_device(self, mac, ip, hostname=None):
        mac = mac.lower()

        if mac not in self.macs:
            return

        now = datetime.now(timezone.utc)

        device = self.devices.get(mac)

        if device is None:
            device = DiscoveredDevice(
                mac=mac,
                ip=ip,
                hostname=hostname,
                last_updated=now,
                last_confirmed=now,
            )

            self.devices[mac] = device

            LOGGER.debug(
                "New device: mac=%s ip=%s hostname=%s",
                mac,
                ip,
                hostname,
            )

        else:
            changed = False

            if device.ip != ip:
                LOGGER.debug(
                    "Device %s IP changed: %s -> %s",
                    mac,
                    device.ip,
                    ip,
                )

                device.ip = ip
                changed = True

            if hostname is not None and device.hostname != hostname:
                LOGGER.debug(
                    "Device %s hostname changed: %s -> %s",
                    mac,
                    device.hostname,
                    hostname,
                )

                device.hostname = hostname
                changed = True

            if changed:
                device.last_updated = now

            device.last_confirmed = now

        await self.on_update(device)

    def _get_networks(self):
        networks = set()
        excluded_interfaces = EXCLUDED_INTERFACES | set(
            self.arp_config.exclude_interfaces
        )

        for iface, addrs in psutil.net_if_addrs().items():
            if iface in excluded_interfaces:
                continue

            for addr in addrs:
                if (
                    addr.family.name == "AF_INET"
                    and addr.address != "127.0.0.1"
                    and addr.netmask
                ):
                    network = ipaddress.IPv4Network(
                        f"{addr.address}/{addr.netmask}",
                        strict=False,
                    )

                    networks.add((iface, str(network)))

        return sorted(networks)

    def _arp_scan(self, interface, network):
        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network)

        answered, _ = srp(
            packet,
            iface=interface,
            timeout=2,
            retry=1,
            verbose=False,
            inter=0.01,
        )

        return answered

    def _get_cached_mac(self, ip):
        try:
            with open("/proc/net/arp", encoding="utf-8") as file:
                next(file)

                for line in file:
                    parts = line.split()

                    if len(parts) < 6:
                        continue

                    arp_ip = parts[0]
                    mac = parts[3].lower()

                    if arp_ip == ip and mac != "00:00:00:00:00:00":
                        LOGGER.debug(
                            "ARP cache resolved %s as %s",
                            ip,
                            mac,
                        )

                        return mac

        except OSError:
            LOGGER.exception("Failed to read ARP cache")

        return None

    async def _lookup_ip_for_hostname(self, hostname):
        LOGGER.debug(
            "Looking up IP address for hostname: %s",
            hostname,
        )

        try:
            ip = await asyncio.to_thread(
                socket.gethostbyname,
                hostname,
            )
        except socket.gaierror as err:
            LOGGER.debug(
                "Could not resolve hostname %s to an IP address: %s",
                hostname,
                err,
            )
            return None

        LOGGER.debug(
            "Resolved hostname %s to IP address %s",
            hostname,
            ip,
        )

        return ip

    async def _lookup_mac_for_ip(self, ip):
        LOGGER.debug(
            "Looking up MAC address for IP: %s",
            ip,
        )

        mac = self._get_cached_mac(ip)

        if mac is not None:
            LOGGER.debug(
                "Found MAC address for %s in ARP cache: %s",
                ip,
                mac,
            )
            return mac

        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            LOGGER.debug(
                "Cannot look up MAC address for invalid IP: %s",
                ip,
            )
            return None

        if not isinstance(address, ipaddress.IPv4Address):
            LOGGER.debug(
                "Cannot look up MAC address for non-IPv4 address: %s",
                ip,
            )
            return None

        for iface, network in self.networks:
            if address not in ipaddress.ip_network(network, strict=False):
                continue

            LOGGER.debug(
                "Looking up MAC address for %s using ARP on %s (%s)",
                ip,
                iface,
                network,
            )

            responses = await asyncio.to_thread(
                self._arp_scan,
                iface,
                ip,
            )

            for _, response in responses:
                mac = response.hwsrc.lower()

                LOGGER.debug(
                    "Resolved IP %s to MAC address %s",
                    ip,
                    mac,
                )

                return mac

        LOGGER.debug(
            "Could not find MAC address for IP %s on any local network: %s",
            ip,
            self.networks,
        )

        return None

    async def _lookup_hostname_for_ip(self, ip):
        LOGGER.debug(
            "Looking up hostname for IP: %s",
            ip,
        )

        try:
            hostname, _, _ = await asyncio.to_thread(
                socket.gethostbyaddr,
                ip,
            )
        except (socket.herror, socket.gaierror) as err:
            LOGGER.debug(
                "Could not resolve IP %s to a hostname: %s",
                ip,
                err,
            )
            return None

        hostname = hostname.rstrip(".")

        if hostname == ip:
            LOGGER.debug(
                "Reverse DNS lookup for %s returned the IP itself",
                ip,
            )
            return None

        LOGGER.debug(
            "Resolved IP %s to hostname %s",
            ip,
            hostname,
        )

        return hostname

    async def _handle_arp_device(self, mac, ip):
        hostname = await self._lookup_hostname_for_ip(ip)

        await self.found_device(
            mac,
            ip,
            hostname,
        )

    async def _handle_zeroconf_device(self, ip, name, type):
        LOGGER.debug(
            "Processing Zeroconf device at %s",
            ip,
        )

        mac = await self._lookup_mac_for_ip(ip)

        if mac is None:
            LOGGER.debug(
                "No MAC found for Zeroconf device at %s",
                ip,
            )
            return

        if mac not in self.macs:
            LOGGER.debug(
                "Ignoring Zeroconf device %s at %s, MAC not monitored",
                mac,
                ip,
            )
            return

        service_type = type.rstrip(".")
        device_name = name.rstrip(".").removesuffix(service_type).rstrip(".")

        hostname = await self._lookup_hostname_for_ip(ip) or device_name

        LOGGER.debug(
            "Found monitored Zeroconf device: mac=%s ip=%s hostname=%s",
            mac,
            ip,
            hostname,
        )

        await self.found_device(
            mac,
            ip,
            hostname,
        )

    async def arp_discovery_loop(self):
        LOGGER.debug("Starting ARP discovery loop")

        while True:
            for iface, network in self.networks:
                responses = await asyncio.to_thread(
                    self._arp_scan,
                    iface,
                    network,
                )

                devices = [
                    (
                        response.hwsrc.lower(),
                        response.psrc,
                    )
                    for _, response in responses
                    if response.hwsrc.lower() in self.macs
                ]

                await asyncio.gather(
                    *(self._handle_arp_device(mac, ip) for mac, ip in devices)
                )

            await asyncio.sleep(self.arp_config.interval_seconds)

    async def home_assistant_discovery_loop(self):
        LOGGER.debug("Starting Home Assistant discovery loop")

        networks = [
            ipaddress.ip_network(network, strict=False) for _, network in self.networks
        ]

        async def discovered_dhcp(event):
            LOGGER.debug(
                "DHCP discovery event: %s",
                event,
            )

            for device in event.get("add", []):
                mac = device["mac_address"].lower()
                ip = device["ip_address"]
                hostname = device.get("hostname")

                if mac not in self.macs:
                    continue

                try:
                    address = ipaddress.ip_address(ip)
                except ValueError:
                    continue

                if not any(address in network for network in networks):
                    continue

                if hostname == ip:
                    hostname = None

                LOGGER.debug(
                    "Found monitored DHCP device: mac=%s ip=%s hostname=%s",
                    mac,
                    ip,
                    hostname,
                )

                await self.found_device(
                    mac,
                    ip,
                    hostname,
                )

        async def discovered_zeroconf(event):
            LOGGER.debug(
                "Zeroconf discovery event: %s",
                event,
            )

            devices = set()

            for device in event.get("add", []):
                name = device.get("name")
                type = device.get("type")
                ip_addresses = device.get("ip_addresses", [])

                LOGGER.debug(
                    "Zeroconf device: name=%s type=%s ips=%s properties=%s",
                    name,
                    type,
                    ip_addresses,
                    device.get("properties"),
                )

                for ip in ip_addresses:
                    try:
                        address = ipaddress.ip_address(ip)
                    except ValueError:
                        LOGGER.debug(
                            "Ignoring invalid Zeroconf IP: %s",
                            ip,
                        )
                        continue

                    if not isinstance(address, ipaddress.IPv4Address):
                        continue

                    devices.add((ip, name, type))

            await asyncio.gather(
                *(
                    self._handle_zeroconf_device(ip, name, type)
                    for (ip, name, type) in devices
                )
            )

        subscription_ids = []

        try:
            subscription_ids.append(
                await self.ws_api.subscribe(
                    {
                        "type": "dhcp/subscribe_discovery",
                    },
                    discovered_dhcp,
                )
            )

            LOGGER.debug("Subscribed to DHCP discovery")

            if self.home_assistant_config.include_zeroconf:
                subscription_ids.append(
                    await self.ws_api.subscribe(
                        {
                            "type": "zeroconf/subscribe_discovery",
                        },
                        discovered_zeroconf,
                    )
                )

                LOGGER.debug("Subscribed to Zeroconf discovery")

            await asyncio.Future()

        finally:
            if self.ws_api.ws is not None:
                for subscription_id in subscription_ids:
                    await self.ws_api.unsubscribe(subscription_id)
