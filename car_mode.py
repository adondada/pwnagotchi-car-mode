import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import _thread

import tomlkit

import pwnagotchi.plugins as plugins
from pwnagotchi import restart
from pwnagotchi.utils import save_config
from flask import abort, render_template_string


WEB_TEMPLATE = r"""
{% extends "base.html" %}
{% set active_page = "plugins" %}

{% block title %}Car Mode Settings{% endblock %}

{% block meta %}
{{ super() }}
<meta name="viewport" content="width=device-width, initial-scale=1">
{% endblock %}

{% block styles %}
{{ super() }}
<style>
.car-wrap { max-width: 980px; margin: 0 auto; padding: 14px; }
.car-card { border: 1px solid #d8d8d8; border-radius: 10px; padding: 16px; margin-bottom: 14px; background: #fff; }
.car-card h2 { margin-top: 0; }
.car-card h3 { margin-bottom: 8px; }
.car-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.car-field label { font-weight: 700; display: block; margin-bottom: 5px; }
.car-field input, .car-field select { width: 100%; padding: 9px; box-sizing: border-box; border: 1px solid #bbb; border-radius: 6px; }
.car-help { font-size: 0.85rem; opacity: 0.78; margin-top: 5px; line-height: 1.35; }
.car-note { padding: 10px 12px; border-radius: 7px; margin: 10px 0 14px; background: #f3f6f9; line-height: 1.4; }
.car-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.car-btn { display: inline-block; padding: 10px 15px; border: 0; border-radius: 7px; cursor: pointer; text-decoration: none; }
.car-save { background: #0061b0; color: #fff; }
.car-secondary { background: #e7e7e7; color: #111; }
.car-status { padding: 10px; border-radius: 7px; margin-bottom: 14px; background: #efefef; }
.car-ok { background: #dff5e5; }
.car-error { background: #f8dddd; }
.car-meter { font-variant-numeric: tabular-nums; }
.car-muted { opacity: 0.7; }
</style>
{% endblock %}

{% block content %}
<div class="car-wrap">
    <h1>🚗 Car Mode</h1>
    <p>Configure Car Mode, movement sensing, GPS and Bluetooth without editing config.toml manually.</p>

    {% if message %}
    <div class="car-status {{ 'car-ok' if success else 'car-error' }}">{{ message }}</div>
    {% endif %}

    <form method="POST" action="/plugins/car_mode/save">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <div class="car-card">
            <h2>General</h2>
            <div class="car-grid">
                <div class="car-field">
                    <label>Plugin enabled</label>
                    <select name="enabled">
                        <option value="true" {{ 'selected' if cfg.enabled else '' }}>Enabled</option>
                        <option value="false" {{ 'selected' if not cfg.enabled else '' }}>Disabled</option>
                    </select>
                    <div class="car-help">Disabling takes effect after restart.</div>
                </div>

                <div class="car-field">
                    <label>Manual channels</label>
                    <input name="channels" value="{{ cfg.channels }}">
                    <div class="car-help">Channels used when GPS mode is off. Example: 1,6,11.</div>
                </div>

                <div class="car-field">
                    <label>Hop period (250 ms units)</label>
                    <input id="hop_period" type="number" min="1" step="1" name="hop_period" value="{{ cfg.hop_period }}">
                    <div class="car-help"><strong>1 = 250 ms</strong>, 2 = 500 ms, 4 = 1 second. Lower means less dwell time per channel; lower is not always better. Current effective value: <span id="hop_effective"></span>.</div>
                </div>
            </div>
        </div>

        <div class="car-card">
            <h2>Movement sensor fusion</h2>
            <div class="car-note">
                Car Mode estimates movement from changes in nearby Wi-Fi APs and, optionally, passive Bluetooth LE advertisements. GPS can join the estimate when enabled. No Bluetooth pairing or connections are performed, and device names/addresses are not stored.
            </div>
            <div class="car-grid">
                <div class="car-field">
                    <label>Sensor fusion</label>
                    <select name="sensor_fusion_enabled">
                        <option value="true" {{ 'selected' if cfg.sensor_fusion_enabled else '' }}>Enabled (recommended)</option>
                        <option value="false" {{ 'selected' if not cfg.sensor_fusion_enabled else '' }}>Legacy Wi-Fi-only stop detection</option>
                    </select>
                    <div class="car-help">Enabled uses a smoothed 0–100% movement score. Disabled restores the old similarity-only logic.</div>
                </div>

                <div class="car-field">
                    <label>Wi-Fi influence</label>
                    <input type="number" min="0" max="5" step="0.05" name="wifi_movement_weight" value="{{ cfg.wifi_movement_weight }}">
                    <div class="car-help">Higher = changes in visible APs matter more. Weights are automatically normalized, so they do not need to add to 1.</div>
                </div>

                <div class="car-field">
                    <label>Bluetooth movement sensing</label>
                    <select name="ble_movement_enabled">
                        <option value="true" {{ 'selected' if cfg.ble_movement_enabled else '' }}>Enabled</option>
                        <option value="false" {{ 'selected' if not cfg.ble_movement_enabled else '' }}>Disabled</option>
                    </select>
                    <div class="car-help">Uses passive BLE discovery as an extra movement signal. If BlueZ/bluetoothctl is unavailable, Car Mode automatically continues without it.</div>
                </div>

                <div class="car-field">
                    <label>Protect Bluetooth tethering</label>
                    <select name="ble_skip_if_pan_active">
                        <option value="true" {{ 'selected' if cfg.ble_skip_if_pan_active else '' }}>Enabled (recommended)</option>
                        <option value="false" {{ 'selected' if not cfg.ble_skip_if_pan_active else '' }}>Disabled</option>
                    </select>
                    <div class="car-help">If a Bluetooth PAN/tether interface (bnep*) is active, Car Mode pauses BLE discovery and keeps using Wi-Fi/GPS movement signals. This avoids competing with Bluetooth tethering.</div>
                </div>

                <div class="car-field">
                    <label>Bluetooth influence</label>
                    <input type="number" min="0" max="5" step="0.05" name="ble_movement_weight" value="{{ cfg.ble_movement_weight }}">
                    <div class="car-help">Higher = BLE device turnover and RSSI changes matter more. Set 0 to ignore BLE while still allowing the scanner for diagnostics.</div>
                </div>

                <div class="car-field">
                    <label>BLE scan interval (seconds)</label>
                    <input type="number" min="2" max="120" step="1" name="ble_scan_interval" value="{{ cfg.ble_scan_interval }}">
                    <div class="car-help">How often a BLE sample starts. Lower reacts faster but uses Bluetooth more often. Recommended: 8–15 s.</div>
                </div>

                <div class="car-field">
                    <label>BLE scan duration (seconds)</label>
                    <input type="number" min="1" max="15" step="1" name="ble_scan_duration" value="{{ cfg.ble_scan_duration }}">
                    <div class="car-help">Longer scans see more advertisers but keep the shared 2.4 GHz radio busier. Recommended: 2–4 s.</div>
                </div>

                <div class="car-field">
                    <label>BLE minimum RSSI (dBm)</label>
                    <input type="number" min="-110" max="-20" step="1" name="ble_min_rssi" value="{{ cfg.ble_min_rssi }}">
                    <div class="car-help">Ignores very weak BLE signals. -90 is balanced; -100 sees farther/noisier devices; -75 focuses on nearby devices.</div>
                </div>

                <div class="car-field">
                    <label>Minimum BLE devices</label>
                    <input type="number" min="1" max="30" step="1" name="ble_min_devices" value="{{ cfg.ble_min_devices }}">
                    <div class="car-help">BLE is trusted only when both consecutive scans contain at least this many devices. Higher reduces false movement in sparse/noisy scans.</div>
                </div>

                <div class="car-field">
                    <label>RSSI full-movement delta (dB)</label>
                    <input type="number" min="2" max="50" step="1" name="ble_rssi_delta_full_scale" value="{{ cfg.ble_rssi_delta_full_scale }}">
                    <div class="car-help">Average RSSI change that counts as a 100% RSSI movement signal. Lower makes RSSI changes more sensitive; higher makes them less sensitive.</div>
                </div>

                <div class="car-field">
                    <label>Movement smoothing</label>
                    <input type="number" min="0.05" max="1" step="0.05" name="movement_smoothing" value="{{ cfg.movement_smoothing }}">
                    <div class="car-help">0.05 = very stable/slow response. 1.0 = no smoothing/instant response. Recommended: 0.25–0.45.</div>
                </div>

                <div class="car-field">
                    <label>Moving threshold</label>
                    <input type="number" min="0" max="1" step="0.01" name="moving_threshold" value="{{ cfg.moving_threshold }}">
                    <div class="car-help">Movement score above this immediately keeps/returns to Car Mode. 0.45 means 45%.</div>
                </div>

                <div class="car-field">
                    <label>Stationary threshold</label>
                    <input type="number" min="0" max="1" step="0.01" name="stationary_threshold" value="{{ cfg.stationary_threshold }}">
                    <div class="car-help">Score below this starts the stationary timer. The gap between this and Moving threshold prevents mode-flapping.</div>
                </div>

                <div class="car-field">
                    <label>Stationary timeout (seconds)</label>
                    <input type="number" min="5" max="1800" step="1" name="stationary_timeout" value="{{ cfg.stationary_timeout }}">
                    <div class="car-help">How long the score must remain clearly stationary before normal AUTO fallback. 60 s is safer for traffic lights than 30 s.</div>
                </div>

                <div class="car-field">
                    <label>Legacy environment similarity</label>
                    <input type="number" min="0" max="1" step="0.01" name="environment_similarity" value="{{ cfg.environment_similarity }}">
                    <div class="car-help">Used only when Sensor fusion is disabled. 0.80 means consecutive Wi-Fi environments ~80% similar count as stationary.</div>
                </div>
            </div>
        </div>

        <div class="car-card">
            <h2>GPS</h2>
            <div class="car-grid">
                <div class="car-field">
                    <label>GPS mode</label>
                    <select name="gps_mode_enabled">
                        <option value="true" {{ 'selected' if cfg.gps_mode_enabled else '' }}>Enabled</option>
                        <option value="false" {{ 'selected' if not cfg.gps_mode_enabled else '' }}>Disabled</option>
                    </select>
                    <div class="car-help">Leave disabled if you do not have GPS data. Sensor fusion works without GPS.</div>
                </div>

                <div class="car-field">
                    <label>GPS movement influence</label>
                    <input type="number" min="0" max="5" step="0.05" name="gps_movement_weight" value="{{ cfg.gps_movement_weight }}">
                    <div class="car-help">Used only when GPS mode is enabled and valid speed exists. Higher makes GPS speed dominate the movement estimate.</div>
                </div>

                <div class="car-field">
                    <label>Fast-mode threshold (km/h)</label>
                    <input type="number" min="0.1" step="0.1" name="gps_speed_threshold" value="{{ cfg.gps_speed_threshold }}">
                    <div class="car-help">At or above this speed, GPS uses the fast channel profile. It also scales the GPS movement score.</div>
                </div>

                <div class="car-field">
                    <label>GPS value is m/s</label>
                    <select name="gps_speed_is_mps">
                        <option value="true" {{ 'selected' if cfg.gps_speed_is_mps else '' }}>Yes</option>
                        <option value="false" {{ 'selected' if not cfg.gps_speed_is_mps else '' }}>No</option>
                    </select>
                    <div class="car-help">Enable only if your GPS plugin reports meters/second instead of km/h.</div>
                </div>

                <div class="car-field"><label>Fast channels</label><input name="gps_fast_channels" value="{{ cfg.gps_fast_channels }}"></div>
                <div class="car-field"><label>Slow channels</label><input name="gps_slow_channels" value="{{ cfg.gps_slow_channels }}"></div>
            </div>
        </div>

        <div class="car-card">
            <h2>Current runtime state</h2>
            <div class="car-grid car-meter">
                <div><strong>Recon profile:</strong> {{ runtime.mode_state }}</div>
                <div><strong>Motion state:</strong> {{ runtime.motion_state }}</div>
                <div><strong>Movement score:</strong> {{ runtime.movement_score }}</div>
                <div><strong>Wi-Fi change:</strong> {{ runtime.wifi_change }}</div>
                <div><strong>BLE change:</strong> {{ runtime.ble_change }}</div>
                <div><strong>BLE RSSI movement:</strong> {{ runtime.ble_rssi }}</div>
                <div><strong>BLE devices:</strong> {{ runtime.ble_devices }}</div>
                <div><strong>BLE scanner:</strong> {{ runtime.ble_status }}</div>
                <div><strong>AUTO fallback:</strong> {{ runtime.forced_auto_mode }}</div>
                <div><strong>Plugin ready:</strong> {{ runtime.ready }}</div>
            </div>
            <div class="car-help">Runtime values refresh when the page is reloaded. BLE identifiers stay in memory only as short salted hashes; names and advertisement payloads are not retained.</div>
        </div>

        <div class="car-actions">
            <button class="car-btn car-save" type="submit" name="restart" value="yes">Save & Restart</button>
            <button class="car-btn car-secondary" type="submit" name="restart" value="no">Save Only</button>
        </div>
    </form>
</div>
<script>
(function () {
    const input = document.getElementById('hop_period');
    const out = document.getElementById('hop_effective');
    function updateHop() {
        const units = Math.max(1, parseInt(input.value || '1', 10));
        const ms = units * 250;
        out.textContent = ms >= 1000 ? (ms / 1000).toFixed(ms % 1000 ? 2 : 0) + ' s' : ms + ' ms';
    }
    input.addEventListener('input', updateHop);
    updateHop();
})();
</script>
{% endblock %}
"""


