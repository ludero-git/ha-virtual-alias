import asyncio
import logging

from nftables import Nftables

from .const import NFT_TABLE, NFT_TABLE_FAMILY

LOGGER = logging.getLogger(__name__)


class AsyncNftables:
    def __init__(self):
        self._nft = Nftables()
        self._lock = asyncio.Lock()

    async def cmd(self, command: str):
        async with self._lock:
            return await asyncio.to_thread(
                self._nft.cmd,
                command,
            )


class Firewall:
    def __init__(self, virtual_ips):
        self.virtual_ips = set(virtual_ips)
        self.routes = {}

        self.nft = None

    async def start(self):
        self.nft = AsyncNftables()

        # Remove old table if present.
        await self.nft.cmd(f"delete table {NFT_TABLE_FAMILY} {NFT_TABLE}")

        ruleset = f"""
table {NFT_TABLE_FAMILY} {NFT_TABLE} {{
    map aliases {{
        type ipv4_addr : ipv4_addr;
    }}

    set configured_vips {{
        type ipv4_addr;
    }}

    chain output_nat {{
        type nat hook output priority dstnat; policy accept;
        dnat to ip daddr map @aliases
    }}

    chain output_guard {{
        type filter hook output priority filter; policy accept;
        ip daddr @configured_vips drop
    }}
}}
"""

        await self.nft.cmd(ruleset)

        if self.virtual_ips:
            values = ", ".join(str(ip) for ip in self.virtual_ips)

            await self.nft.cmd(f"""
add element {NFT_TABLE_FAMILY} {NFT_TABLE} configured_vips {{
    {values}
}}
""")

        LOGGER.info("Firewall started")

    async def stop(self):
        if self.nft is None:
            return

        await self.nft.cmd(f"delete table {NFT_TABLE_FAMILY} {NFT_TABLE}")

        self.routes.clear()
        self.nft = None

        LOGGER.info("Firewall stopped")

    async def set_route(self, virtual_ip, ip):
        old_ip = self.routes.get(virtual_ip)

        if old_ip == ip:
            return

        if old_ip is None:
            # First discovery.
            await self.nft.cmd(f"""
add element {NFT_TABLE_FAMILY} {NFT_TABLE} aliases {{
    {virtual_ip} : {ip}
}}
""")

        else:
            # Device moved to another real IP.
            await self.nft.cmd(f"""
delete element {NFT_TABLE_FAMILY} {NFT_TABLE} aliases {{
    {virtual_ip}
}}

add element {NFT_TABLE_FAMILY} {NFT_TABLE} aliases {{
    {virtual_ip} : {ip}
}}
""")

        self.routes[virtual_ip] = ip

        LOGGER.info(
            "Routing %s to %s",
            virtual_ip,
            ip,
        )

    async def remove_route(self, virtual_ip):
        if virtual_ip not in self.routes:
            return

        await self.nft.cmd(f"""
delete element {NFT_TABLE_FAMILY} {NFT_TABLE} aliases {{
    {virtual_ip}
}}
""")

        del self.routes[virtual_ip]

        LOGGER.info(
            "Removed route for %s",
            virtual_ip,
        )
