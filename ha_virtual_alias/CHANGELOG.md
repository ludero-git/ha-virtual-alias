# Changelog

## Unreleased

### Added

- Device timeout to mark unreachable devices as unknown and remove routes (#3).

### Changed

- Improved DNS routing logging for more consistency and useful diagnostics.

### Fixed

- Prevent unnecessary route updates (#1).
- Unreachable devices never change status after first discovery (#3).
- Normalize discovered hostnames (#4).
- Normalize MAC address casing for consistent device matching.
- Properly close REST API when stopping DNS routing to avoid warnings.
- Prevent animation race time issues for the refresh button by adding a timeout.

## 0.1.0 - 19/09/2026

### Added

- Initial release.