class CarMode(plugins.Plugin):
    __author__ = "adondada"
    __version__ = "6.5.1"
    __description__ = (
        "Dynamic Car Mode with Wi-Fi/BLE/GPS movement sensor fusion, "
        "AUTO fallback, LED feedback, and a WebUI settings page."
    )

    CONFIG_PATH = "/etc/pwnagotchi/config.toml"

    DEFAULTS = {
        "enabled": True,
        "hop_period": 1,
        "channels": "1,6,11",
        "gps_mode_enabled": False,
        "gps_speed_threshold": 20.0,
        "gps_fast_channels": "1,6,11",
        "gps_slow_channels": "1,2,3,4,5,6,7,8,9,10,11,12,13,14",
        "gps_speed_is_mps": False,
        "gps_movement_weight": 0.80,
        "sensor_fusion_enabled": True,
        "wifi_movement_weight": 0.60,
        "ble_movement_enabled": True,
        "ble_skip_if_pan_active": True,
        "ble_movement_weight": 0.40,
        "ble_scan_interval": 10.0,
        "ble_scan_duration": 2,
        "ble_min_rssi": -90,
        "ble_min_devices": 3,
        "ble_rssi_delta_full_scale": 18.0,
        "movement_smoothing": 0.35,
        "moving_threshold": 0.45,
        "stationary_threshold": 0.15,
        "stationary_timeout": 60.0,
        "environment_similarity": 0.80,
    }

    def __init__(self):
        self.ready = False
        self.mode = "AUTO"
        self._agent = None
        self._original_personality_channels = None
        self._applied_profile = None

        if os.path.exists("/sys/class/leds/ACT"):
            self.led_path = "/sys/class/leds/ACT"
        else:
            self.led_path = "/sys/class/leds/led0"

        self.last_ap_set = set()
        self.stationary_since = None
        self.forced_auto_mode = False
        self.mode_state = None
        self.last_status = None

        self.hop_period = 1
        self.channels = "1,6,11"
        self.gps_mode_enabled = False
        self.gps_speed_threshold = 20.0
        self.gps_fast_channels = "1,6,11"
        self.gps_slow_channels = "1,2,3,4,5,6,7,8,9,10,11,12,13,14"
        self.gps_speed_is_mps = False
        self.gps_movement_weight = 0.80

        self.sensor_fusion_enabled = True
        self.wifi_movement_weight = 0.60
        self.ble_movement_enabled = True
        self.ble_skip_if_pan_active = True
        self.ble_movement_weight = 0.40
        self.ble_scan_interval = 10.0
        self.ble_scan_duration = 2
        self.ble_min_rssi = -90
        self.ble_min_devices = 3
        self.ble_rssi_delta_full_scale = 18.0
        self.movement_smoothing = 0.35
        self.moving_threshold = 0.45
        self.stationary_threshold = 0.15
        self.stationary_timeout = 60.0
        self.environment_similarity = 0.80

        self.motion_state = "UNKNOWN"
        self.movement_score = None
        self.wifi_change_score = None
        self.ble_change_score = None
        self.ble_turnover_score = None
        self.ble_rssi_score = None
        self.ble_device_count = 0
        self.ble_scanner_status = "Not started"
        self.ble_last_scan_at = 0.0
        self._ble_snapshot = {}
        self._ble_lock = threading.Lock()
        self._ble_stop = threading.Event()
        self._ble_thread = None
        self._ble_hash_salt = os.urandom(16)

    def on_loaded(self):
        logging.info("[Car-Mode] Version %s loaded.", self.__version__)
        self.ready = True

    def on_ready(self, agent):
        self._agent = agent

        try:
            self._original_personality_channels = list(
                agent._config.get("personality", {}).get("channels", []) or []
            )
        except Exception:
            self._original_personality_channels = []

        self.mode = "MANU" if getattr(agent, "mode", "auto") == "manual" else "AUTO"
        self._load_runtime_options()
        self._start_ble_scanner()

        self.forced_auto_mode = False
        self.stationary_since = None
        self.mode_state = None
        self.last_status = None
        self.last_ap_set = set()

        if self.gps_mode_enabled:
            self._set_profile(
                agent,
                state="CAR_FAST",
                hop_period=self.hop_period,
                channels=self.gps_fast_channels,
            )
        else:
            self._set_profile(
                agent,
                state="CAR_MANUAL",
                hop_period=self.hop_period,
                channels=self.channels,
            )

        view = agent.view()
        if self.gps_mode_enabled:
            self._set_status(view, "CAR", "(CAR) Car Mode Active")
        else:
            self._set_status(view, "CAR", "(CAR) Manual Car Mode")

        logging.info(
            "[Car-Mode] Ready. GPS=%s BLE=%s fusion=%s threshold=%.1f stationary_timeout=%.1fs",
            self.gps_mode_enabled,
            self.ble_movement_enabled,
            self.sensor_fusion_enabled,
            self.gps_speed_threshold,
            self.stationary_timeout,
        )

    def on_unload(self, agent):
        self._ble_stop.set()
        logging.info("[Car-Mode] Deactivated. Restoring recon defaults...")

        try:
            if self._original_personality_channels is not None:
                agent._config["personality"]["channels"] = list(
                    self._original_personality_channels
                )
                logging.info(
                    "[Car-Mode] Restored core personality.channels -> %s",
                    self._original_personality_channels or "ALL",
                )
        except Exception as exc:
            logging.error(
                "[Car-Mode] Failed restoring core personality channels: %s",
                exc,
            )

        try:
            agent.run("set wifi.hop.period 250")
            agent.run("wifi.recon.channel clear")
            agent.run("wifi.recon off")
            agent.run("wifi.recon on")
        except Exception as exc:
            logging.error("[Car-Mode] Failed restoring recon defaults: %s", exc)

        try:
            view = agent.view()
            if view:
                view.set("mode", "AUTO")
                view.set("status", "(AUTO) Normal mode restored.")
                view.update(force=True)
        except Exception as exc:
            logging.error("[Car-Mode] Failed restoring UI: %s", exc)

        self.mode_state = None
        self._applied_profile = None
        self.forced_auto_mode = False

    def on_wifi_update(self, agent, access_points):
        if not self.ready:
            return

        if access_points is None:
            access_points = []

        now = time.monotonic()
        current_ap_set = {
            ap.get("mac")
            for ap in access_points
            if ap.get("mac")
        }

        wifi_similarity = self._environment_similarity(
            current_ap_set, self.last_ap_set
        )
        if current_ap_set and self.last_ap_set:
            self.wifi_change_score = 1.0 - wifi_similarity
        else:
            self.wifi_change_score = None

        gps_speed_kmh = self._get_gps_speed_kmh(agent) if self.gps_mode_enabled else None
        view = agent.view()

        if self.sensor_fusion_enabled:
            raw_score = self._calculate_movement_score(now, gps_speed_kmh)

            if raw_score is None:
                self.motion_state = "UNKNOWN"
                self.stationary_since = None
            else:
                alpha = min(1.0, max(0.05, self.movement_smoothing))
                if self.movement_score is None:
                    self.movement_score = raw_score
                else:
                    self.movement_score = (
                        alpha * raw_score
                        + (1.0 - alpha) * self.movement_score
                    )

                clear_moving = self.movement_score >= self.moving_threshold
                # When already in AUTO fallback, a single strong fresh change
                # should wake Car Mode immediately instead of being diluted by
                # an old near-zero EMA score.
                if self.forced_auto_mode and raw_score >= self.moving_threshold:
                    clear_moving = True

                if clear_moving:
                    self.motion_state = "MOVING"
                    self.stationary_since = None

                    if self.forced_auto_mode:
                        logging.info(
                            "[Car-Mode] Movement detected (score=%.2f). "
                            "Leaving AUTO fallback.",
                            self.movement_score,
                        )
                        self.forced_auto_mode = False
                        self.mode_state = None
                        self._applied_profile = None

                elif self.movement_score <= self.stationary_threshold:
                    if self.stationary_since is None:
                        self.stationary_since = now
                    self.motion_state = "STILL"
                else:
                    # Hysteresis zone: do not count ambiguous movement as parked.
                    self.motion_state = "HOLD"
                    self.stationary_since = None
        else:
            # v6.4-compatible fallback: consecutive similar Wi-Fi environments
            # start the stationary timer.
            stationary = (
                bool(current_ap_set)
                and bool(self.last_ap_set)
                and wifi_similarity >= self.environment_similarity
            )

            self.movement_score = self.wifi_change_score
            if stationary:
                if self.stationary_since is None:
                    self.stationary_since = now
                self.motion_state = "STILL"
            else:
                self.stationary_since = None
                self.motion_state = "MOVING" if self.last_ap_set else "UNKNOWN"

                if self.forced_auto_mode:
                    logging.info(
                        "[Car-Mode] Wi-Fi environment changed. Leaving AUTO fallback."
                    )
                    self.forced_auto_mode = False
                    self.mode_state = None
                    self._applied_profile = None

        self.last_ap_set = current_ap_set

        # AUTO fallback is entered only after a continuously clear stationary
        # period. Ambiguous HOLD samples reset the timer above.
        if self.stationary_since is not None:
            stationary_duration = now - self.stationary_since
            if stationary_duration >= self.stationary_timeout:
                if not self.forced_auto_mode:
                    logging.info(
                        "[Car-Mode] Stationary for %.1fs. Switching to AUTO fallback.",
                        stationary_duration,
                    )
                    self.forced_auto_mode = True
                    self._set_profile(
                        agent,
                        state="AUTO",
                        hop_period=10,
                        channels="",
                    )

                score_text = self._score_text(self.movement_score)
                self._set_status(
                    view,
                    "AUTO",
                    f"(AUTO) Stationary {score_text}",
                )
                return

        # Once AUTO fallback has been entered, remain there until there is a
        # clear moving signal rather than bouncing back on an ambiguous sample.
        if self.forced_auto_mode:
            score_text = self._score_text(self.movement_score)
            self._set_status(view, "AUTO", f"(AUTO) Waiting for movement {score_text}")
            return

        # Safety net for manual Car Mode. v6.4 accidentally called
        # _sync_core_channels() without the required channels argument here;
        # v6.5 fixes that so the safety check can actually work.
        if not self.gps_mode_enabled:
            try:
                allowed = set(self._parse_channels(self.channels))
                current = int(agent.get_current_channel() or 0)

                if allowed and current not in allowed and current != 0:
                    logging.warning(
                        "[Car-Mode] Core selected disallowed CH %s; "
                        "restoring locked channels %s",
                        current,
                        sorted(allowed),
                    )
                    self._sync_core_channels(agent, self.channels)
                    agent.run(f"wifi.recon.channel {self.channels}")
                    agent._current_channel = 0
            except Exception as exc:
                logging.debug(
                    "[Car-Mode] Channel-lock safety check failed: %s",
                    exc,
                )

        if not self.gps_mode_enabled:
            self._set_profile(
                agent,
                state="CAR_MANUAL",
                hop_period=self.hop_period,
                channels=self.channels,
            )

            score_text = self._score_text(self.movement_score)
            if self.motion_state == "MOVING":
                status = f"(CAR) Moving {score_text}"
            elif self.motion_state == "STILL" and self.stationary_since is not None:
                elapsed = int(now - self.stationary_since)
                status = f"(CAR) Still {elapsed}/{int(self.stationary_timeout)}s {score_text}"
            elif self.motion_state == "HOLD":
                status = f"(CAR) Motion uncertain {score_text}"
            else:
                status = "(CAR) Learning movement..."

            self._set_status(view, "CAR", status)
            return

        if gps_speed_kmh is None:
            self._set_status(view, "CAR", "(GPS) Waiting for GPS; fusion still active")
            return

        if gps_speed_kmh >= self.gps_speed_threshold:
            self._set_profile(
                agent,
                state="CAR_FAST",
                hop_period=self.hop_period,
                channels=self.gps_fast_channels,
            )
            self._set_status(
                view,
                "CAR",
                f"(CAR) GPS Fast: {gps_speed_kmh:.0f}km/h {self._score_text(self.movement_score)}",
            )
        else:
            self._set_profile(
                agent,
                state="CAR_SLOW",
                hop_period=6,
                channels=self.gps_slow_channels,
            )
            self._set_status(
                view,
                "CAR",
                f"(SLOW) {gps_speed_kmh:.0f}km/h {self._score_text(self.movement_score)}",
            )

    def on_handshake(self, agent, filename, access_point):
        if not self.ready:
            return

        try:
            if isinstance(access_point, dict):
                ssid = access_point.get("hostname", "Unknown")
            else:
                ssid = str(access_point)

            view = agent.view()
            self._set_status(view, "CAR", f"CAPTURED: {ssid[:8]}")
            self._blink_led(times=5, speed=0.08)

        except Exception as exc:
            logging.error("[Car-Mode] Handshake handler error: %s", exc)

    def on_ui_update(self, ui):
        if not self.ready:
            return

        try:
            ui.set("mode", "AUTO" if self.forced_auto_mode else "CAR")
        except Exception as exc:
            logging.debug("[Car-Mode] UI update error: %s", exc)

    def on_webhook(self, path, request):
        if not self.ready:
            return "Car Mode plugin not ready", 503

        path = (path or "").strip("/")

        if request.method == "GET":
            if path in ("", "/"):
                return self._render_web()
            abort(404)

        if request.method == "POST":
            if path == "save":
                return self._handle_web_save(request)
            abort(404)

        abort(405)

    def _render_web(self, message=None, success=True):
        cfg = self._read_plugin_config()
        runtime = {
            "mode_state": self.mode_state or "Not initialized",
            "motion_state": self.motion_state,
            "movement_score": self._score_text(self.movement_score),
            "wifi_change": self._score_text(self.wifi_change_score),
            "ble_change": self._score_text(self.ble_change_score),
            "ble_rssi": self._score_text(self.ble_rssi_score),
            "ble_devices": self.ble_device_count,
            "ble_status": self.ble_scanner_status,
            "forced_auto_mode": "Yes" if self.forced_auto_mode else "No",
            "ready": "Yes" if self.ready else "No",
        }

        return render_template_string(
            WEB_TEMPLATE,
            cfg=cfg,
            runtime=runtime,
            message=message,
            success=success,
        )

    def _handle_web_save(self, request):
        try:
            new_values = {
                "enabled": self._form_bool(request.form.get("enabled")),
                "hop_period": self._safe_int(
                    request.form.get("hop_period"), 1, minimum=1, maximum=100
                ),
                "channels": self._clean_channels(
                    request.form.get("channels", "1,6,11")
                ),
                "sensor_fusion_enabled": self._form_bool(
                    request.form.get("sensor_fusion_enabled")
                ),
                "wifi_movement_weight": self._safe_float(
                    request.form.get("wifi_movement_weight"), 0.60, minimum=0.0, maximum=5.0
                ),
                "ble_movement_enabled": self._form_bool(
                    request.form.get("ble_movement_enabled")
                ),
                "ble_skip_if_pan_active": self._form_bool(
                    request.form.get("ble_skip_if_pan_active")
                ),
                "ble_movement_weight": self._safe_float(
                    request.form.get("ble_movement_weight"), 0.40, minimum=0.0, maximum=5.0
                ),
                "ble_scan_interval": self._safe_float(
                    request.form.get("ble_scan_interval"), 10.0, minimum=2.0, maximum=120.0
                ),
                "ble_scan_duration": self._safe_int(
                    request.form.get("ble_scan_duration"), 2, minimum=1, maximum=15
                ),
                "ble_min_rssi": self._safe_int(
                    request.form.get("ble_min_rssi"), -90, minimum=-110, maximum=-20
                ),
                "ble_min_devices": self._safe_int(
                    request.form.get("ble_min_devices"), 3, minimum=1, maximum=30
                ),
                "ble_rssi_delta_full_scale": self._safe_float(
                    request.form.get("ble_rssi_delta_full_scale"), 18.0, minimum=2.0, maximum=50.0
                ),
                "movement_smoothing": self._safe_float(
                    request.form.get("movement_smoothing"), 0.35, minimum=0.05, maximum=1.0
                ),
                "moving_threshold": self._safe_float(
                    request.form.get("moving_threshold"), 0.45, minimum=0.0, maximum=1.0
                ),
                "stationary_threshold": self._safe_float(
                    request.form.get("stationary_threshold"), 0.15, minimum=0.0, maximum=1.0
                ),
                "stationary_timeout": self._safe_float(
                    request.form.get("stationary_timeout"), 60.0, minimum=5.0, maximum=1800.0
                ),
                "environment_similarity": self._safe_float(
                    request.form.get("environment_similarity"), 0.80, minimum=0.0, maximum=1.0
                ),
                "gps_mode_enabled": self._form_bool(
                    request.form.get("gps_mode_enabled")
                ),
                "gps_movement_weight": self._safe_float(
                    request.form.get("gps_movement_weight"), 0.80, minimum=0.0, maximum=5.0
                ),
                "gps_speed_threshold": self._safe_float(
                    request.form.get("gps_speed_threshold"), 20.0, minimum=0.1
                ),
                "gps_fast_channels": self._clean_channels(
                    request.form.get("gps_fast_channels", "1,6,11")
                ),
                "gps_slow_channels": self._clean_channels(
                    request.form.get(
                        "gps_slow_channels",
                        "1,2,3,4,5,6,7,8,9,10,11,12,13,14",
                    )
                ),
                "gps_speed_is_mps": self._form_bool(
                    request.form.get("gps_speed_is_mps")
                ),
            }

            # Preserve hysteresis: the stationary threshold must remain below
            # the moving threshold. If the user crosses them, gently separate
            # them rather than saving an unstable configuration.
            if new_values["stationary_threshold"] >= new_values["moving_threshold"]:
                new_values["stationary_threshold"] = max(
                    0.0, new_values["moving_threshold"] - 0.05
                )

            self._save_plugin_config(new_values)

            should_restart = request.form.get("restart") == "yes"

            if should_restart:
                logging.info("[Car-Mode] Settings saved from WebUI. Restarting.")
                _thread.start_new_thread(restart, (self.mode,))
                return self._render_web(
                    "Settings saved. Pwnagotchi is restarting...",
                    True,
                )

            self.options.update(new_values)
            self._load_runtime_options()
            self._start_ble_scanner()

            # Re-learn motion after changing fusion thresholds/weights so an old
            # smoothed score cannot immediately trigger a mode change.
            self.movement_score = None
            self.stationary_since = None
            self.motion_state = "UNKNOWN"
            self.last_ap_set = set()
            self.forced_auto_mode = False
            with self._ble_lock:
                self._ble_snapshot = {}
                self.ble_change_score = None
                self.ble_turnover_score = None
                self.ble_rssi_score = None

            if self._agent is not None:
                self.mode_state = None
                self._applied_profile = None

                if self.gps_mode_enabled:
                    self._set_profile(
                        self._agent,
                        state="CAR_FAST",
                        hop_period=self.hop_period,
                        channels=self.gps_fast_channels,
                    )
                else:
                    self._set_profile(
                        self._agent,
                        state="CAR_MANUAL",
                        hop_period=self.hop_period,
                        channels=self.channels,
                    )

            logging.info("[Car-Mode] Settings saved from WebUI without restart.")
            return self._render_web(
                "Settings saved and the active channel profile was reapplied.",
                True,
            )

        except Exception as exc:
            logging.exception("[Car-Mode] WebUI save failed")
            return self._render_web(
                f"Could not save settings: {exc}",
                False,
            ), 500

    def _read_plugin_config(self):
        result = dict(self.DEFAULTS)

        try:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as fp:
                    config = tomlkit.load(fp)

                plugin_cfg = (
                    config.get("main", {})
                    .get("plugins", {})
                    .get("car_mode", {})
                )

                for key, default in self.DEFAULTS.items():
                    if key in plugin_cfg:
                        result[key] = plugin_cfg[key]
                    elif key in self.options:
                        result[key] = self.options[key]

        except Exception as exc:
            logging.error("[Car-Mode] Failed reading config file: %s", exc)

            for key, default in self.DEFAULTS.items():
                result[key] = self.options.get(key, default)

        return result

    def _save_plugin_config(self, values):
        if os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, "r", encoding="utf-8") as fp:
                config = tomlkit.load(fp)
        else:
            config = tomlkit.document()

        if "main" not in config:
            config["main"] = tomlkit.table()

        if "plugins" not in config["main"]:
            config["main"]["plugins"] = tomlkit.table()

        if "car_mode" not in config["main"]["plugins"]:
            config["main"]["plugins"]["car_mode"] = tomlkit.table()

        plugin_cfg = config["main"]["plugins"]["car_mode"]

        for key, value in values.items():
            plugin_cfg[key] = value

        save_config(config, self.CONFIG_PATH)

    def _load_runtime_options(self):
        self.hop_period = int(self.options.get("hop_period", 1))
        self.channels = str(self.options.get("channels", "1,6,11"))

        self.gps_mode_enabled = self._to_bool(
            self.options.get("gps_mode_enabled", False)
        )
        self.gps_speed_threshold = float(
            self.options.get("gps_speed_threshold", 20.0)
        )
        self.gps_fast_channels = str(
            self.options.get("gps_fast_channels", "1,6,11")
        )
        self.gps_slow_channels = str(
            self.options.get(
                "gps_slow_channels",
                "1,2,3,4,5,6,7,8,9,10,11,12,13,14",
            )
        )
        self.gps_speed_is_mps = self._to_bool(
            self.options.get("gps_speed_is_mps", False)
        )
        self.gps_movement_weight = float(
            self.options.get("gps_movement_weight", 0.80)
        )

        self.sensor_fusion_enabled = self._to_bool(
            self.options.get("sensor_fusion_enabled", True)
        )
        self.wifi_movement_weight = float(
            self.options.get("wifi_movement_weight", 0.60)
        )
        self.ble_movement_enabled = self._to_bool(
            self.options.get("ble_movement_enabled", True)
        )
        self.ble_skip_if_pan_active = self._to_bool(
            self.options.get("ble_skip_if_pan_active", True)
        )
        self.ble_movement_weight = float(
            self.options.get("ble_movement_weight", 0.40)
        )
        self.ble_scan_interval = float(
            self.options.get("ble_scan_interval", 10.0)
        )
        self.ble_scan_duration = int(
            self.options.get("ble_scan_duration", 2)
        )
        self.ble_min_rssi = int(self.options.get("ble_min_rssi", -90))
        self.ble_min_devices = int(self.options.get("ble_min_devices", 3))
        self.ble_rssi_delta_full_scale = float(
            self.options.get("ble_rssi_delta_full_scale", 18.0)
        )
        self.movement_smoothing = float(
            self.options.get("movement_smoothing", 0.35)
        )
        self.moving_threshold = float(
            self.options.get("moving_threshold", 0.45)
        )
        self.stationary_threshold = float(
            self.options.get("stationary_threshold", 0.15)
        )
        if self.stationary_threshold >= self.moving_threshold:
            self.stationary_threshold = max(0.0, self.moving_threshold - 0.05)

        self.stationary_timeout = float(
            self.options.get("stationary_timeout", 60.0)
        )
        self.environment_similarity = float(
            self.options.get("environment_similarity", 0.80)
        )

    def _start_ble_scanner(self):
        if self._ble_thread is not None and self._ble_thread.is_alive():
            return

        self._ble_stop.clear()
        self._ble_thread = threading.Thread(
            target=self._ble_scanner_loop,
            name="car-mode-ble",
            daemon=True,
        )
        self._ble_thread.start()

    def _ble_scanner_loop(self):
        while not self._ble_stop.is_set():
            if not (self.sensor_fusion_enabled and self.ble_movement_enabled):
                self.ble_scanner_status = "Disabled"
                self._ble_stop.wait(2.0)
                continue

            if self.ble_skip_if_pan_active and self._bluetooth_pan_active():
                self.ble_scanner_status = "Paused: Bluetooth tether/PAN active"
                with self._ble_lock:
                    self._ble_snapshot = {}
                    self.ble_device_count = 0
                    self.ble_change_score = None
                    self.ble_turnover_score = None
                    self.ble_rssi_score = None
                self._ble_stop.wait(min(5.0, max(2.0, self.ble_scan_interval)))
                continue

            started = time.monotonic()
            try:
                snapshot = self._scan_ble_once()
                if snapshot is not None:
                    self._publish_ble_snapshot(snapshot)
            except Exception as exc:
                self.ble_scanner_status = f"Error: {str(exc)[:70]}"
                logging.debug("[Car-Mode] BLE scan error: %s", exc)

            elapsed = time.monotonic() - started
            wait_for = max(1.0, self.ble_scan_interval - elapsed)
            self._ble_stop.wait(wait_for)

    def _bluetooth_pan_active(self):
        """Return True when a Linux Bluetooth PAN/tether interface is active.

        BlueZ PAN connections normally expose bnep* network interfaces. Reading
        sysfs is passive: this does not reconfigure Bluetooth, stop services,
        disconnect peers, or touch the network interface.
        """
        net_root = "/sys/class/net"
        try:
            for name in os.listdir(net_root):
                if not name.startswith("bnep"):
                    continue

                base = os.path.join(net_root, name)
                carrier = None
                operstate = ""

                try:
                    with open(os.path.join(base, "carrier"), "r", encoding="ascii") as fp:
                        carrier = fp.read().strip()
                except (OSError, ValueError):
                    pass

                try:
                    with open(os.path.join(base, "operstate"), "r", encoding="ascii") as fp:
                        operstate = fp.read().strip().lower()
                except OSError:
                    pass

                if carrier == "1" or operstate in ("up", "unknown"):
                    return True
        except OSError as exc:
            logging.debug("[Car-Mode] Could not inspect Bluetooth PAN state: %s", exc)

        return False

    def _scan_ble_once(self):
        bluetoothctl = shutil.which("bluetoothctl")
        if not bluetoothctl:
            self.ble_scanner_status = "bluetoothctl not installed"
            return None

        duration = max(1, min(15, int(self.ble_scan_duration)))
        env = os.environ.copy()
        env["LC_ALL"] = "C"

        try:
            result = subprocess.run(
                [bluetoothctl, "--timeout", str(duration), "scan", "le"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=duration + 5,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.ble_scanner_status = "BLE scan timed out"
            return None

        output = self._strip_ansi(result.stdout or "")
        raw_devices = {}
        address_re = re.compile(r"Device\s+([0-9A-Fa-f:]{17})")
        rssi_re = re.compile(r"RSSI:\s*(-?\d+)")

        for line in output.splitlines():
            if "[DEL]" in line:
                continue

            address_match = address_re.search(line)
            if not address_match:
                continue

            address = address_match.group(1).upper()
            rssi_match = rssi_re.search(line)
            rssi = int(rssi_match.group(1)) if rssi_match else None

            # If RSSI is present, reject weak/noisy observations. If the line
            # only announces a newly seen device, keep it for turnover/counts.
            if rssi is not None and rssi < self.ble_min_rssi:
                raw_devices.pop(address, None)
                continue

            previous_rssi = raw_devices.get(address)
            if rssi is not None or previous_rssi is None:
                raw_devices[address] = rssi

        if result.returncode != 0 and not raw_devices:
            last_line = next(
                (line.strip() for line in reversed(output.splitlines()) if line.strip()),
                f"exit {result.returncode}",
            )
            self.ble_scanner_status = f"Unavailable: {last_line[:60]}"
            return None

        # Hash addresses with a boot-local salt before retaining a snapshot.
        # We only need stable short-lived identifiers for consecutive scans.
        snapshot = {}
        for address, rssi in raw_devices.items():
            identifier = hashlib.blake2b(
                address.encode("ascii", "ignore"),
                key=self._ble_hash_salt,
                digest_size=8,
            ).hexdigest()
            snapshot[identifier] = rssi

        self.ble_scanner_status = f"OK ({len(snapshot)} devices)"
        return snapshot

    def _publish_ble_snapshot(self, snapshot):
        now = time.monotonic()
        with self._ble_lock:
            previous = self._ble_snapshot
            self._ble_snapshot = dict(snapshot)
            self.ble_device_count = len(snapshot)
            self.ble_last_scan_at = now

            if not previous:
                self.ble_change_score = None
                self.ble_turnover_score = None
                self.ble_rssi_score = None
                return

            first = set(previous)
            second = set(snapshot)
            similarity = self._environment_similarity(first, second)
            turnover = 1.0 - similarity

            population_delta = abs(len(first) - len(second)) / max(
                1, len(first), len(second)
            )

            rssi_deltas = []
            for identifier in first & second:
                before = previous.get(identifier)
                after = snapshot.get(identifier)
                if before is None or after is None:
                    continue
                rssi_deltas.append(abs(float(after) - float(before)))

            if rssi_deltas:
                average_delta = sum(rssi_deltas) / len(rssi_deltas)
                rssi_score = min(
                    1.0,
                    average_delta / max(1.0, self.ble_rssi_delta_full_scale),
                )
            else:
                rssi_score = 0.0

            self.ble_turnover_score = turnover
            self.ble_rssi_score = rssi_score

            # Do not trust a tiny BLE sample. In that situation Wi-Fi/GPS simply
            # carry the movement estimate until Bluetooth has enough evidence.
            if (
                len(previous) < self.ble_min_devices
                or len(snapshot) < self.ble_min_devices
            ):
                self.ble_change_score = None
                return

            self.ble_change_score = min(
                1.0,
                0.55 * turnover
                + 0.15 * population_delta
                + 0.30 * rssi_score,
            )

    def _calculate_movement_score(self, now, gps_speed_kmh=None):
        components = []

        if self.wifi_change_score is not None and self.wifi_movement_weight > 0:
            components.append(
                (self.wifi_change_score, self.wifi_movement_weight)
            )

        if self.ble_movement_enabled and self.ble_movement_weight > 0:
            with self._ble_lock:
                ble_score = self.ble_change_score
                ble_age = (
                    now - self.ble_last_scan_at
                    if self.ble_last_scan_at
                    else float("inf")
                )

            # A BLE result older than roughly two scan cycles is no longer a
            # useful movement observation.
            ble_fresh_for = max(
                15.0,
                self.ble_scan_interval * 2.5 + self.ble_scan_duration,
            )
            if ble_score is not None and ble_age <= ble_fresh_for:
                components.append((ble_score, self.ble_movement_weight))

        if (
            self.gps_mode_enabled
            and gps_speed_kmh is not None
            and self.gps_movement_weight > 0
        ):
            gps_score = min(
                1.0,
                max(0.0, gps_speed_kmh)
                / max(1.0, self.gps_speed_threshold),
            )
            components.append((gps_score, self.gps_movement_weight))

        total_weight = sum(weight for _, weight in components)
        if total_weight <= 0:
            return None

        return min(
            1.0,
            max(
                0.0,
                sum(score * weight for score, weight in components)
                / total_weight,
            ),
        )

    def _get_gps_speed_kmh(self, agent):
        gps = self._get_gps_data(agent)
        if not gps:
            return None

        raw_speed = gps.get("speed")
        if raw_speed is None:
            return None

        try:
            speed = max(0.0, float(raw_speed))
        except (TypeError, ValueError):
            logging.warning("[Car-Mode] Invalid GPS speed value: %r", raw_speed)
            return None

        return speed * 3.6 if self.gps_speed_is_mps else speed

    @staticmethod
    def _score_text(value):
        if value is None:
            return "n/a"
        return f"{max(0.0, min(1.0, float(value))) * 100:.0f}%"

    @staticmethod
    def _strip_ansi(value):
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)

    def _parse_channels(self, value):
        """Convert a comma-separated channel string to a validated integer list."""
        cleaned = self._clean_channels(value)
        if not cleaned:
            return []
        return [int(part) for part in cleaned.split(",")]

    def _active_channel_string(self):
        if self._applied_profile and len(self._applied_profile) == 3:
            _state, _hop_period, channels = self._applied_profile
            if channels:
                return channels
        if self.gps_mode_enabled:
            return self.gps_fast_channels
        return self.channels

    def _sync_core_channels(self, agent, channels):
        """Keep Pwnagotchi core locked to the exact active channel profile.

        BetterCAP's ``wifi.recon.channel`` controls the radio hopper, while
        Pwnagotchi also consults ``personality.channels`` when selecting APs.
        Keeping both sources in sync prevents the core from later selecting or
        requesting channels outside the currently active Car Mode profile.
        """
        try:
            desired = self._parse_channels(channels)
            agent._config["personality"]["channels"] = desired

            logging.debug(
                "[Car-Mode] Core personality.channels locked to %s",
                desired or "ALL",
            )
            return desired

        except Exception as exc:
            logging.error(
                "[Car-Mode] Failed syncing core personality.channels: %s",
                exc,
            )
            return []

    def _get_gps_data(self, agent):
        try:
            session = agent.session()
            if not session:
                return None

            gps = session.get("gps")
            if not isinstance(gps, dict):
                return None

            return gps

        except Exception as exc:
            logging.debug("[Car-Mode] GPS data unavailable: %s", exc)
            return None

    def _set_profile(self, agent, state, hop_period, channels):
        hop_period = max(1, int(hop_period))
        channels = self._clean_channels(channels)
        profile_key = (state, hop_period, channels)

        # Do not skip a reconfiguration merely because the state name is the
        # same: users may have changed the channels or hop period in WebUI.
        if self._applied_profile == profile_key:
            return

        logging.info(
            "[Car-Mode] Switching recon profile -> %s (hop=%s channels=%s)",
            state,
            hop_period,
            channels if channels else "ALL",
        )

        try:
            if state == "AUTO":
                # AUTO fallback intentionally restores the user's original core
                # channel configuration and clears BetterCAP's explicit lock.
                agent._config["personality"]["channels"] = list(
                    self._original_personality_channels or []
                )
            else:
                # Exact lock: both Pwnagotchi and BetterCAP receive the same
                # currently active channel list (not a fast/slow union).
                self._sync_core_channels(agent, channels)

            # BetterCAP's hopper period is expressed in milliseconds.
            agent.run(f"set wifi.hop.period {hop_period * 250}")

            if channels:
                agent.run(f"wifi.recon.channel {channels}")
            else:
                agent.run("wifi.recon.channel clear")

            # Restart recon so the new hopper/channel configuration takes
            # effect immediately rather than waiting for a later recon cycle.
            agent.run("wifi.recon off")
            agent.run("wifi.recon on")

            self.mode_state = state
            self._applied_profile = profile_key

        except Exception as exc:
            # Leave _applied_profile untouched so the next update retries.
            logging.error(
                "[Car-Mode] Failed switching profile to %s: %s",
                state,
                exc,
            )

    def _set_status(self, view, mode, status):
        if not view:
            return

        status_key = (mode, status)
        if status_key == self.last_status:
            return

        try:
            view.set("mode", mode)
            view.set("status", status)
            view.update(force=True)
            self.last_status = status_key

        except Exception as exc:
            logging.debug("[Car-Mode] Failed updating display: %s", exc)

    def _environment_similarity(self, first, second):
        if not first or not second:
            return 0.0

        union = first | second
        if not union:
            return 0.0

        intersection = first & second
        return len(intersection) / len(union)

    def _blink_led(self, times=5, speed=0.1):
        trigger_path = f"{self.led_path}/trigger"
        brightness_path = f"{self.led_path}/brightness"

        if not os.path.exists(brightness_path):
            return

        old_trigger = None

        try:
            if os.path.exists(trigger_path):
                try:
                    with open(trigger_path, "r") as file:
                        trigger_contents = file.read().strip()

                    for entry in trigger_contents.split():
                        if entry.startswith("[") and entry.endswith("]"):
                            old_trigger = entry[1:-1]
                            break
                except Exception:
                    old_trigger = None

                try:
                    with open(trigger_path, "w") as file:
                        file.write("none")
                except Exception:
                    pass

            for _ in range(times):
                with open(brightness_path, "w") as file:
                    file.write("1")

                time.sleep(speed)

                with open(brightness_path, "w") as file:
                    file.write("0")

                time.sleep(speed)

        except Exception as exc:
            logging.error("[Car-Mode] LED error: %s", exc)

        finally:
            if old_trigger and os.path.exists(trigger_path):
                try:
                    with open(trigger_path, "w") as file:
                        file.write(old_trigger)
                except Exception:
                    pass

    @staticmethod
    def _clean_channels(value):
        value = str(value or "").strip()
        if not value:
            return ""

        channels = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue

            channel = int(part)
            if channel < 1 or channel > 196:
                raise ValueError(f"Invalid Wi-Fi channel: {channel}")

            channels.append(str(channel))

        return ",".join(channels)

    @staticmethod
    def _safe_int(value, default, minimum=None, maximum=None):
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default

        if minimum is not None:
            number = max(minimum, number)

        if maximum is not None:
            number = min(maximum, number)

        return number

    @staticmethod
    def _safe_float(value, default, minimum=None, maximum=None):
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default

        if minimum is not None:
            number = max(minimum, number)

        if maximum is not None:
            number = min(maximum, number)

        return number

    @staticmethod
    def _form_bool(value):
        return str(value).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
            "enabled",
        )

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
                "enabled",
            )

        return bool(value)
