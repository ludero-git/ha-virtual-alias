import logging
import asyncio
from datetime import datetime
from dataclasses import asdict, dataclass

from .config import load_config
from .discovery import Discovery
from .dns_routing import DNSRouting
from .firewall import Firewall
from .web import Web

LOGGER = logging.getLogger(__name__)


def humanize_datetime(value):
    seconds = int((datetime.now() - value).total_seconds())

    if seconds < 60:
        return "just now"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

    hours = minutes // 60

    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    days = hours // 24

    return f"{days} day{'s' if days != 1 else ''} ago"


@dataclass
class DeviceState:
    friendly_name: str
    mac: str
    virtual_ip: str | None
    virtual_hostname: str | None
    status: str = "unknown"
    hostname: str | None = None
    ip: str | None = None
    last_updated: datetime | None = None
    last_confirmed: datetime | None = None


class App:
    def __init__(self, config):
        self.config = config

        self.aliases = {alias.mac.lower(): alias for alias in config.aliases}

        self.devices = {
            mac: DeviceState(
                friendly_name=alias.friendly_name,
                mac=alias.mac.lower(),
                virtual_ip=str(alias.virtual_ip) if alias.virtual_ip else None,
                virtual_hostname=alias.virtual_hostname,
            )
            for mac, alias in self.aliases.items()
        }

        self.tasks = []

        self.dns = DNSRouting()

        self.firewall = Firewall(
            virtual_ips={
                alias.virtual_ip for alias in config.aliases if alias.virtual_ip
            }
        )

        self.discovery = Discovery(
            macs=set(self.aliases),
            arp_config=config.arp_discovery,
            home_assistant_config=config.home_assistant_discovery,
            on_update=self.device_changed,
        )

        self.web = Web(
            app=self,
            web_config=config.webui,
        )

    async def start(self):
        LOGGER.info("Starting")

        if any(alias.virtual_hostname for alias in self.aliases.values()):
            await self.dns.start()

        if any(alias.virtual_ip for alias in self.aliases.values()):
            await self.firewall.start()

        await self.discovery.start()
        await self.web.start()

        self.tasks.append(asyncio.create_task(self.device_timeout_loop()))

        LOGGER.info("Started")

    async def stop(self):
        LOGGER.info("Stopping")

        for task in self.tasks:
            task.cancel()

            await asyncio.gather(
                *self.tasks,
                return_exceptions=True,
            )

        await self.web.stop()
        await self.discovery.stop()
        await self.firewall.stop()
        await self.dns.stop()

        LOGGER.info("Stopped")

    async def device_timeout_loop(self):
        while True:
            now = datetime.now()

            for mac, state in self.devices.items():
                if state.status != "known" or state.last_confirmed is None:
                    continue

                seconds = (now - state.last_confirmed).total_seconds()

                if seconds < self.config.timeout_seconds:
                    continue

                alias = self.aliases[mac]

                LOGGER.info(
                    "Device no longer confirmed: %s",
                    mac,
                )

                state.status = "unknown"
                state.ip = None
                state.hostname = None

                if alias.virtual_hostname:
                    await self.dns.remove_route(alias.virtual_hostname)

                if alias.virtual_ip:
                    await self.firewall.remove_route(alias.virtual_ip)

            await asyncio.sleep(5)

    def get_devices(self):
        devices = []

        for device in self.devices.values():
            data = asdict(device)

            if device.last_updated:
                data["last_updated"] = (
                    humanize_datetime(device.last_updated)
                    if self.config.webui.humanize_datetime
                    else device.last_updated.strftime("%Y-%m-%d %H:%M:%S")
                )

            if device.last_confirmed:
                data["last_confirmed"] = (
                    humanize_datetime(device.last_confirmed)
                    if self.config.webui.humanize_datetime
                    else device.last_confirmed.strftime("%Y-%m-%d %H:%M:%S")
                )

            devices.append(data)

        return devices

    async def device_changed(self, device):
        mac = device.mac.lower()
        alias = self.aliases.get(mac)

        if not alias:
            return

        state = self.devices[mac]
        now = datetime.now()

        changed = state.ip != device.ip or state.hostname != device.hostname

        state.status = "known"
        state.hostname = device.hostname
        state.ip = device.ip
        state.last_confirmed = now

        if not changed:
            LOGGER.debug(
                "Device confirmed unchanged: %s -> %s (%s)",
                device.mac,
                device.ip,
                device.hostname,
            )
            return

        state.last_updated = now

        LOGGER.info(
            "Device changed: %s -> %s (%s)",
            device.mac,
            device.ip,
            device.hostname,
        )

        if alias.virtual_hostname:
            await self.dns.set_route(
                alias.virtual_hostname,
                device.ip,
            )

        if alias.virtual_ip:
            await self.firewall.set_route(
                alias.virtual_ip,
                device.ip,
            )


def create_app():
    config = load_config()

    logging.basicConfig(
        level=getattr(
            logging,
            config.log_level.upper(),
        ),
        format=("%(asctime)s %(levelname)s " "%(name)s: %(message)s"),
    )

    return App(config)
