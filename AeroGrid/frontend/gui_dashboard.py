#!/usr/bin/env python3
"""AeroGrid UTM - Tactical Mission Control Cockpit (Glass HUD).

Sleek, minimalist, high-impact aerospace dashboard designed for rapid situational
awareness and live demonstration during the ITU AI for Good Hackathon.

Features:
- Glass Cockpit Tactical Airspace Radar (Dubai BVLOS Corridor)
- High-contrast Avionics Telemetry Meters (Altitude, Speed, Battery, C2 QoS)
- 4 Primary Interactive Scenario Decks (Nominal, HEMS, 5G Shadow, Battery Divert)
- Clean Visual Agent Decision Cards (Aviation, Telecom, Fleet) with Priority Badges
- Executive Statutory Arbitration Verdict Banner
- Real-Time Mission Event Ticker (Clean audit stream)
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# Project paths
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine
from backend.simulation.coppelia_zmq_bridge import CoppeliaZMQBridge


# ==============================================================================
# Glass Cockpit Tactical Radar Widget
# ==============================================================================
class GlassCockpitRadar(QWidget):
    """High-contrast, minimalist Tactical Airspace Radar display."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(460, 440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sweep_angle: float = 0.0
        self.active_scenario: int = 0
        self.drone_pos = {"x": 0.0, "y": 0.0, "z": 2.0}

        # 30 FPS sweep timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def _tick(self):
        self.sweep_angle = (self.sweep_angle + 2.5) % 360.0
        self.update()

    def set_scenario(self, scenario_idx: int):
        self.active_scenario = scenario_idx
        self.update()

    def update_drone_telemetry(self, x: float, y: float, z: float):
        self.drone_pos = {"x": x, "y": y, "z": z}
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(cx, cy) - 24.0

        # Deep aerospace backdrop
        p.fillRect(0, 0, w, h, QColor("#080c14"))

        # Outer Radar Ring with Subtle Cyan Glow
        p.setPen(QPen(QColor("#00f3ff"), 1.8))
        p.setBrush(QBrush(QColor("#0a111e")))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Concentric Distance Rings
        ring_pen = QPen(QColor(0, 243, 255, 40), 1, Qt.DashLine)
        p.setPen(ring_pen)
        p.setBrush(Qt.NoBrush)

        rings = [(0.25, "250m"), (0.50, "500m"), (0.75, "750m"), (1.0, "1000m")]
        p.setFont(QFont("Monospace", 8))
        for frac, label in rings:
            r = radius * frac
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QPen(QColor(0, 243, 255, 80)))
            p.drawText(int(cx + 6), int(cy - r + 12), label)
            p.setPen(ring_pen)

        # Crosshairs
        p.setPen(QPen(QColor(0, 243, 255, 30), 1))
        p.drawLine(int(cx - radius), int(cy), int(cx + radius), int(cy))
        p.drawLine(int(cx), int(cy - radius), int(cx), int(cy + radius))

        # Radar Sweep Beam
        rad = math.radians(self.sweep_angle)
        bx = cx + radius * math.cos(rad)
        by = cy + radius * math.sin(rad)

        p.setPen(QPen(QColor(0, 243, 255, 190), 2))
        p.drawLine(QPointF(cx, cy), QPointF(bx, by))

        # Sweep sector cone
        cone = QPainterPath()
        cone.moveTo(cx, cy)
        cone.arcTo(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), -self.sweep_angle, 35)
        cone.closeSubpath()
        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0, QColor(0, 243, 255, 45))
        grad.setColorAt(1, QColor(0, 243, 255, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawPath(cone)

        # ----------------------------------------------------------------------
        # Tactical Map Objects
        # ----------------------------------------------------------------------
        # 1. Vertiport Pad 1 (Always Visible in Safe Sector)
        vp_x = cx - radius * 0.65
        vp_y = cy + radius * 0.45
        p.setPen(QPen(QColor("#30d158"), 2))
        p.setBrush(QBrush(QColor(48, 209, 88, 50)))
        p.drawEllipse(QPointF(vp_x, vp_y), 9, 9)
        p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
        p.setPen(QPen(QColor("#30d158")))
        p.drawText(int(vp_x + 14), int(vp_y + 4), "Vertiport Pad 1")

        # 2. Scenario 1: HEMS Manned Medical Helicopter Incursion
        if self.active_scenario == 1:
            hx = cx + radius * 0.60
            hy = cy - radius * 0.50
            # Warning Pulse
            flash = int(180 + 75 * math.sin(time.time() * 9))
            p.setPen(QPen(QColor(255, 69, 58, flash), 2))
            p.setBrush(QBrush(QColor(255, 69, 58, 60)))
            p.drawEllipse(QPointF(hx, hy), 12, 12)
            p.setBrush(QBrush(QColor("#ff453a")))
            p.drawEllipse(QPointF(hx, hy), 5, 5)
            p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
            p.setPen(QPen(QColor("#ff453a")))
            p.drawText(int(hx + 16), int(hy + 4), "🚨 HEMS INTRUDER (820m)")

        # 3. Scenario 2: 5G Signal Shadow Zone
        elif self.active_scenario == 2:
            sx = cx - radius * 0.15
            sy = cy - radius * 0.40
            p.setPen(QPen(QColor(0, 243, 255, 180), 1.5, Qt.DashDotLine))
            p.setBrush(QBrush(QColor(0, 243, 255, 25)))
            p.drawEllipse(QPointF(sx, sy), 48, 48)
            p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
            p.setPen(QPen(QColor("#00f3ff")))
            p.drawText(int(sx - 40), int(sy), "📶 5G SHADOW CELL")

        # 4. Our UAS Flight (Drone)
        # Scaled coordinates
        dx = cx + (self.drone_pos["x"] * (radius / 3.0))
        dy = cy - (self.drone_pos["y"] * (radius / 3.0))
        p.setPen(QPen(QColor(0, 243, 255, 120), 2))
        p.setBrush(QBrush(QColor(0, 243, 255, 45)))
        p.drawEllipse(QPointF(dx, dy), 10, 10)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(dx, dy), 4, 4)

        # Drone Label & Altitude Tag
        p.setFont(QFont("Monospace", 9, QFont.Bold))
        p.setPen(QPen(QColor("#00f3ff")))
        p.drawText(int(dx + 15), int(dy + 4), f"UAS-104 [{self.drone_pos['z']:.2f}m]")


# ==============================================================================
# Modern Glass Mission Control HUD
# ==============================================================================
class AeroGridTacticalHUD(QMainWindow):
    """Clean, intuitive Glass Mission Control Cockpit for AeroGrid UTM."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroGrid UTM - Tactical Mission Control [ITU AI for Good]")
        self.resize(1300, 840)
        self.setMinimumSize(1080, 700)

        # Initialize Backend
        self.audit_engine = AuditEngine(db_path=os.path.join(WORKSPACE_ROOT, "backend/audit/aerogrid_audit.db"))
        self.retriever = PolicyRetriever(chroma_persist_dir=os.path.join(WORKSPACE_ROOT, "backend/knowledge_base/vector_db"))
        self.aviation_agent = AviationAgent(llm_client=None, retriever=self.retriever)
        self.telecom_agent = TelecomAgent(llm_client=None, retriever=self.retriever)
        self.fleet_agent = FleetAgent(llm_client=None, retriever=self.retriever)
        self.coordination_engine = CoordinationEngine(audit_engine=self.audit_engine)

        # ZeroMQ Bridge
        self.zmq_bridge = CoppeliaZMQBridge()
        self.zmq_bridge.connect()

        self.current_scenario_idx = 0
        self._build_ui()
        self._apply_glass_theme()

        # Telemetry poll loop (10 Hz)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_telemetry)
        self.poll_timer.start(100)

        # Boot into Nominal Cruise (Hover 2.0m)
        self.run_scenario(0)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # ----------------------------------------------------------------------
        # Top Deck: App Identity + 4 Primary Scenario Control Cards
        # ----------------------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(1)
        b_title = QLabel("AEROGRID")
        b_title.setObjectName("brandTitle")
        b_sub = QLabel("AUTONOMOUS UTM MISSION CONTROL • ITU AI FOR GOOD")
        b_sub.setObjectName("brandSubtitle")
        brand_box.addWidget(b_title)
        brand_box.addWidget(b_sub)
        top_bar.addLayout(brand_box)

        top_bar.addSpacing(20)

        # 4 Interactive Scenario Cards
        self.btn_scen0 = self._create_scenario_btn("0: NOMINAL CRUISE", "Safe BVLOS Corridor (2.0m)", "#30d158", 0)
        self.btn_scen1 = self._create_scenario_btn("1: HEMS EMERGENCY", "Manned Aircraft Right-of-Way", "#ff453a", 1)
        self.btn_scen2 = self._create_scenario_btn("2: 5G SHADOWING", "Urban Canyon C2 Handover", "#00f3ff", 2)
        self.btn_scen3 = self._create_scenario_btn("3: LOW BATTERY", "Critical Vertiport Divert", "#ff9f0a", 3)

        top_bar.addWidget(self.btn_scen0)
        top_bar.addWidget(self.btn_scen1)
        top_bar.addWidget(self.btn_scen2)
        top_bar.addWidget(self.btn_scen3)

        root.addLayout(top_bar)

        # ----------------------------------------------------------------------
        # Avionics Telemetry HUD Bar (5 Clean Digital Gauges)
        # ----------------------------------------------------------------------
        telem_row = QHBoxLayout()
        telem_row.setSpacing(10)

        self.gauge_alt = self._create_avionics_gauge("ALTITUDE", "2.00 m", "#00f3ff", "Sim Target Altitude")
        self.gauge_speed = self._create_avionics_gauge("GROUND SPEED", "20.0 m/s", "#ffffff", "Corridor Velocity")
        self.gauge_battery = self._create_avionics_gauge("BATTERY SOC", "82%", "#30d158", "LiPo Energy Reserve")
        self.gauge_c2 = self._create_avionics_gauge("C2 LATENCY", "32 ms", "#30d158", "TDRA 5GHz Link QoS")
        self.gauge_cop = self._create_avionics_gauge("COPPELIASIM", "CONNECTED", "#30d158", "ZeroMQ Port 23000")

        telem_row.addWidget(self.gauge_alt)
        telem_row.addWidget(self.gauge_speed)
        telem_row.addWidget(self.gauge_battery)
        telem_row.addWidget(self.gauge_c2)
        telem_row.addWidget(self.gauge_cop)

        root.addLayout(telem_row)

        # ----------------------------------------------------------------------
        # Center Body: Tactical Radar (Left) + 3 Clean Domain Cards (Right)
        # ----------------------------------------------------------------------
        body_split = QSplitter(Qt.Horizontal)
        body_split.setHandleWidth(8)

        # Left: Tactical Radar
        radar_container = QFrame()
        radar_container.setObjectName("radarContainer")
        rc_layout = QVBoxLayout(radar_container)
        rc_layout.setContentsMargins(10, 10, 10, 10)
        self.radar = GlassCockpitRadar()
        rc_layout.addWidget(self.radar)
        body_split.addWidget(radar_container)

        # Right: Clean Multi-Agent Status Deck
        deck_box = QWidget()
        deck_layout = QVBoxLayout(deck_box)
        deck_layout.setContentsMargins(0, 0, 0, 0)
        deck_layout.setSpacing(10)

        # 3 Visual Agent Cards
        self.card_aviation = self._create_domain_card(
            agent_name="AVIATION SAFETY AGENT",
            tier_badge="TIER 1 (AIRSPACE SAFETY)",
            action_text="MAINTAIN CORRIDOR",
            status_text="NOMINAL",
            law_tag="UAE Law 26 • GCAA CAR Part IV",
            theme_color="#30d158",
        )
        self.card_telecom = self._create_domain_card(
            agent_name="TELECOM C2 AGENT",
            tier_badge="TIER 2 (SPECTRUM QoS)",
            action_text="MAINTAIN C2 PROFILE",
            status_text="NOMINAL",
            law_tag="TDRA 5030-5091 MHz • ICAO Annex 10",
            theme_color="#30d158",
        )
        self.card_fleet = self._create_domain_card(
            agent_name="FLEET LOGISTICS AGENT",
            tier_badge="TIER 3 (COMMERCIAL SLA)",
            action_text="CONTINUE FLIGHT PLAN",
            status_text="NOMINAL",
            law_tag="AeroGrid Fleet SOP Sec 4.2",
            theme_color="#30d158",
        )

        deck_layout.addWidget(self.card_aviation)
        deck_layout.addWidget(self.card_telecom)
        deck_layout.addWidget(self.card_fleet)

        body_split.addWidget(deck_box)
        body_split.setStretchFactor(0, 6)
        body_split.setStretchFactor(1, 5)

        root.addWidget(body_split, stretch=5)

        # ----------------------------------------------------------------------
        # Executive Arbitration Verdict Banner
        # ----------------------------------------------------------------------
        self.verdict_frame = QFrame()
        self.verdict_frame.setObjectName("verdictFrame")
        vf_layout = QHBoxLayout(self.verdict_frame)
        vf_layout.setContentsMargins(16, 12, 16, 12)
        vf_layout.setSpacing(14)

        v_left = QVBoxLayout()
        v_left.setSpacing(2)
        self.v_badge = QLabel("STATUTORY ARBITRATION VERDICT")
        self.v_badge.setObjectName("vBadge")
        self.v_action = QLabel("MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR")
        self.v_action.setObjectName("vAction")
        v_left.addWidget(self.v_badge)
        v_left.addWidget(self.v_action)
        vf_layout.addLayout(v_left, stretch=4)

        v_right = QVBoxLayout()
        v_right.setSpacing(2)
        self.v_summary = QLabel("All airspace safety, spectrum, and battery telemetry are nominal. Continuing BVLOS corridor cruise.")
        self.v_summary.setObjectName("vSummary")
        self.v_summary.setWordWrap(True)
        self.v_overruled = QLabel("Consensus Reached: No agent recommendations overruled.")
        self.v_overruled.setObjectName("vOverruled")
        v_right.addWidget(self.v_summary)
        v_right.addWidget(self.v_overruled)
        vf_layout.addLayout(v_right, stretch=6)

        root.addWidget(self.verdict_frame, stretch=1)

        # ----------------------------------------------------------------------
        # Real-Time Mission Event Ticker (Clean Audit Log Stream)
        # ----------------------------------------------------------------------
        self.ticker_box = QFrame()
        self.ticker_box.setObjectName("tickerBox")
        tb_layout = QHBoxLayout(self.ticker_box)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        self.ticker_label = QLabel("MISSION LOG: System initialized. SQLite WAL audit active. CoppeliaSim bridge ready.")
        self.ticker_label.setObjectName("tickerLabel")
        tb_layout.addWidget(self.ticker_label)
        root.addWidget(self.ticker_box)

    # --------------------------------------------------------------------------
    # UI Component Generators
    # --------------------------------------------------------------------------
    def _create_scenario_btn(self, title: str, subtitle: str, color: str, idx: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("scenBtn")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumHeight(52)

        l = QVBoxLayout(btn)
        l.setContentsMargins(12, 6, 12, 6)
        l.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"color: {color}; font-weight: 800; font-size: 11px;")
        s = QLabel(subtitle)
        s.setStyleSheet("color: #718096; font-size: 9px;")
        l.addWidget(t)
        l.addWidget(s)

        btn.clicked.connect(lambda: self.run_scenario(idx))
        btn.color = color
        btn.idx = idx
        return btn

    def _create_avionics_gauge(self, label: str, val: str, color: str, sub: str) -> QFrame:
        gauge = QFrame()
        gauge.setObjectName("gaugeCard")
        l = QVBoxLayout(gauge)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(1)

        lbl = QLabel(label)
        lbl.setObjectName("gaugeLabel")
        v = QLabel(val)
        v.setObjectName("gaugeValue")
        v.setStyleSheet(f"color: {color};")
        s = QLabel(sub)
        s.setObjectName("gaugeSub")

        l.addWidget(lbl)
        l.addWidget(v)
        l.addWidget(s)
        gauge.val_lbl = v
        return gauge

    def _create_domain_card(self, agent_name: str, tier_badge: str, action_text: str, status_text: str, law_tag: str, theme_color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("domainCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(14, 10, 14, 10)
        l.setSpacing(4)

        head = QHBoxLayout()
        name = QLabel(agent_name)
        name.setObjectName("cardName")
        badge = QLabel(tier_badge)
        badge.setObjectName("cardBadge")
        badge.setStyleSheet(f"color: {theme_color}; border: 1px solid {theme_color};")
        head.addWidget(name)
        head.addStretch()
        head.addWidget(badge)
        l.addLayout(head)

        mid = QHBoxLayout()
        act = QLabel(action_text)
        act.setObjectName("cardAction")
        stat = QLabel(status_text)
        stat.setObjectName("cardStatus")
        stat.setStyleSheet(f"color: {theme_color}; font-weight: 800;")
        mid.addWidget(act)
        mid.addStretch()
        mid.addWidget(stat)
        l.addLayout(mid)

        law = QLabel(law_tag)
        law.setObjectName("cardLaw")
        l.addWidget(law)

        card.action_lbl = act
        card.status_lbl = stat
        card.badge_lbl = badge
        return card

    # --------------------------------------------------------------------------
    # Scenario Coordination & Execution
    # --------------------------------------------------------------------------
    def run_scenario(self, scenario_idx: int):
        self.current_scenario_idx = scenario_idx
        self.radar.set_scenario(scenario_idx)

        # Highlight active button
        for b in [self.btn_scen0, self.btn_scen1, self.btn_scen2, self.btn_scen3]:
            if b.idx == scenario_idx:
                b.setStyleSheet(f"background: #132238; border: 2px solid {b.color}; border-radius: 6px;")
            else:
                b.setStyleSheet("background: #0d1524; border: 1px solid #1a273e; border-radius: 6px;")

        state = self._build_state(scenario_idx)
        drone_id = state["drone_id"]

        # Deliberate with domain agents
        av_resp = self.aviation_agent.evaluate_state(state)
        tel_resp = self.telecom_agent.evaluate_state(state)
        flt_resp = self.fleet_agent.evaluate_state(state)

        # Resolve with statutory priority
        cmd = self.coordination_engine.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tel_resp,
            fleet_resp=flt_resp,
            state=state,
            target_drone_id=drone_id,
        )

        # Update HUD Visuals
        self._update_hud(scenario_idx, av_resp, tel_resp, flt_resp, cmd, state)

        # Actuate via ZeroMQ
        act = self.zmq_bridge.execute_utm_action(cmd.action, drone_id)

        # Update Event Ticker
        now_str = time.strftime("%H:%M:%S")
        self.ticker_label.setText(
            f"[{now_str}] SCENARIO {scenario_idx} • DIRECTIVE: {cmd.action} • TARGET Z: {act['target_z']:.2f}m • WAL AUDIT ID: {cmd.audit_event_id[:16]}..."
        )

    def _build_state(self, s: int) -> dict:
        if s == 0:
            return {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": "2026-11-08T17:00:00Z",
                "altitude_m": 120,
                "ground_speed_mps": 20.0,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 9999, "corridor_id": "DXB-BVLOS-04"},
                "telecom_metrics": {"rtt_latency_ms": 32, "packet_loss_pct": 0.05, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_CARGO_DXB_104", "battery_soc_pct": 82.0, "cargo_type": "standard_parcel", "expedited_medical_payload": False},
            }
        elif s == 1:
            return {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": "2026-11-08T17:00:00Z",
                "altitude_m": 120,
                "ground_speed_mps": 22.5,
                "airspace_traffic": {
                    "manned_traffic_detected": True,
                    "intruder_type": "HEMS_AIR_AMBULANCE",
                    "intruder_distance_m": 820,
                    "bearing_deg": 45,
                    "closing_speed_mps": 65.0,
                    "estimated_tcas_tau_sec": 12.6,
                    "corridor_id": "DXB-BVLOS-04",
                },
                "telecom_metrics": {"rtt_latency_ms": 42, "packet_loss_pct": 0.1, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_CARGO_DXB_104", "battery_soc_pct": 21.5, "cargo_type": "standard_parcel", "expedited_medical_payload": False},
            }
        elif s == 2:
            return {
                "drone_id": "UAS_DELIVERY_AUH_209",
                "timestamp": "2026-11-08T17:05:00Z",
                "altitude_m": 90,
                "ground_speed_mps": 18.0,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 4500},
                "telecom_metrics": {"rtt_latency_ms": 295, "packet_loss_pct": 3.8, "link_lost": False, "urban_canyon_shadowing": True},
                "fleet_telemetry": {"drone_id": "UAS_DELIVERY_AUH_209", "battery_soc_pct": 58.0, "cargo_type": "high_value_retail", "expedited_medical_payload": False},
            }
        else:
            return {
                "drone_id": "UAS_MED_SHJ_311",
                "timestamp": "2026-11-08T17:10:00Z",
                "altitude_m": 105,
                "ground_speed_mps": 15.0,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 6000},
                "telecom_metrics": {"rtt_latency_ms": 38, "packet_loss_pct": 0.05, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_MED_SHJ_311", "battery_soc_pct": 14.2, "cargo_type": "emergency_antivenom", "expedited_medical_payload": True},
            }

    def _update_hud(self, s: int, av, tel, flt, cmd, state):
        # 1. Update Avionics Gauges
        if s == 0:
            self.gauge_alt.val_lbl.setText("2.00 m")
            self.gauge_alt.val_lbl.setStyleSheet("color: #30d158;")
            self.gauge_battery.val_lbl.setText("82%")
            self.gauge_battery.val_lbl.setStyleSheet("color: #30d158;")
            self.gauge_c2.val_lbl.setText("32 ms")
            self.gauge_c2.val_lbl.setStyleSheet("color: #30d158;")
        elif s == 1:
            self.gauge_alt.val_lbl.setText("LAND (0.05m)")
            self.gauge_alt.val_lbl.setStyleSheet("color: #ff453a;")
            self.gauge_battery.val_lbl.setText("21.5%")
            self.gauge_battery.val_lbl.setStyleSheet("color: #ff9f0a;")
            self.gauge_c2.val_lbl.setText("42 ms")
        elif s == 2:
            self.gauge_alt.val_lbl.setText("1.50 m (-0.5m)")
            self.gauge_alt.val_lbl.setStyleSheet("color: #00f3ff;")
            self.gauge_c2.val_lbl.setText("295 ms (LOSS 3.8%)")
            self.gauge_c2.val_lbl.setStyleSheet("color: #ff453a;")
            self.gauge_battery.val_lbl.setText("58%")
        else:
            self.gauge_alt.val_lbl.setText("0.80 m (Pad 1)")
            self.gauge_alt.val_lbl.setStyleSheet("color: #ff9f0a;")
            self.gauge_battery.val_lbl.setText("14.2% (CRITICAL)")
            self.gauge_battery.val_lbl.setStyleSheet("color: #ff453a;")

        # 2. Update Domain Cards with clean visual cues
        self.card_aviation.action_lbl.setText(av.recommended_action)
        self.card_telecom.action_lbl.setText(tel.recommended_action)
        self.card_fleet.action_lbl.setText(flt.recommended_action)

        if s == 0:
            self.card_aviation.status_lbl.setText("NOMINAL")
            self.card_aviation.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_telecom.status_lbl.setText("NOMINAL")
            self.card_telecom.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_fleet.status_lbl.setText("NOMINAL")
            self.card_fleet.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")

        elif s == 1:
            self.card_aviation.status_lbl.setText("🚨 CRITICAL ACTION")
            self.card_aviation.status_lbl.setStyleSheet("color: #ff453a; font-weight: 800;")
            self.card_telecom.status_lbl.setText("NOMINAL")
            self.card_telecom.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_fleet.status_lbl.setText("OVERRULED")
            self.card_fleet.status_lbl.setStyleSheet("color: #718096; font-weight: 800;")

        elif s == 2:
            self.card_aviation.status_lbl.setText("NOMINAL")
            self.card_aviation.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_telecom.status_lbl.setText("⚠️ C2 DEGRADED")
            self.card_telecom.status_lbl.setStyleSheet("color: #00f3ff; font-weight: 800;")
            self.card_fleet.status_lbl.setText("OVERRULED")
            self.card_fleet.status_lbl.setStyleSheet("color: #718096; font-weight: 800;")

        else:
            self.card_aviation.status_lbl.setText("NOMINAL")
            self.card_aviation.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_telecom.status_lbl.setText("NOMINAL")
            self.card_telecom.status_lbl.setStyleSheet("color: #30d158; font-weight: 800;")
            self.card_fleet.status_lbl.setText("⚡ BATTERY CRITICAL")
            self.card_fleet.status_lbl.setStyleSheet("color: #ff9f0a; font-weight: 800;")

        # 3. Update Verdict Banner
        self.v_action.setText(cmd.action)
        if s == 0:
            self.v_badge.setText("STATUS: NOMINAL BVLOS CRUISE (STABLE 2.0m HOVER)")
            self.v_badge.setStyleSheet("color: #30d158; font-weight: 800;")
            self.v_summary.setText("Airspace clear, C2 link nominal, battery healthy. Drone maintaining assigned corridor setpoint.")
            self.v_overruled.setText("Consensus Reached: No agent recommendations overruled.")
            self.verdict_frame.setStyleSheet("background: #0c182b; border: 1.5px solid #30d158; border-radius: 8px;")

        elif s == 1:
            self.v_badge.setText("TIER 1 STATUTORY MANDATE ENFORCED (AIRSPACE SAFETY)")
            self.v_badge.setStyleSheet("color: #ff453a; font-weight: 800;")
            self.v_summary.setText("HEMS medical helicopter detected at 820m. Airspace law strictly commands immediate landing to yield corridor.")
            self.v_overruled.setText("Overruled: [Fleet Agent] Delivery SLA subordinated to life-safety separation minima.")
            self.verdict_frame.setStyleSheet("background: #1a0f16; border: 1.5px solid #ff453a; border-radius: 8px;")

        elif s == 2:
            self.v_badge.setText("TIER 2 STATUTORY MANDATE ENFORCED (C2 LINK QOS)")
            self.v_badge.setStyleSheet("color: #00f3ff; font-weight: 800;")
            self.v_summary.setText("5G latency spiked to 295ms due to skyscraper shadowing. Dropping altitude to 1.5m to regain gNodeB line-of-sight.")
            self.v_overruled.setText("Overruled: [Fleet Agent] Commercial flight schedule subordinated to C2 link failsafe requirements.")
            self.verdict_frame.setStyleSheet("background: #091729; border: 1.5px solid #00f3ff; border-radius: 8px;")

        else:
            self.v_badge.setText("TIER 3 FLEET SAFETY DIRECTIVE APPROVED")
            self.v_badge.setStyleSheet("color: #ff9f0a; font-weight: 800;")
            self.v_summary.setText("Battery depleted to 14.2%. Airspace and C2 link confirmed clear. Rerouting flight path to Vertiport Pad 1.")
            self.v_overruled.setText("Consensus Approved: Emergency energy diversion authorized pursuant to Fleet SOP Sec 4.2.")
            self.verdict_frame.setStyleSheet("background: #19140c; border: 1.5px solid #ff9f0a; border-radius: 8px;")

    def _poll_telemetry(self):
        telem = self.zmq_bridge.read_telemetry()
        if telem["connected"]:
            self.gauge_cop.val_lbl.setText("CONNECTED")
            self.gauge_cop.val_lbl.setStyleSheet("color: #30d158;")
            self.radar.update_drone_telemetry(telem["x"], telem["y"], telem["z"])
        else:
            self.gauge_cop.val_lbl.setText("STANDBY")
            self.gauge_cop.val_lbl.setStyleSheet("color: #718096;")

    # --------------------------------------------------------------------------
    # Clean Glass Aerospace Theme (QSS)
    # --------------------------------------------------------------------------
    def _apply_glass_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #080c14;
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            }
            #brandTitle {
                font-size: 22px;
                font-weight: 900;
                color: #00f3ff;
                letter-spacing: 2px;
            }
            #brandSubtitle {
                font-size: 9px;
                font-weight: 700;
                color: #64748b;
                letter-spacing: 1.2px;
            }
            #gaugeCard {
                background-color: #0c1322;
                border: 1px solid #162238;
                border-radius: 6px;
            }
            #gaugeLabel {
                font-size: 9px;
                font-weight: 800;
                color: #94a3b8;
                letter-spacing: 0.8px;
            }
            #gaugeValue {
                font-size: 15px;
                font-weight: 900;
                font-family: 'Monospace', monospace;
            }
            #gaugeSub {
                font-size: 8px;
                color: #64748b;
            }
            #radarContainer {
                background-color: #0a111e;
                border: 1px solid #16243c;
                border-radius: 8px;
            }
            #domainCard {
                background-color: #0b1426;
                border: 1px solid #192742;
                border-radius: 8px;
            }
            #cardName {
                font-size: 11px;
                font-weight: 800;
                color: #f1f5f9;
            }
            #cardBadge {
                font-size: 9px;
                font-weight: 800;
                padding: 2px 7px;
                border-radius: 4px;
                font-family: 'Monospace', monospace;
            }
            #cardAction {
                font-size: 12px;
                font-weight: 800;
                color: #38bdf8;
                font-family: 'Monospace', monospace;
            }
            #cardStatus {
                font-size: 10px;
                font-weight: 800;
            }
            #cardLaw {
                font-size: 9px;
                color: #64748b;
                font-style: italic;
            }
            #verdictFrame {
                background: #0c182b;
                border: 1.5px solid #00f3ff;
                border-radius: 8px;
            }
            #vBadge {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            #vAction {
                font-size: 15px;
                font-weight: 900;
                color: #00f3ff;
                font-family: 'Monospace', monospace;
            }
            #vSummary {
                font-size: 11px;
                color: #e2e8f0;
                font-weight: 500;
            }
            #vOverruled {
                font-size: 10px;
                color: #94a3b8;
                font-style: italic;
            }
            #tickerBox {
                background-color: #05080e;
                border: 1px solid #111a2e;
                border-radius: 4px;
            }
            #tickerLabel {
                font-size: 9.5px;
                color: #38bdf8;
                font-family: 'Monospace', monospace;
            }
        """)


def main():
    app = QApplication(sys.argv)
    window = AeroGridTacticalHUD()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
