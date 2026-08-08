# Changelog

All notable changes to Pwnagotchi Car Mode are documented here.

## 6.5.1 - 2026-08-08

- Added Bluetooth PAN/tether protection.
- BLE discovery now pauses while an active `bnep*` interface is detected, keeping Bluetooth tethering prioritized.
- Wi-Fi and optional GPS movement signals continue while BLE sensing is paused.
- Added WebUI setting and explanation for tether protection.
- Set plugin author metadata to `adondada`.

## 6.5.0 - 2026-08-08

- Added Wi-Fi/BLE/GPS sensor-fusion movement scoring.
- Added passive BLE advertiser turnover and RSSI-change sensing.
- Added movement smoothing and separate moving/stationary thresholds for hysteresis.
- Increased default stationary timeout to 60 seconds.
- GPS is now optional and disabled by default.
- Added runtime movement diagnostics to the WebUI.
- Added privacy-minimal boot-local hashing for BLE addresses retained between samples.
- Clarified that one hop-period unit equals 250 ms.

## 6.4.1

- Improved manual channel synchronization between Pwnagotchi and BetterCAP.
- Added WebUI configuration and runtime state display.
