# <img width="50" height="50" align="absmiddle" alt="Logo" src="https://raw.githubusercontent.com/ludero-git/ha-virtual-alias/main/ha_virtual_alias/icon.png" /> HA Virtual Alias

[![Latest Version][version-shield]][repository]
[![Supports aarch64 Architecture][aarch64-shield]][repository]
[![Supports amd64 Architecture][amd64-shield]][repository]

Virtual Alias provides persistent virtual hostnames and IPs for LAN devices whose real IP addresses may change.

Devices are identified by MAC address and automatically rediscovered on local networks.

## Installation

### 1. Open and add the repository

[![Open app][app-badge]][app-open]

**Or manually:**

1. In the Home Assistant App Store, open **Repositories**.
2. Add `https://github.com/ludero-git/ha-virtual-alias`.
3. Refresh the App Store and open **Virtual Alias**.

### 2. Install the app

Click **Install**.

### 3. Configure and start

Configure the app, then click **Start**. Access it through its web interface.

## Technical

### How it works

Virtual Alias uses:

* Dnsmasq for virtual hostname resolution.
* Nftables for virtual IP routing.
* ARP discovery using Scapy.
* DHCP/Zeroconf discovery, fetched from Home Assistant.

When a device is rediscovered at a new IP address, its DNS and routing aliases are updated automatically.

## License

[MIT](./LICENSE)

[repository]: https://github.com/ludero-git/ha-virtual-alias
[app-badge]: https://my.home-assistant.io/badges/supervisor_addon.svg
[app-open]: https://my.home-assistant.io/redirect/supervisor_addon/?addon=ac66eee4_virtual_alias&repository_url=https%3A%2F%2Fgithub.com%2Fludero-git%2Fha-virtual-alias
[version-shield]: https://img.shields.io/github/v/tag/ludero-git/ha-virtual-alias?sort=semver
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
