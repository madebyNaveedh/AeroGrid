#!/usr/bin/env python3
"""AeroGrid UTM - Tactical Mission Control Glass Cockpit HUD (Phase 4).

High-contrast aerospace Glass Cockpit HUD matching the exact design
of the AeroGrid web console. Directly connects Python multi-agent deliberation
with CoppeliaSim ZeroMQ actuation (port 23000), SQLite WAL auditing, and
ROS 2 Humble topic publishing.
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Dict, List, Optional

os.environ.setdefault("HF_HUB_OFFLINE", "1")

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
    QGraphicsDropShadowEffect,
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

# Workspace and backend imports
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(WORKSPACE_ROOT)
for p in [PROJECT_ROOT, WORKSPACE_ROOT, os.path.join(PROJECT_ROOT, "py_packages")]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine
from backend.simulation.coppelia_zmq_bridge import CoppeliaZMQBridge, get_coppelia_bridge


# ==============================================================================
# Tactical Airspace Radar Map (Glass Cockpit)
# ==============================================================================
class GlassCockpitRadar(QWidget):
    """30 FPS Tactical Airspace Radar matching the AeroGrid HUD aesthetic with dual-drone fleet support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sweep_angle = 0.0
        self.active_scenario = 0
        self.drone1_pos = {"x": 0.0, "y": 0.0, "z": 2.0}
        self.drone2_pos = {"x": 1.2, "y": 0.6, "z": 2.6}
        self.drone_pos = {"x": 0.0, "y": 0.0, "z": 2.0}

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(33)  # ~30 FPS

    def set_scenario(self, scenario_idx: int):
        self.active_scenario = scenario_idx
        self.update()

    def update_drone_pos(self, pos: dict):
        self.drone_pos = pos
        self.drone1_pos = pos
        self.update()

    def update_fleet_telemetry(self, telem: dict):
        if "drone1" in telem:
            self.drone1_pos = telem["drone1"]
            self.drone_pos = telem["drone1"]
        elif "x" in telem:
            self.drone1_pos = telem
            self.drone_pos = telem

        if "drone2" in telem:
            self.drone2_pos = telem["drone2"]
        self.update()

    def _tick(self):
        self.sweep_angle = (self.sweep_angle + 2.5) % 360.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(cx, cy) - 20.0

        # Radar Backdrop
        p.fillRect(0, 0, w, h, QColor("#060911"))

        # Concentric Distance Rings
        ring_pen = QPen(QColor("#2d3748"), 1)
        p.setPen(ring_pen)
        p.setBrush(Qt.NoBrush)

        rings = [(0.35, "250m"), (0.65, "500m"), (0.95, "1000m")]
        p.setFont(QFont("Monospace", 8))
        for frac, label in rings:
            r = radius * frac
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QPen(QColor(160, 174, 192, 120)))
            p.drawText(int(cx + 6), int(cy - r + 12), label)
            p.setPen(ring_pen)

        # Crosshairs
        p.setPen(QPen(QColor("#2d3748"), 1))
        p.drawLine(int(cx - radius), int(cy), int(cx + radius), int(cy))
        p.drawLine(int(cx), int(cy - radius), int(cx), int(cy + radius))

        # Geofence NFZ Buffer Box (Upper Right)
        nfz_w, nfz_h = 100, 75
        nfz_x, nfz_y = cx + 60, cy - 110
        nfz_pen = QPen(QColor(245, 101, 101, 140), 1, Qt.DashLine)
        p.setPen(nfz_pen)
        p.setBrush(QBrush(QColor(245, 101, 101, 20)))
        p.drawRect(int(nfz_x), int(nfz_y), nfz_w, nfz_h)
        p.setFont(QFont("Monospace", 7, QFont.Bold))
        p.setPen(QPen(QColor("#f56565")))
        p.drawText(int(nfz_x + 6), int(nfz_y + 14), "NFZ BUFFER (500m)")

        # Vertiport Pad 1 (Lower Left)
        vp_x, vp_y = cx - 110, cy + 75
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#48bb78")))
        p.drawEllipse(QPointF(vp_x, vp_y), 5, 5)
        p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
        p.setPen(QPen(QColor("#48bb78")))
        p.drawText(int(vp_x + 10), int(vp_y + 4), "Vertiport Pad 1")

        # Scenario 2: 5G Shadow Zone
        if self.active_scenario == 2:
            sh_x, sh_y = cx + 40, cy - 40
            p.setPen(QPen(QColor("#4299e1"), 1, Qt.DashLine))
            p.setBrush(QBrush(QColor(66, 153, 225, 25)))
            p.drawRect(int(sh_x), int(sh_y), 80, 80)
            p.setFont(QFont("Monospace", 7))
            p.setPen(QPen(QColor("#4299e1")))
            p.drawText(int(sh_x + 6), int(sh_y + 14), "5G CELL SHADOW")

        # ----------------------------------------------------------------------
        # Fleet Drone 1: Primary Flight (UAS_CARGO_DXB_104)
        # ----------------------------------------------------------------------
        d1_x = cx + float(self.drone1_pos.get("x", 0.0)) * 40.0
        d1_y = cy - float(self.drone1_pos.get("y", 0.0)) * 40.0
        d1_z = float(self.drone1_pos.get("z", 2.0))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#00f2fe")))
        p.drawEllipse(QPointF(d1_x, d1_y), 5, 5)

        p.setPen(QPen(QColor(0, 242, 254, 120), 1.8))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(d1_x, d1_y), 12, 12)

        p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
        p.setPen(QPen(QColor("#00f2fe")))
        if d1_z <= 0.15:
            p.drawText(int(d1_x + 16), int(d1_y + 4), f"UAS-104 [GROUNDED - YIELDING] ({d1_z:.2f}m)")
        else:
            p.drawText(int(d1_x + 16), int(d1_y + 4), f"UAS-104 (Our Flight) [{d1_z:.2f}m]")

        # ----------------------------------------------------------------------
        # Fleet Drone 2: HEMS Manned Incursion / Peer Commercial UAS
        # ----------------------------------------------------------------------
        d2_x = cx + float(self.drone2_pos.get("x", 1.2)) * 40.0
        d2_y = cy - float(self.drone2_pos.get("y", 0.6)) * 40.0
        d2_z = float(self.drone2_pos.get("z", 2.6))

        if self.active_scenario == 1:
            # Red Manned Intruder Marker
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor("#f56565")))
            p.drawEllipse(QPointF(d2_x, d2_y), 6, 6)

            p.setPen(QPen(QColor(245, 101, 101, 150), 1.8))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(d2_x, d2_y), 14, 14)

            # Proximity separation vector between Drone 1 and HEMS
            dash_red = QPen(QColor(245, 101, 101, 160), 1.2, Qt.DashLine)
            p.setPen(dash_red)
            p.drawLine(QPointF(d1_x, d1_y), QPointF(d2_x, d2_y))

            # Label
            p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
            p.setPen(QPen(QColor("#f56565")))
            p.drawText(int(d2_x + 16), int(d2_y + 4), f"HEMS Air Ambulance (Manned) [{d2_z:.2f}m]")
        else:
            # Amber Peer Fleet Marker
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor("#ed8936")))
            p.drawEllipse(QPointF(d2_x, d2_y), 5, 5)

            p.setPen(QPen(QColor(237, 137, 54, 120), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(d2_x, d2_y), 12, 12)

            # Label
            p.setFont(QFont("Sans-Serif", 8, QFont.Bold))
            p.setPen(QPen(QColor("#ed8936")))
            p.drawText(int(d2_x + 16), int(d2_y + 4), f"UAS-209 (Peer Fleet) [{d2_z:.2f}m]")

        # Radar Sweep Beam
        rad = math.radians(self.sweep_angle)
        sx = cx + radius * math.cos(rad)
        sy = cy + radius * math.sin(rad)
        p.setPen(QPen(QColor(0, 242, 254, 180), 1.5))
        p.drawLine(QPointF(cx, cy), QPointF(sx, sy))

        p.end()


# ==============================================================================
# Glass Cockpit Mission Control HUD Window
# ==============================================================================
class AeroGridTacticalHUD(QMainWindow):
    """Turnkey Mission Control HUD matching the AeroGrid web console."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroGrid UTM - Multi-Agent Airspace Coordination Control")
        self.resize(1280, 780)
        self.setMinimumSize(1080, 680)

        # Initialize Backend Services
        db_path = os.path.join(WORKSPACE_ROOT, "backend/audit/aerogrid_audit.db")
        vector_db = os.path.join(WORKSPACE_ROOT, "backend/knowledge_base/vector_db")

        self.audit_engine = AuditEngine(db_path=db_path)
        self.retriever = PolicyRetriever(chroma_persist_dir=vector_db)
        self.aviation_agent = AviationAgent(llm_client=None, retriever=self.retriever)
        self.telecom_agent = TelecomAgent(llm_client=None, retriever=self.retriever)
        self.fleet_agent = FleetAgent(llm_client=None, retriever=self.retriever)
        self.coordination_engine = CoordinationEngine(audit_engine=self.audit_engine, retriever=self.retriever)

        # Authoritative Shared ZeroMQ CoppeliaSim Bridge
        self.zmq_bridge = get_coppelia_bridge()

        self.current_scenario_idx = 0
        self._build_ui()
        self._apply_theme()

        # Telemetry Poller (10 Hz)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_telemetry)
        self.poll_timer.start(100)

        # Startup in Nominal Cruise (Scenario 0)
        self.run_scenario(0)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # ----------------------------------------------------------------------
        # Top Header: Title + Scenario Selector Buttons
        # ----------------------------------------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        h1 = QLabel("AEROGRID UTM")
        h1.setObjectName("mainTitle")
        sub_badge = QLabel("ITU AI FOR GOOD HACKATHON")
        sub_badge.setObjectName("badgeItu")
        title_box.addWidget(h1)
        title_box.addWidget(sub_badge)
        header.addLayout(title_box)

        header.addStretch()

        # Scenario Buttons
        scen_box = QHBoxLayout()
        scen_box.setSpacing(8)
        scen_lbl = QLabel("SCENARIOS:")
        scen_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #a0aec0;")
        scen_box.addWidget(scen_lbl)

        self.btn_scen0 = self._create_scenario_btn("0: Nominal Cruise", 0)
        self.btn_scen1 = self._create_scenario_btn("1: HEMS Emergency", 1)
        self.btn_scen2 = self._create_scenario_btn("2: Urban 5G Shadow", 2)
        self.btn_scen3 = self._create_scenario_btn("3: Battery Divert", 3)

        scen_box.addWidget(self.btn_scen0)
        scen_box.addWidget(self.btn_scen1)
        scen_box.addWidget(self.btn_scen2)
        scen_box.addWidget(self.btn_scen3)
        header.addLayout(scen_box)

        root.addLayout(header)

        # ----------------------------------------------------------------------
        # Main Grid Container (Left: Radar Card + Telemetry | Right: Agents Column)
        # ----------------------------------------------------------------------
        grid = QHBoxLayout()
        grid.setSpacing(14)

        # LEFT: Radar Card
        radar_card = QFrame()
        radar_card.setObjectName("radarCard")
        rc_layout = QVBoxLayout(radar_card)
        rc_layout.setContentsMargins(12, 10, 12, 10)
        rc_layout.setSpacing(8)

        rc_head = QHBoxLayout()
        rc_title = QLabel("Tactical Airspace Map (Dubai Corridor DXB-BVLOS)")
        rc_title.setObjectName("cardHeaderLabel")
        self.target_drone_badge = QLabel("UAS_CARGO_DXB_104")
        self.target_drone_badge.setObjectName("droneBadge")
        rc_head.addWidget(rc_title)
        rc_head.addStretch()
        rc_head.addWidget(self.target_drone_badge)
        rc_layout.addLayout(rc_head)

        self.radar = GlassCockpitRadar()
        rc_layout.addWidget(self.radar, stretch=1)

        # Telemetry Row (5 horizontal boxes)
        telem_row = QHBoxLayout()
        telem_row.setSpacing(8)
        self.t_alt = self._create_telem_box("ALTITUDE", "120m")
        self.t_speed = self._create_telem_box("GROUND SPEED", "22.5 m/s")
        self.t_soc = self._create_telem_box("BATTERY SOC", "82.0%")
        self.t_rtt = self._create_telem_box("C2 RTT LATENCY", "35 ms")
        self.t_loss = self._create_telem_box("PACKET LOSS", "0.05%")

        telem_row.addWidget(self.t_alt)
        telem_row.addWidget(self.t_speed)
        telem_row.addWidget(self.t_soc)
        telem_row.addWidget(self.t_rtt)
        telem_row.addWidget(self.t_loss)
        rc_layout.addLayout(telem_row)

        grid.addWidget(radar_card, stretch=6)

        # RIGHT: Agents Column (380px fixed width style)
        agents_col = QVBoxLayout()
        agents_col.setSpacing(10)

        self.card_av = self._create_agent_card(
            agent_title="Aviation Safety Agent",
            theme_color="#f56565",
            conf_text="Conf: 0.98",
            action_text="EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION",
            just_text="Immediate right-of-way yielding required for manned medical helicopter (HEMS) detected at 820m.",
            citations=["UAE Law 26 Art. 14", "GCAA CAR.UAS.405"],
        )
        self.card_tc = self._create_agent_card(
            agent_title="Telecom C2 Agent",
            theme_color="#4299e1",
            conf_text="Conf: 0.92",
            action_text="MAINTAIN_C2_COMMUNICATIONS_PROFILE",
            just_text="C2 aeronautical spectrum parameters nominal (RTT=42ms, Loss=0.1%). Operating within TDRA QoS bounds.",
            citations=["TDRA 5030-5091 MHz"],
        )
        self.card_fl = self._create_agent_card(
            agent_title="Fleet Operations Agent",
            theme_color="#ecc94b",
            conf_text="Conf: 0.88",
            action_text="THROTTLE_BACK_TO_MAX_ENDURANCE_SPEED_AVOID_EXTRA_MANEUVERS",
            just_text="Battery at 21.5% approaching 20% reserve threshold. Recommend straight-in cruise to conserve power.",
            citations=["AeroGrid Fleet SOP 4.2"],
        )

        agents_col.addWidget(self.card_av)
        agents_col.addWidget(self.card_tc)
        agents_col.addWidget(self.card_fl)

        grid.addLayout(agents_col, stretch=4)
        root.addLayout(grid, stretch=6)

        # ----------------------------------------------------------------------
        # Coordination Engine Arbitration Verdict Banner
        # ----------------------------------------------------------------------
        self.coord_banner = QFrame()
        self.coord_banner.setObjectName("coordBanner")
        cb_layout = QHBoxLayout(self.coord_banner)
        cb_layout.setContentsMargins(14, 10, 14, 10)
        cb_layout.setSpacing(12)

        cb_left = QVBoxLayout()
        cb_left.setSpacing(3)
        cb_title = QLabel("Coordination Engine Arbitration Verdict")
        cb_title.setObjectName("cbTitle")
        self.coord_action_lbl = QLabel("EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")
        self.coord_action_lbl.setObjectName("coordAction")
        self.coord_just_lbl = QLabel("Tier 1 Airspace Safety Priority Enforced pursuant to ASTM F3411 and UAE Federal Decree-Law No. 26 Art. 14.")
        self.coord_just_lbl.setObjectName("coordJust")
        self.coord_just_lbl.setWordWrap(True)
        self.coord_overruled_lbl = QLabel("Overruled: [fleet_ops_agent] 'THROTTLE_BACK_TO_MAX_ENDURANCE_SPEED_AVOID_EXTRA_MANEUVERS' — Subordinated to life-safety separation minima.")
        self.coord_overruled_lbl.setObjectName("coordOverruled")
        self.coord_overruled_lbl.setWordWrap(True)

        cb_left.addWidget(cb_title)
        cb_left.addWidget(self.coord_action_lbl)
        cb_left.addWidget(self.coord_just_lbl)
        cb_left.addWidget(self.coord_overruled_lbl)
        cb_layout.addLayout(cb_left, stretch=8)

        cb_right = QVBoxLayout()
        cb_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cb_right.setSpacing(3)
        ros_hdr = QLabel("ROS 2 TOPIC PUBLISHED")
        ros_hdr.setStyleSheet("font-size: 10px; color: #a0aec0; text-align: right;")
        ros_topic = QLabel("/aerogrid/utm_commands")
        ros_topic.setObjectName("rosTopic")
        self.ros_status = QLabel("Status: CONFLICT RESOLVED (Tier 1)")
        self.ros_status.setObjectName("rosStatus")

        cb_right.addWidget(ros_hdr)
        cb_right.addWidget(ros_topic)
        cb_right.addWidget(self.ros_status)
        cb_layout.addLayout(cb_right, stretch=3)

        root.addWidget(self.coord_banner, stretch=2)

        # ----------------------------------------------------------------------
        # Footer: SQLite WAL Status & Audit Event ID
        # ----------------------------------------------------------------------
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)

        wal_box = QHBoxLayout()
        wal_box.setSpacing(6)
        wal_dot = QLabel("●")
        wal_dot.setObjectName("walDot")
        wal_txt = QLabel("SQLite WAL Audit Engine: PRAGMA journal_mode=WAL | Cryptographic Provenance Active")
        wal_txt.setObjectName("walText")
        wal_box.addWidget(wal_dot)
        wal_box.addWidget(wal_txt)
        footer.addLayout(wal_box)

        footer.addStretch()

        self.audit_event_lbl = QLabel("Audit Event ID: evt_f8de8509874447cb9ef4002c47dd968d")
        self.audit_event_lbl.setObjectName("auditEventId")
        footer.addWidget(self.audit_event_lbl)

        root.addLayout(footer)

    # --------------------------------------------------------------------------
    # Component Helpers
    # --------------------------------------------------------------------------
    def _create_scenario_btn(self, title: str, idx: int) -> QPushButton:
        btn = QPushButton(title)
        btn.setObjectName("scenBtn")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(lambda: self.run_scenario(idx))
        btn.idx = idx
        return btn

    def _create_telem_box(self, label: str, val: str) -> QFrame:
        box = QFrame()
        box.setObjectName("telemBox")
        l = QVBoxLayout(box)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(2)

        lbl = QLabel(label)
        lbl.setObjectName("telemLabel")
        v = QLabel(val)
        v.setObjectName("telemValue")

        l.addWidget(lbl)
        l.addWidget(v)
        box.val_lbl = v
        return box

    def _create_agent_card(self, agent_title: str, theme_color: str, conf_text: str, action_text: str, just_text: str, citations: List[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("agentCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 10, 12, 10)
        l.setSpacing(5)

        # Header: Name + Conf pill
        h = QHBoxLayout()
        t = QLabel(agent_title)
        t.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {theme_color};")
        c = QLabel(conf_text)
        c.setObjectName("confPill")
        h.addWidget(t)
        h.addStretch()
        h.addWidget(c)
        l.addLayout(h)

        # Action
        act = QLabel(action_text)
        act.setObjectName("agentAction")
        act.setWordWrap(True)
        l.addWidget(act)

        # Justification
        jst = QLabel(just_text)
        jst.setObjectName("agentJust")
        jst.setWordWrap(True)
        l.addWidget(jst)

        # Citations row
        cit_layout = QHBoxLayout()
        cit_layout.setSpacing(6)
        card.cit_layout = cit_layout
        for cit in citations:
            tag = QLabel(cit)
            tag.setObjectName("citationTag")
            cit_layout.addWidget(tag)
        cit_layout.addStretch()
        l.addLayout(cit_layout)

        card.conf_lbl = c
        card.action_lbl = act
        card.just_lbl = jst
        return card

    # --------------------------------------------------------------------------
    # Live Scenario Execution & ZeroMQ Actuation
    # --------------------------------------------------------------------------
    def run_scenario(self, idx: int):
        self.current_scenario_idx = idx
        self.radar.set_scenario(idx)

        # Update button active states
        for b in [self.btn_scen0, self.btn_scen1, self.btn_scen2, self.btn_scen3]:
            b.setProperty("active", b.idx == idx)
            b.style().unpolish(b)
            b.style().polish(b)

        state = self._get_state_for_scenario(idx)
        drone_id = state["drone_id"]
        self.target_drone_badge.setText(drone_id)

        # Execute Multi-Agent Deliberation
        av_resp = self.aviation_agent.evaluate_state(state)
        tc_resp = self.telecom_agent.evaluate_state(state)
        fl_resp = self.fleet_agent.evaluate_state(state)

        cmd = self.coordination_engine.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=state,
            target_drone_id=drone_id,
        )

        # ZeroMQ Actuation in CoppeliaSim
        act_info = self.zmq_bridge.execute_utm_action(cmd.action, drone_id)

        # Update HUD Metrics
        self.t_alt.val_lbl.setText(f"{state['altitude_m']}m")
        self.t_speed.val_lbl.setText(f"{state['ground_speed_mps']} m/s")
        self.t_soc.val_lbl.setText(f"{state['fleet_telemetry']['battery_soc_pct']}%")
        self.t_rtt.val_lbl.setText(f"{state['telecom_metrics']['rtt_latency_ms']} ms")
        self.t_loss.val_lbl.setText(f"{state['telecom_metrics']['packet_loss_pct']:.2f}%")

        # Update Agent Cards
        self.card_av.action_lbl.setText(av_resp.recommended_action)
        self.card_av.conf_lbl.setText(f"Conf: {av_resp.confidence:.2f}")
        self.card_av.just_lbl.setText(av_resp.justification)

        self.card_tc.action_lbl.setText(tc_resp.recommended_action)
        self.card_tc.conf_lbl.setText(f"Conf: {tc_resp.confidence:.2f}")
        self.card_tc.just_lbl.setText(tc_resp.justification)

        self.card_fl.action_lbl.setText(fl_resp.recommended_action)
        self.card_fl.conf_lbl.setText(f"Conf: {fl_resp.confidence:.2f}")
        self.card_fl.just_lbl.setText(fl_resp.justification)

        # Update Coordination Banner
        self.coord_action_lbl.setText(cmd.action)
        self.coord_just_lbl.setText(cmd.justification)
        if cmd.overruled_recommendations:
            ov = cmd.overruled_recommendations[0]
            self.coord_overruled_lbl.setText(f"Overruled: [{ov.get('agent_id')}] '{ov.get('action')}' — {ov.get('reason')}")
            self.ros_status.setText("Status: CONFLICT RESOLVED (Tier 1)")
        else:
            self.coord_overruled_lbl.setText("Consensus: No agent recommendations overruled.")
            self.ros_status.setText("Status: CONSENSUS NOMINAL")

        if cmd.audit_event_id:
            self.audit_event_lbl.setText(f"Audit Event ID: {cmd.audit_event_id}")

    def _get_state_for_scenario(self, s: int) -> dict:
        if s == 0:
            return {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "altitude_m": 120,
                "ground_speed_mps": 22.5,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 8500, "hems_in_vicinity": False},
                "telecom_metrics": {"rtt_latency_ms": 35, "packet_loss_pct": 0.05, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_CARGO_DXB_104", "battery_soc_pct": 82.0, "cargo_type": "standard_parcel", "expedited_medical_payload": False},
            }
        elif s == 1:
            return {
                "drone_id": "UAS_CARGO_DXB_104",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "altitude_m": 120,
                "ground_speed_mps": 22.5,
                "airspace_traffic": {"manned_traffic_detected": True, "intruder_distance_m": 820, "closing_velocity_mps": 65.0, "hems_in_vicinity": True},
                "telecom_metrics": {"rtt_latency_ms": 42, "packet_loss_pct": 0.1, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_CARGO_DXB_104", "battery_soc_pct": 21.5, "cargo_type": "standard_parcel", "expedited_medical_payload": False},
            }
        elif s == 2:
            return {
                "drone_id": "UAS_DELIVERY_AUH_209",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "altitude_m": 90,
                "ground_speed_mps": 18.0,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 4500, "hems_in_vicinity": False},
                "telecom_metrics": {"rtt_latency_ms": 295, "packet_loss_pct": 3.8, "link_lost": False, "urban_canyon_shadowing": True},
                "fleet_telemetry": {"drone_id": "UAS_DELIVERY_AUH_209", "battery_soc_pct": 58.0, "cargo_type": "high_value_retail", "expedited_medical_payload": False},
            }
        else:
            return {
                "drone_id": "UAS_MED_SHJ_311",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "altitude_m": 105,
                "ground_speed_mps": 20.0,
                "airspace_traffic": {"manned_traffic_detected": False, "intruder_distance_m": 8000, "hems_in_vicinity": False},
                "telecom_metrics": {"rtt_latency_ms": 38, "packet_loss_pct": 0.05, "link_lost": False, "urban_canyon_shadowing": False},
                "fleet_telemetry": {"drone_id": "UAS_MED_SHJ_311", "battery_soc_pct": 16.2, "cargo_type": "lab_blood_samples", "expedited_medical_payload": True},
            }

    def _poll_telemetry(self):
        telem = self.zmq_bridge.read_telemetry()
        self.radar.update_fleet_telemetry(telem)
        if telem.get("drone1"):
            z1 = telem["drone1"].get("z", 2.0)
            if hasattr(self.t_alt, "val_lbl"):
                self.t_alt.val_lbl.setText(f"{z1:.2f}m")
            soc1 = telem["drone1"].get("battery_soc", 82.0)
            if hasattr(self.t_soc, "val_lbl"):
                self.t_soc.val_lbl.setText(f"{soc1:.1f}%")

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0e17;
            }
            #mainTitle {
                font-size: 20px;
                font-weight: 800;
                color: #00f2fe;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            #badgeItu {
                font-size: 9.5px;
                font-weight: 700;
                color: #4facfe;
                letter-spacing: 0.5px;
            }
            #scenBtn {
                background-color: #111827;
                border: 1px solid #2d3748;
                border-radius: 6px;
                color: #a0aec0;
                padding: 6px 14px;
                font-size: 11.5px;
                font-weight: 600;
            }
            #scenBtn:hover {
                border-color: #00f2fe;
                color: #ffffff;
            }
            #scenBtn[active="true"] {
                background-color: rgba(0, 242, 254, 0.12);
                border: 1.5px solid #00f2fe;
                color: #00f2fe;
            }
            #radarCard {
                background-color: #111827;
                border: 1px solid #2d3748;
                border-radius: 8px;
            }
            #cardHeaderLabel {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #a0aec0;
            }
            #droneBadge {
                font-size: 11px;
                font-weight: 700;
                font-family: 'Monospace', monospace;
                color: #00f2fe;
            }
            #telemBox {
                background-color: #1f293d;
                border-radius: 5px;
                border-left: 3px solid #4facfe;
            }
            #telemLabel {
                font-size: 8.5px;
                font-weight: 700;
                text-transform: uppercase;
                color: #a0aec0;
            }
            #telemValue {
                font-size: 13px;
                font-weight: 800;
                font-family: 'Monospace', monospace;
                color: #f7fafc;
            }
            #agentCard {
                background-color: #111827;
                border: 1px solid #2d3748;
                border-radius: 8px;
            }
            #confPill {
                background-color: rgba(255, 255, 255, 0.08);
                color: #a0aec0;
                font-size: 9px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Monospace', monospace;
            }
            #agentAction {
                font-size: 11px;
                font-weight: 800;
                color: #f7fafc;
                font-family: 'Monospace', monospace;
            }
            #agentJust {
                font-size: 9.5px;
                color: #a0aec0;
                line-height: 1.3;
            }
            #citationTag {
                background-color: rgba(79, 172, 254, 0.12);
                border: 1px solid rgba(79, 172, 254, 0.35);
                color: #4facfe;
                font-size: 8px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 3px;
            }
            #coordBanner {
                background: linear-gradient(135deg, rgba(72, 187, 120, 0.1), rgba(17, 24, 39, 0.95));
                border: 1px solid rgba(72, 187, 120, 0.4);
                border-radius: 8px;
            }
            #cbTitle {
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                color: #48bb78;
                letter-spacing: 0.5px;
            }
            #coordAction {
                font-size: 13px;
                font-weight: 900;
                color: #f7fafc;
                font-family: 'Monospace', monospace;
            }
            #coordJust {
                font-size: 10px;
                color: #a0aec0;
            }
            #coordOverruled {
                background-color: rgba(245, 101, 101, 0.12);
                border: 1px solid rgba(245, 101, 101, 0.25);
                color: #feb2b2;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 9.5px;
                font-style: italic;
            }
            #rosTopic {
                font-size: 11.5px;
                font-weight: 800;
                color: #00f2fe;
                font-family: 'Monospace', monospace;
            }
            #rosStatus {
                font-size: 9.5px;
                font-weight: 700;
                color: #48bb78;
            }
            #walDot {
                color: #48bb78;
                font-size: 10px;
            }
            #walText {
                font-size: 9.5px;
                color: #718096;
            }
            #auditEventId {
                font-size: 9.5px;
                color: #718096;
                font-family: 'Monospace', monospace;
            }
        """)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    hud = AeroGridTacticalHUD()
    hud.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
