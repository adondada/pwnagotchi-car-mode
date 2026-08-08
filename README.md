# Pwnagotchi Car Mode

Adaptive movement-aware channel profiles for Pwnagotchi, with optional Wi-Fi/BLE/GPS sensor fusion and a built-in settings WebUI.

> **Use responsibly.** This plugin is intended for networks and radio environments you own or are authorized to test. Follow local law and Pwnagotchi/BetterCAP project guidance.

## Highlights

- Movement-aware `CAR` / `AUTO` behavior instead of a fixed stop timer alone.
- Wi-Fi environment change as the always-available movement signal.
- Optional passive BLE discovery using BlueZ for a second movement signal.
- Optional GPS speed integration when a GPS source is available.
- Bluetooth tether protection: BLE discovery pauses while an active Linux Bluetooth PAN interface such as `bnep0` is carrying a tethered connection.
- WebUI settings with plain-language explanations and recommended ranges.
- Runtime diagnostics for motion state, movement score, Wi-Fi change, BLE change/RSSI, scanner state, and active profile.
- Manual channel profile for systems without GPS.
- Channel-hop UI uses **250 ms units**: `1 = 250 ms`, `2 = 500 ms`, `4 = 1 s`.
- Graceful fallback: if BLE/GPS are unavailable, the remaining sensors continue working.

## Current release

**v6.5.1**

v6.5.1 adds Bluetooth-tether protection on top of the v6.5 sensor-fusion release. With protection enabled (the default), Car Mode checks for active `bnep*` PAN interfaces and pauses BLE discovery while Bluetooth tethering is active; Wi-Fi/GPS movement estimation remains available.

## Requirements

- Pwnagotchi with plugin support (developed around the jayofelony Pwnagotchi 2.9.5.x line).
- Python dependencies already used by Pwnagotchi plus `tomlkit`.
- Optional BLE sensing: BlueZ with `bluetoothctl` available.
- Optional GPS sensing: a Pwnagotchi session/plugin that exposes GPS speed data.

BLE sensing is optional. The plugin continues without it if BlueZ is missing or scanning is paused.

## Installation

Copy `car_mode.py` into your custom plugin directory. A common setup is:

```bash
sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins
sudo cp car_mode.py /usr/local/share/pwnagotchi/custom-plugins/car_mode.py
sudo chmod 644 /usr/local/share/pwnagotchi/custom-plugins/car_mode.py
```

Make sure your Pwnagotchi configuration points at that directory if it does not already:

```toml
main.custom_plugins = "/usr/local/share/pwnagotchi/custom-plugins/"
```

Then add the plugin section to `/etc/pwnagotchi/config.toml`:

```toml
[main.plugins.car_mode]
enabled = true
hop_period = 1
channels = "1,6,11"

gps_mode_enabled = false

sensor_fusion_enabled = true
wifi_movement_weight = 0.60
ble_movement_enabled = true
ble_skip_if_pan_active = true
ble_movement_weight = 0.40
ble_scan_interval = 10.0
ble_scan_duration = 2
ble_min_rssi = -90
ble_min_devices = 3
ble_rssi_delta_full_scale = 18.0
movement_smoothing = 0.35
moving_threshold = 0.45
stationary_threshold = 0.15
stationary_timeout = 60.0
environment_similarity = 0.80
```

Restart Pwnagotchi:

```bash
sudo systemctl restart pwnagotchi
```

Open the plugin page from the Pwnagotchi WebUI under the plugins section to tune settings.

## Recommended starting settings (no GPS)

For a Pi using Wi-Fi + onboard Bluetooth but no GPS adapter, start with the defaults:

