# Changelog

## Unreleased

### Added

- Device timeout to mark unreachable devices as unknown and remove routes automatically (#3).

### Changed

- Improved DNS routing logging for more consistency and useful diagnostics.
- Normalize MAC address casing for consistentcy.
- Moved hardcoded excluded interface defaults into the configuration.

### Fixed

- Prevent unnecessary route updates for unchanged devices (#1).
- Prevent unreachable devices from remaining marked as known after initial discovery (#3).
- Normalize discovered hostnames to prevent unnecessary update triggers (#4).
- Properly close the REST API when stopping DNS routing to prevent unclosed-session warnings.
- Prevent refresh-button animation race conditions.

## 0.1.0 - 19/09/2026

### Added

- Initial release.
