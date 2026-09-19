import asyncio
import logging

from pathlib import Path

from .api import RestAPI
from .const import DNSMASQ_CONFIG_PATH

LOGGER = logging.getLogger(__name__)


class DNSRouting:
    def __init__(self):
        self.rest_api = RestAPI()

        self.app_ip = None
        self.upstreams = []
        self.routes = {}
        self.servers = None

        self._process = None
        self._log_task = None
        self._apply_lock = asyncio.Lock()

    def _get_upstreams(self, dns_info):
        servers = dns_info.get("servers", [])
        locals_ = dns_info.get("locals", [])

        values = servers or [item for item in locals_ if item != f"dns://{self.app_ip}"]

        return [host[6:] for host in values if host.startswith("dns://")]

    def _get_dnsmasq_config(self):
        lines = [
            f"listen-address={self.app_ip}",
            "bind-interfaces",
            "no-resolv",
            "log-queries=extra",
            "log-facility=-",
        ]

        for upstream in self.upstreams:
            lines.append(f"server={upstream}")

        for hostname, ip in self.routes.items():
            lines.append(f"address=/{hostname}/{ip}")

        return "\n".join(lines) + "\n"

    async def _write_config(self):
        config = self._get_dnsmasq_config()

        await asyncio.to_thread(
            DNSMASQ_CONFIG_PATH.write_text,
            config,
            encoding="utf-8",
        )

    async def _set_ha_servers(self, servers):
        LOGGER.debug(
            "Setting servers to: %s",
            str(servers),
        )

        await self.rest_api.post(
            "/dns/options",
            json={
                "servers": servers,
            },
        )

        return True

    async def _start_dnsmasq(self):
        if self._process is not None:
            return

        LOGGER.info("Starting dnsmasq")

        self._process = await asyncio.create_subprocess_exec(
            "dnsmasq",
            "--keep-in-foreground",
            f"--conf-file={DNSMASQ_CONFIG_PATH}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        self._log_task = asyncio.create_task(self._read_dnsmasq_logs())

        # Give dnsmasq a chance to fail immediately.
        await asyncio.sleep(0.1)

        if self._process.returncode is not None:
            raise RuntimeError(f"dnsmasq exited with code {self._process.returncode}")

    async def _stop_dnsmasq(self):
        process = self._process

        if process is None:
            return

        self._process = None

        if process.returncode is None:
            LOGGER.info("Stopping dnsmasq")

            process.terminate()

            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=5,
                )

            except asyncio.TimeoutError:
                LOGGER.warning("dnsmasq did not stop gracefully, killing it")

                process.kill()
                await process.wait()

        if self._log_task is not None:
            await self._log_task
            self._log_task = None

    async def _restart_dnsmasq(self):
        await self._stop_dnsmasq()
        await self._start_dnsmasq()

    async def _read_dnsmasq_logs(self):
        process = self._process

        if process is None or process.stdout is None:
            return

        while line := await process.stdout.readline():
            LOGGER.debug(
                "dnsmasq: %s",
                line.decode().rstrip(),
            )

    async def start(self):
        app_info = await self.rest_api.get("/addons/self/info")

        self.app_ip = app_info["ip_address"]

        dns_info = await self.rest_api.get("/dns/info")

        self.upstreams = self._get_upstreams(dns_info)

        await self._write_config()
        await self._start_dnsmasq()

        current = [
            server
            for server in dns_info.get("servers", [])
            if server != f"dns://{self.app_ip}"
        ]

        self.servers = current

        await self._set_ha_servers(
            [
                f"dns://{self.app_ip}",
                *current,
            ]
        )

        LOGGER.debug("DNS Routing started")

    async def stop(self):
        if self.servers is not None:
            await self._set_ha_servers(self.servers)

            LOGGER.info(
                "Restored servers: %s",
                str(self.servers),
            )

            self.servers = None

        await self.rest_api.close()
        await self._stop_dnsmasq()

        LOGGER.debug("DNS Routing stopped")

    async def set_route(self, hostname, ip):
        if self.routes.get(hostname) == ip:
            return

        self.routes[hostname] = ip

        await self.apply()

        LOGGER.info(
            "Routing %s to %s",
            hostname,
            ip,
        )

    async def remove_route(self, hostname):
        if hostname not in self.routes:
            return

        del self.routes[hostname]

        await self.apply()

        LOGGER.info(
            "Removed route for %s",
            hostname,
        )

    async def apply(self):
        async with self._apply_lock:
            await self._write_config()
            await self._restart_dnsmasq()
