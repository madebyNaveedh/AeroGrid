#!/usr/bin/env python3
"""AeroGrid UTM - Native PyQt5 Tactical Mission Control Dashboard.

High-performance native desktop GUI for the ITU AI for Good Hackathon.
Visualizes:
- Tactical Airspace Radar with dynamic targets (HEMS, NFZ, BVLOS Corridors)
- Live Multi-Agent Deliberation (Aviation Safety, Telecom C2, Fleet Logistics)
- Coordination Engine Statutory Arbitration Verdicts
- Real-Time Drone Telemetry & Actuation via ZeroMQ CoppeliaSim Bridge
- SQLite WAL Audit Log Stream
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Add AeroGrid to path
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
# Tactical Airspace Radar Widget (QPainter)
# ==============================================================================
class AirspaceRadarWidget(QWidget):
    """Custom high-DPI Tactical Airspace Radar Display."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(420, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Radar animation state
        self.sweep_angle: float = 0.0
        self.active_scenario: int = 1

        # Drone position and altitude
        self.drone_pos = {"x": 0.0, "y": 0.0, "z": 2.0}
        self.hems_pos = {"x": 160.0, "y": -120.0, "dist": 820}
        self.vertiport_pos = {"x": -180.0, "y": 140.0}

        # 30 FPS sweep timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_sweep)
        self.anim_timer.start(33)

    def _update_sweep(self):
        self.sweep_angle = (self.sweep_angle + 2.5) % 360.0
        self.update()

    def set_scenario(self, scenario_idx: int):
        self.active_scenario = scenario_idx
        self.update()

    def update_drone_telemetry(self, x: float, y: float, z: float):
        self.drone_pos = {"x": x, "y": y, "z": z}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = width / 2.0
        center_y = height / 2.0
        radius = min(center_x, center_y) - 20.0

        # Background
        painter.fillRect(0, 0, width, height, QColor("#080c14"))

        # Outer glowing boundary
        pen_outer = QPen(QColor("#00f3ff"), 1.5)
        painter.setPen(pen_outer)
        painter.setBrush(QBrush(QColor("#0b121e")))
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        # Concentric Radar Range Rings
        ring_pen = QPen(QColor(0, 243, 255, 45), 1, Qt.DashLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)

        num_rings = 4
        labels = ["250m", "500m", "750m", "1000m"]
        font_ring = QFont("Monospace", 8)
        painter.setFont(font_ring)

        for i in range(1, num_rings + 1):
            r = radius * (i / num_rings)
            painter.drawEllipse(QPointF(center_x, center_y), r, r)
            painter.setPen(QPen(QColor(0, 243, 255, 90)))
            painter.drawText(int(center_x + 5), int(center_y - r + 12), labels[i - 1])
            painter.setPen(ring_pen)

        # Crosshairs and radial lines
        cross_pen = QPen(QColor(0, 243, 255, 35), 1)
        painter.setPen(cross_pen)
        painter.drawLine(int(center_x - radius), int(center_y), int(center_x + radius), int(center_y))
        painter.drawLine(int(center_x), int(center_y - radius), int(center_x), int(center_y + radius))

        # Radar Sweep Beam
        rad = math.radians(self.sweep_angle)
        beam_x = center_x + radius * math.cos(rad)
        beam_y = center_y + radius * math.sin(rad)

        sweep_pen = QPen(QColor(0, 243, 255, 180), 2)
        painter.setPen(sweep_pen)
        painter.drawLine(QPointF(center_x, center_y), QPointF(beam_x, beam_y))

        # Sweep sector cone gradient
        cone_path = QPainterPath()
        cone_path.moveTo(center_x, center_y)
        cone_path.arcTo(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2), -self.sweep_angle, 40)
        cone_path.closeSubpath()
        grad = QRadialGradient(center_x, center_y, radius)
        grad.setColorAt(0, QColor(0, 243, 255, 40))
        grad.setColorAt(1, QColor(0, 243, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawPath(cone_path)

        # ----------------------------------------------------------------------
        # Tactical Entities
        # ----------------------------------------------------------------------
        # 1. No-Fly Zone (NFZ Buffer)
        nfz_x = center_x + 40
        nfz_y = center_y - 120
        painter.setPen(QPen(QColor(255, 59, 48, 160), 1.5, Qt.DashLine))
        painter.setBrush(QBrush(QColor(255, 59, 48, 25)))
        painter.drawRect(int(nfz_x), int(nfz_y), 70, 50)
        painter.setPen(QPen(QColor(255, 59, 48, 200)))
        painter.setFont(QFont("Monospace", 7, QFont.Bold))
        painter.drawText(int(nfz_x + 6), int(nfz_y + 16), "NFZ BUFFER")

        # 2. Vertiport Pad 1
        vp_x = center_x + self.vertiport_pos["x"] * (radius / 250.0)
        vp_y = center_y + self.vertiport_pos["y"] * (radius / 250.0)
        painter.setPen(QPen(QColor(48, 209, 88), 2))
        painter.setBrush(QBrush(QColor(48, 209, 88, 120)))
        painter.drawEllipse(QPointF(vp_x, vp_y), 5, 5)
        painter.setPen(QPen(QColor(48, 209, 88)))
        painter.setFont(QFont("Monospace", 7))
        painter.drawText(int(vp_x + 8), int(vp_y + 4), "Vertiport Pad 1")

        # 3. Scenario-Specific Entities
        if self.active_scenario == 1:
            # HEMS Manned Helicopter Incursion
            hx = center_x + self.hems_pos["x"] * (radius / 250.0)
            hy = center_y + self.hems_pos["y"] * (radius / 250.0)
            # Flashing red ring
            flash_alpha = int(180 + 75 * math.sin(time.time() * 8))
            painter.setPen(QPen(QColor(255, 69, 58, flash_alpha), 2))
            painter.setBrush(QBrush(QColor(255, 69, 58, 60)))
            painter.drawEllipse(QPointF(hx, hy), 9, 9)
            painter.setBrush(QBrush(QColor(255, 69, 58)))
            painter.drawEllipse(QPointF(hx, hy), 4, 4)
            painter.setFont(QFont("Monospace", 8, QFont.Bold))
            painter.drawText(int(hx + 12), int(hy + 4), "HEMS Air Ambulance (820m)")

        elif self.active_scenario == 2:
            # 5G Shadowing Cell Zone
            sx = center_x - 30
            sy = center_y - 70
            painter.setPen(QPen(QColor(255, 159, 10, 180), 1.5, Qt.DashDotLine))
            painter.setBrush(QBrush(QColor(255, 159, 10, 30)))
            painter.drawEllipse(QPointF(sx, sy), 45, 45)
            painter.setPen(QPen(QColor(255, 159, 10)))
            painter.setFont(QFont("Monospace", 7, QFont.Bold))
            painter.drawText(int(sx - 35), int(sy), "5G SHADOW CELL")

        # 4. Our UAS Flight (Drone)
        dx = center_x + (self.drone_pos["x"] * 10)
        dy = center_y - (self.drone_pos["y"] * 10)
        # Pulsing Cyan Halo
        pulse_r = 7.0 + 3.0 * math.sin(time.time() * 6)
        painter.setPen(QPen(QColor(0, 243, 255, 120), 1.5))
        painter.setBrush(QBrush(QColor(0, 243, 255, 40)))
        painter.drawEllipse(QPointF(dx, dy), pulse_r, pulse_r)
        # Core icon
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QBrush(QColor(0, 243, 255)))
        painter.drawEllipse(QPointF(dx, dy), 4.5, 4.5)
        # Label
        painter.setFont(QFont("Monospace", 8, QFont.Bold))
        painter.setPen(QPen(QColor(0, 243, 255)))
        painter.drawText(int(dx + 12), int(dy + 4), f"UAS-104 ({self.drone_pos['z']:.2f}m)")

        # Title Overlay
        painter.setFont(QFont("Sans-Serif", 8, QFont.Bold))
        painter.setPen(QPen(QColor(160, 180, 205)))
        painter.drawText(15, 22, "TACTICAL AIRSPACE RADAR (DUBAI BVLOS CORRIDOR)")


# ==============================================================================
# AeroGrid Main GUI Window (PyQt5)
# ==============================================================================
class AeroGridTacticalHUD(QMainWindow):
    """Integrated Tactical Multi-Agent UTM Mission Control Center."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroGrid UTM - Tactical Multi-Agent Mission Control [ITU AI for Good]")
        self.resize(1340, 880)
        self.setMinimumSize(1100, 720)

        # 1. Initialize UTM Engines
        self.audit_engine = AuditEngine(db_path=os.path.join(WORKSPACE_ROOT, "backend/audit/aerogrid_audit.db"))
        self.retriever = PolicyRetriever(chroma_persist_dir=os.path.join(WORKSPACE_ROOT, "backend/knowledge_base/vector_db"))
        self.aviation_agent = AviationAgent(llm_client=None, retriever=self.retriever)
        self.telecom_agent = TelecomAgent(llm_client=None, retriever=self.retriever)
        self.fleet_agent = FleetAgent(llm_client=None, retriever=self.retriever)
        self.coordination_engine = CoordinationEngine(audit_engine=self.audit_engine)

        # 2. ZeroMQ Bridge
        self.zmq_bridge = CoppeliaZMQBridge()
        self.zmq_bridge.connect()

        # UI State
        self.current_scenario_idx = 1
        self._build_ui()
        self._apply_dark_theme()

        # Telemetry Polling Timer (10 Hz)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_telemetry)
        self.poll_timer.start(100)

        # Initial scenario run (Start in safe Nominal Cruise Hover!)
        self.run_scenario(0)

    def _build_ui(self):
        """Build responsive desktop layout."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Top Header Bar: Title + Scenario Switcher Buttons
        # ----------------------------------------------------------------------
        header_bar = QHBoxLayout()

        title_col = QVBoxLayout()
        title_lbl = QLabel("AEROGRID UTM")
        title_lbl.setObjectName("appTitle")
        title_sub = QLabel("MODULAR MULTI-AGENT UNMANNED TRAFFIC MANAGEMENT • ITU AI FOR GOOD")
        title_sub.setObjectName("appSubtitle")
        title_col.addWidget(title_lbl)
        title_col.addWidget(title_sub)
        header_bar.addLayout(title_col)

        header_bar.addStretch()

        # Scenario Buttons
        self.btn_scen0 = QPushButton("0: Nominal Cruise (2.0m)")
        self.btn_scen1 = QPushButton("1: HEMS Emergency")
        self.btn_scen2 = QPushButton("2: Urban 5G Shadow")
        self.btn_scen3 = QPushButton("3: Battery Divert")

        for idx, btn in enumerate([self.btn_scen0, self.btn_scen1, self.btn_scen2, self.btn_scen3], start=0):
            btn.setObjectName("scenarioBtn")
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda checked, s=idx: self.run_scenario(s))
            header_bar.addWidget(btn)

        main_layout.addLayout(header_bar)

        # ----------------------------------------------------------------------
        # Telemetry Quick-Bar
        # ----------------------------------------------------------------------
        telem_bar = QHBoxLayout()
        telem_bar.setSpacing(8)

        self.card_alt = self._create_telem_card("ALTITUDE", "120 m", "#00f3ff")
        self.card_spd = self._create_telem_card("GROUND SPEED", "22.5 m/s", "#ffffff")
        self.card_bat = self._create_telem_card("BATTERY SOC", "21.5%", "#ff9f0a")
        self.card_rtt = self._create_telem_card("C2 RTT LATENCY", "42 ms", "#30d158")
        self.card_loss = self._create_telem_card("PACKET LOSS", "0.10%", "#30d158")
        self.card_zmq = self._create_telem_card("COPPELIASIM ZMQ", "STANDBY", "#a0b4cd")

        for card in [self.card_alt, self.card_spd, self.card_bat, self.card_rtt, self.card_loss, self.card_zmq]:
            telem_bar.addWidget(card)

        main_layout.addLayout(telem_bar)

        # ----------------------------------------------------------------------
        # Middle Split: Airspace Radar (Left) + Multi-Agent Cards (Right)
        # ----------------------------------------------------------------------
        mid_splitter = QSplitter(Qt.Horizontal)
        mid_splitter.setHandleWidth(8)

        # Left Column: Radar + CoppeliaSim ZMQ Controls
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.radar_widget = AirspaceRadarWidget()
        left_layout.addWidget(self.radar_widget, stretch=4)

        # ZMQ Controls Row
        zmq_ctrl_row = QHBoxLayout()
        self.btn_connect_zmq = QPushButton("Connect CoppeliaSim ZMQ")
        self.btn_connect_zmq.setObjectName("actionBtn")
        self.btn_connect_zmq.clicked.connect(self._manual_connect_zmq)

        self.btn_land = QPushButton("Force Land (0.05m)")
        self.btn_land.setObjectName("actionBtn")
        self.btn_land.clicked.connect(lambda: self._manual_set_z(0.05))

        self.btn_hover = QPushButton("Hover Setpoint (2.0m)")
        self.btn_hover.setObjectName("actionBtn")
        self.btn_hover.clicked.connect(lambda: self._manual_set_z(2.0))

        zmq_ctrl_row.addWidget(self.btn_connect_zmq)
        zmq_ctrl_row.addWidget(self.btn_land)
        zmq_ctrl_row.addWidget(self.btn_hover)
        left_layout.addLayout(zmq_ctrl_row)

        mid_splitter.addWidget(left_box)

        # Right Column: Multi-Agent Recommendation Cards
        agent_box = QWidget()
        agent_layout = QVBoxLayout(agent_box)
        agent_layout.setContentsMargins(0, 0, 0, 0)
        agent_layout.setSpacing(8)

        # Agent Cards
        self.aviation_card = self._create_agent_card(
            title="Aviation Safety Agent (Tier 1)",
            badge="Conf: 0.98",
            action="EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION",
            justification="Immediate right-of-way yielding required for manned medical helicopter (HEMS) at 820m.",
            citations="UAE Federal Decree-Law No. 26 Art. 14 • GCAA CAR Part IV UAS.406",
            accent_color="#ff453a",
        )
        self.telecom_card = self._create_agent_card(
            title="Telecom C2 Agent (Tier 2)",
            badge="Conf: 0.92",
            action="MAINTAIN_C2_COMMUNICATIONS_PROFILE",
            justification="C2 aeronautical spectrum parameters nominal (RTT=42ms, loss<0.1%). Operating within TDRA QoS bounds.",
            citations="TDRA UAE Spectrum Guidelines Sec 5.2 • 5030-5091 MHz",
            accent_color="#00f3ff",
        )
        self.fleet_card = self._create_agent_card(
            title="Fleet Operations Agent (Tier 3)",
            badge="Conf: 0.88",
            action="THROTTLE_BACK_TO_MAX_ENDURANCE_SPEED_AVOID_EXTRA_MANEUVERS",
            justification="Battery at 21.5% approaching 20% reserve threshold. Recommend straight-line cruise to conserve energy.",
            citations="AeroGrid Fleet SOP Sec 4.2 • Delivery SLA Priority",
            accent_color="#ff9f0a",
        )

        agent_layout.addWidget(self.aviation_card)
        agent_layout.addWidget(self.telecom_card)
        agent_layout.addWidget(self.fleet_card)

        mid_splitter.addWidget(agent_box)
        mid_splitter.setStretchFactor(0, 5)
        mid_splitter.setStretchFactor(1, 5)

        main_layout.addWidget(mid_splitter, stretch=5)

        # ----------------------------------------------------------------------
        # Coordination Engine Arbitration Verdict Card
        # ----------------------------------------------------------------------
        self.verdict_card = QFrame()
        self.verdict_card.setObjectName("verdictCard")
        v_layout = QVBoxLayout(self.verdict_card)
        v_layout.setContentsMargins(14, 10, 14, 10)
        v_layout.setSpacing(4)

        v_head = QHBoxLayout()
        v_title = QLabel("COORDINATION ENGINE ARBITRATION VERDICT")
        v_title.setObjectName("verdictTitle")
        self.v_tier_badge = QLabel("TIER 1 SAFETY ENFORCED")
        self.v_tier_badge.setObjectName("tierBadge")
        v_head.addWidget(v_title)
        v_head.addWidget(self.v_tier_badge)
        v_head.addStretch()

        self.ros_topic_lbl = QLabel("ROS 2 TOPIC: /aerogrid/utm_commands • STATUS: ACTUATED")
        self.ros_topic_lbl.setObjectName("rosTopic")
        v_head.addWidget(self.ros_topic_lbl)
        v_layout.addLayout(v_head)

        self.v_action = QLabel("EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")
        self.v_action.setObjectName("verdictAction")
        v_layout.addWidget(self.v_action)

        self.v_justification = QLabel(
            "ARBITRATION DECISION: Tier 1 Airspace Safety Priority Enforced pursuant to ASTM F3411 and UAE Federal Decree-Law No. 26 Art. 14."
        )
        self.v_justification.setObjectName("verdictJustification")
        self.v_justification.setWordWrap(True)
        v_layout.addWidget(self.v_justification)

        self.v_overruled = QLabel("Overruled: [fleet_ops_agent] 'THROTTLE_BACK' (Subordinated to life-safety separation minima).")
        self.v_overruled.setObjectName("verdictOverruled")
        v_layout.addWidget(self.v_overruled)

        main_layout.addWidget(self.verdict_card, stretch=2)

        # ----------------------------------------------------------------------
        # Bottom: SQLite WAL Audit Log Table
        # ----------------------------------------------------------------------
        self.audit_table = QTableWidget(0, 5)
        self.audit_table.setObjectName("auditTable")
        self.audit_table.setHorizontalHeaderLabels(["Event ID", "Agent ID", "Parent Decision ID", "Action Directive", "Timestamp"])
        self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.audit_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.audit_table.setMaximumHeight(130)
        main_layout.addWidget(self.audit_table, stretch=2)

    # --------------------------------------------------------------------------
    # Card Builder Helpers
    # --------------------------------------------------------------------------
    def _create_telem_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("telemCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("telemTitle")
        v = QLabel(value)
        v.setObjectName("telemValue")
        v.setStyleSheet(f"color: {color};")
        l.addWidget(t)
        l.addWidget(v)
        card.value_lbl = v
        return card

    def _create_agent_card(self, title: str, badge: str, action: str, justification: str, citations: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("agentCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(4)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("agentTitle")
        b = QLabel(badge)
        b.setObjectName("agentBadge")
        b.setStyleSheet(f"color: {accent_color}; border: 1px solid {accent_color};")
        head.addWidget(t)
        head.addStretch()
        head.addWidget(b)
        l.addLayout(head)

        act = QLabel(action)
        act.setObjectName("agentAction")
        act.setWordWrap(True)
        l.addWidget(act)

        just = QLabel(justification)
        just.setObjectName("agentJustification")
        just.setWordWrap(True)
        l.addWidget(just)

        cit = QLabel(citations)
        cit.setObjectName("agentCitations")
        cit.setWordWrap(True)
        l.addWidget(cit)

        card.badge_lbl = b
        card.action_lbl = act
        card.just_lbl = just
        card.cit_lbl = cit
        return card

    # --------------------------------------------------------------------------
    # Scenario Execution & Coordination Arbitration
    # --------------------------------------------------------------------------
    def run_scenario(self, scenario_idx: int):
        """Execute selected multi-agent conflict scenario and actuate CoppeliaSim."""
        self.current_scenario_idx = scenario_idx
        self.radar_widget.set_scenario(scenario_idx)

        # Highlight active button
        self.btn_scen0.setStyleSheet("background: #30d158; color: #000; font-weight: bold;" if scenario_idx == 0 else "")
        self.btn_scen1.setStyleSheet("background: #ff453a; color: #fff; font-weight: bold;" if scenario_idx == 1 else "")
        self.btn_scen2.setStyleSheet("background: #00f3ff; color: #000; font-weight: bold;" if scenario_idx == 2 else "")
        self.btn_scen3.setStyleSheet("background: #ff9f0a; color: #000; font-weight: bold;" if scenario_idx == 3 else "")

        state = self._build_scenario_state(scenario_idx)
        drone_id = state["drone_id"]

        # Evaluate domain agents
        av_resp = self.aviation_agent.evaluate_state(state)
        tel_resp = self.telecom_agent.evaluate_state(state)
        flt_resp = self.fleet_agent.evaluate_state(state)

        # Resolve conflict
        command = self.coordination_engine.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tel_resp,
            fleet_resp=flt_resp,
            state=state,
            target_drone_id=drone_id,
        )

        # Update UI Cards
        self._update_cards(av_resp, tel_resp, flt_resp, command, state)

        # Actuate via ZeroMQ
        actuation = self.zmq_bridge.execute_utm_action(command.action, drone_id)
        self.ros_topic_lbl.setText(f"ROS 2 TOPIC: /aerogrid/utm_commands • ACTUATION: Z={actuation['target_z']:.2f}m")

        # Refresh Audit Log Table
        self._refresh_audit_table()

    def _build_scenario_state(self, scenario_idx: int) -> dict:
        if scenario_idx == 0:
            # Baseline Nominal BVLOS Cruise (Safe Hover at 2.0m)
            return {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": "2026-11-08T17:00:00Z",
                "altitude_m": 120,
                "ground_speed_mps": 20.0,
                "airspace_traffic": {
                    "manned_traffic_detected": False,
                    "intruder_distance_m": 9999,
                    "corridor_id": "DXB-BVLOS-04",
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 32,
                    "packet_loss_pct": 0.05,
                    "link_lost": False,
                    "urban_canyon_shadowing": False,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "battery_soc_pct": 82.0,
                    "cargo_type": "standard_parcel",
                    "expedited_medical_payload": False,
                },
            }
        elif scenario_idx == 1:
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
                "telecom_metrics": {
                    "rtt_latency_ms": 42,
                    "packet_loss_pct": 0.1,
                    "link_lost": False,
                    "urban_canyon_shadowing": False,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "battery_soc_pct": 21.5,
                    "cargo_type": "standard_parcel",
                    "expedited_medical_payload": False,
                },
            }
        elif scenario_idx == 2:
            return {
                "drone_id": "UAS_DELIVERY_AUH_209",
                "timestamp": "2026-11-08T17:05:00Z",
                "altitude_m": 90,
                "ground_speed_mps": 18.0,
                "airspace_traffic": {
                    "manned_traffic_detected": False,
                    "intruder_distance_m": 4500,
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 295,
                    "packet_loss_pct": 3.8,
                    "link_lost": False,
                    "urban_canyon_shadowing": True,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_DELIVERY_AUH_209",
                    "battery_soc_pct": 58.0,
                    "cargo_type": "high_value_retail",
                    "expedited_medical_payload": False,
                },
            }
        else:
            return {
                "drone_id": "UAS_MED_SHJ_311",
                "timestamp": "2026-11-08T17:10:00Z",
                "altitude_m": 105,
                "ground_speed_mps": 15.0,
                "airspace_traffic": {
                    "manned_traffic_detected": False,
                    "intruder_distance_m": 6000,
                },
                "telecom_metrics": {
                    "rtt_latency_ms": 38,
                    "packet_loss_pct": 0.05,
                    "link_lost": False,
                    "urban_canyon_shadowing": False,
                },
                "fleet_telemetry": {
                    "drone_id": "UAS_MED_SHJ_311",
                    "battery_soc_pct": 14.2,
                    "cargo_type": "emergency_antivenom",
                    "expedited_medical_payload": True,
                },
            }

    def _update_cards(self, av_resp, tel_resp, flt_resp, command, state):
        # Update Telemetry Bar
        alt_str = "120 m" if self.current_scenario_idx != 1 else "LANDED (0.05m)"
        self.card_alt.value_lbl.setText(alt_str)
        self.card_spd.value_lbl.setText(f"{state['ground_speed_mps']:.1f} m/s")
        self.card_bat.value_lbl.setText(f"{state['fleet_telemetry']['battery_soc_pct']:.1f}%")
        self.card_rtt.value_lbl.setText(f"{state['telecom_metrics']['rtt_latency_ms']:.0f} ms")
        self.card_loss.value_lbl.setText(f"{state['telecom_metrics']['packet_loss_pct']:.2f}%")

        # Aviation Agent Card
        self.aviation_card.badge_lbl.setText(f"Conf: {av_resp.confidence:.2f}")
        self.aviation_card.action_lbl.setText(av_resp.recommended_action)
        self.aviation_card.just_lbl.setText(av_resp.justification)
        self.aviation_card.cit_lbl.setText(" • ".join(av_resp.policy_citations))

        # Telecom C2 Agent Card
        self.telecom_card.badge_lbl.setText(f"Conf: {tel_resp.confidence:.2f}")
        self.telecom_card.action_lbl.setText(tel_resp.recommended_action)
        self.telecom_card.just_lbl.setText(tel_resp.justification)
        self.telecom_card.cit_lbl.setText(" • ".join(tel_resp.policy_citations))

        # Fleet Ops Agent Card
        self.fleet_card.badge_lbl.setText(f"Conf: {flt_resp.confidence:.2f}")
        self.fleet_card.action_lbl.setText(flt_resp.recommended_action)
        self.fleet_card.just_lbl.setText(flt_resp.justification)
        self.fleet_card.cit_lbl.setText(" • ".join(flt_resp.policy_citations))

        # Verdict Card
        self.v_action.setText(command.action)
        self.v_justification.setText(command.justification)
        if command.overruled_recommendations:
            overruled_str = " • ".join([f"[{ov.get('agent_id')}] '{ov.get('action')}'" for ov in command.overruled_recommendations])
            self.v_overruled.setText(f"Overruled: {overruled_str}")
        else:
            self.v_overruled.setText("Consensus reached: No domain recommendations were overruled.")

        # Priority badge text
        if self.current_scenario_idx == 0:
            self.v_tier_badge.setText("NOMINAL BVLOS CORRIDOR CRUISE (STABLE HOVER)")
            self.v_tier_badge.setStyleSheet("color: #30d158; border: 1px solid #30d158;")
        elif self.current_scenario_idx == 1:
            self.v_tier_badge.setText("TIER 1 AIRSPACE LAW ENFORCED")
            self.v_tier_badge.setStyleSheet("color: #ff453a; border: 1px solid #ff453a;")
        elif self.current_scenario_idx == 2:
            self.v_tier_badge.setText("TIER 2 C2 QoS LINK ENFORCED")
            self.v_tier_badge.setStyleSheet("color: #00f3ff; border: 1px solid #00f3ff;")
        else:
            self.v_tier_badge.setText("TIER 3 FLEET SAFETY APPROVED")
            self.v_tier_badge.setStyleSheet("color: #ff9f0a; border: 1px solid #ff9f0a;")

    def _poll_telemetry(self):
        """Periodic poll of CoppeliaSim ZeroMQ telemetry."""
        telem = self.zmq_bridge.read_telemetry()
        if telem["connected"]:
            self.card_zmq.value_lbl.setText("CONNECTED (ZMQ)")
            self.card_zmq.value_lbl.setStyleSheet("color: #30d158;")
            self.card_alt.value_lbl.setText(f"{telem['z']:.2f} m")
            self.radar_widget.update_drone_telemetry(telem["x"], telem["y"], telem["z"])
        else:
            self.card_zmq.value_lbl.setText("STANDBY")
            self.card_zmq.value_lbl.setStyleSheet("color: #a0b4cd;")

    def _manual_connect_zmq(self):
        res = self.zmq_bridge.connect()
        if res:
            self.card_zmq.value_lbl.setText("CONNECTED (ZMQ)")
            self.card_zmq.value_lbl.setStyleSheet("color: #30d158;")
            self.zmq_bridge.start_simulation()
        else:
            self.card_zmq.value_lbl.setText("OFFLINE")
            self.card_zmq.value_lbl.setStyleSheet("color: #ff453a;")

    def _manual_set_z(self, z_alt: float):
        self.zmq_bridge.set_target_altitude(z_alt)
        self.card_alt.value_lbl.setText(f"{z_alt:.2f} m")
        self.ros_topic_lbl.setText(f"MANUAL ACTUATION: Target Z set to {z_alt:.2f}m")

    def _refresh_audit_table(self):
        """Fetch latest SQLite WAL records and update QTableWidget."""
        try:
            conn = self.audit_engine._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT event_id, agent_id, parent_decision_id, recommended_action, timestamp
                FROM audit_logs
                ORDER BY rowid DESC LIMIT 12
            """)
            rows = cursor.fetchall()
            self.audit_table.setRowCount(len(rows))
            for r_idx, row in enumerate(rows):
                for c_idx, val in enumerate(row):
                    item = QTableWidgetItem(str(val or ""))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.audit_table.setItem(r_idx, c_idx, item)
        except Exception as e:
            pass

    # --------------------------------------------------------------------------
    # Dark Theme Modern Aerospace Styling
    # --------------------------------------------------------------------------
    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #080c14;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'DejaVu Sans', sans-serif;
            }
            #appTitle {
                font-size: 20px;
                font-weight: 800;
                color: #00f3ff;
                letter-spacing: 1.5px;
            }
            #appSubtitle {
                font-size: 9px;
                font-weight: 600;
                color: #718096;
                letter-spacing: 1px;
            }
            #scenarioBtn {
                background-color: #111a2e;
                color: #00f3ff;
                border: 1px solid #1a2c4e;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 700;
            }
            #scenarioBtn:hover {
                background-color: #1a2c4e;
                border-color: #00f3ff;
            }
            #telemCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
            #telemTitle {
                font-size: 8px;
                font-weight: 700;
                color: #94a3b8;
                letter-spacing: 0.8px;
            }
            #telemValue {
                font-size: 14px;
                font-weight: 800;
                font-family: 'Monospace';
            }
            #agentCard {
                background-color: #0b1325;
                border: 1px solid #1a284a;
                border-radius: 6px;
            }
            #agentTitle {
                font-size: 11px;
                font-weight: 800;
                color: #e2e8f0;
            }
            #agentBadge {
                font-size: 9px;
                font-weight: 700;
                padding: 1px 6px;
                border-radius: 3px;
                font-family: 'Monospace';
            }
            #agentAction {
                font-size: 11px;
                font-weight: 700;
                color: #38bdf8;
                font-family: 'Monospace';
            }
            #agentJustification {
                font-size: 10px;
                color: #cbd5e1;
            }
            #agentCitations {
                font-size: 8px;
                color: #64748b;
                font-style: italic;
            }
            #verdictCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f1d38, stop:1 #091224);
                border: 1.5px solid #00f3ff;
                border-radius: 6px;
            }
            #verdictTitle {
                font-size: 10px;
                font-weight: 800;
                color: #94a3b8;
                letter-spacing: 1px;
            }
            #tierBadge {
                font-size: 9px;
                font-weight: 800;
                padding: 1px 6px;
                border-radius: 3px;
                font-family: 'Monospace';
            }
            #rosTopic {
                font-size: 9px;
                color: #38bdf8;
                font-family: 'Monospace';
                font-weight: 600;
            }
            #verdictAction {
                font-size: 14px;
                font-weight: 800;
                color: #00f3ff;
                font-family: 'Monospace';
            }
            #verdictJustification {
                font-size: 10.5px;
                color: #e2e8f0;
            }
            #verdictOverruled {
                font-size: 9.5px;
                color: #f87171;
                font-style: italic;
            }
            #actionBtn {
                background-color: #111a2e;
                color: #e2e8f0;
                border: 1px solid #1a2c4e;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 600;
            }
            #actionBtn:hover {
                background-color: #1e3a6a;
                border-color: #38bdf8;
            }
            #auditTable {
                background-color: #090f1d;
                border: 1px solid #1a284a;
                border-radius: 6px;
                gridline-color: #152238;
                font-size: 9.5px;
                font-family: 'Monospace';
            }
            #auditTable QHeaderView::section {
                background-color: #0f1a30;
                color: #94a3b8;
                font-size: 9px;
                font-weight: 700;
                padding: 4px;
                border: 1px solid #152238;
            }
        """)


def main():
    app = QApplication(sys.argv)
    window = AeroGridTacticalHUD()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