| Setting | Start with | What it changes |
|---|---:|---|
| `hop_period` | `1` | 250 ms hopper period. Smaller is not supported by this plugin; faster is not automatically better because dwell time matters. |
| `channels` | `1,6,11` | Manual Car Mode channel list when GPS mode is off. |
| `sensor_fusion_enabled` | `true` | Combines available movement signals instead of using only Wi-Fi similarity. |
| `wifi_movement_weight` | `0.60` | Higher values make Wi-Fi environment changes matter more. |
| `ble_movement_enabled` | `true` | Adds passive BLE environment changes to movement estimation. |
| `ble_skip_if_pan_active` | `true` | Prioritizes Bluetooth tethering by pausing BLE discovery while a `bnep*` PAN link is active. |
| `ble_movement_weight` | `0.40` | Higher values make BLE turnover/RSSI changes matter more. |
| `ble_scan_interval` | `10` s | Lower reacts sooner but uses the Bluetooth radio more often. |
| `ble_scan_duration` | `2` s | Longer finds more advertisers but keeps Bluetooth scanning active longer. |
| `ble_min_rssi` | `-90` dBm | More negative includes weaker/farther devices; less negative focuses on nearby devices. |
| `ble_min_devices` | `3` | BLE is ignored as a movement signal until the sample is large enough. |
| `movement_smoothing` | `0.35` | Higher reacts faster; lower is steadier. |
| `moving_threshold` | `0.45` | Score at/above this indicates clear movement. |
| `stationary_threshold` | `0.15` | Score at/below this begins the stationary timer. |
| `stationary_timeout` | `60` s | How long the environment must stay clearly stationary before AUTO fallback. |

The gap between `stationary_threshold` and `moving_threshold` is intentional hysteresis: it reduces rapid state flipping when the signal is ambiguous.

## How sensor fusion works

Car Mode does not try to identify people or pair with nearby Bluetooth devices. It watches environmental change:

1. **Wi-Fi:** compares visible AP sets between updates.
2. **BLE:** compares short-lived, boot-salted hashes of nearby BLE addresses, population change, and RSSI movement.
3. **GPS (optional):** converts reported speed into a movement contribution.
4. Available inputs are weighted and normalized into a movement score.
5. The score is smoothed before state changes are made.

BLE addresses are hashed with a random per-boot salt before snapshots are retained. Device names and advertising payload histories are not needed for the movement estimate.

## Bluetooth tether protection

The default `ble_skip_if_pan_active = true` is designed for setups that manage the Pwnagotchi through Bluetooth tethering/PAN. Before starting a BLE discovery sample, the plugin checks local `/sys/class/net` entries named `bnep*`. If one reports an active link/carrier, BLE scanning is skipped and the WebUI scanner status reports that tethering is being prioritized.

This does **not** disconnect, reconfigure, pair, or unpair Bluetooth devices. While BLE sensing is paused, Wi-Fi and optional GPS remain available to the movement estimator.

If your tethering is USB or Wi-Fi instead, this guard normally never activates.

## WebUI guide

The WebUI is intentionally descriptive rather than exposing unexplained numbers. In general:

- Raise a sensor **weight** to make that sensor matter more relative to others.
- Increase **scan interval** to reduce how often BLE is used; decrease it for quicker BLE updates.
- Increase **scan duration** to see more BLE advertisers per sample.
- Make **minimum RSSI** less negative (for example `-75`) to focus on closer devices.
- Raise **minimum BLE devices** if small BLE samples cause noisy results.
- Raise **movement smoothing** toward `1.0` for faster response; lower it for stability.
- Raise **moving threshold** to require stronger movement evidence.
- Lower **stationary threshold** to require stronger stationary evidence.
- Raise **stationary timeout** if traffic lights or brief stops are being mistaken for parking.

Change one or two parameters at a time and use the runtime diagnostics to see what actually changes.

## GPS

GPS is **off by default**. Enable it only when your Pwnagotchi session exposes valid speed data. GPS can select separate fast/slow channel profiles and also contribute to the sensor-fusion movement score.

## Release asset

Every release attaches the matching `car_mode.py` so it can be installed directly without cloning the repository.

## Development

The release workflow syntax-checks the plugin before publishing. The plugin version is read from `CarMode.__version__`, and the workflow creates the matching `vX.Y.Z` GitHub release if it does not already exist.

## License

MIT — see [LICENSE](LICENSE).
