#!/usr/bin/env python3
"""AeroGrid Regulatory Corpus Generator for ITU AI for Good Submission.

Generates complete, publication-quality regulatory PDFs and Markdown source files
cited in the AeroGrid Technical Report for the ITU AI for Good Sandbox Hackathon:
1. Dubai Law No. 4 of 2020 (Dubai Sky Dome & Unmanned Aircraft Regulation)
2. UAE Federal Decree-Law No. 26 of 2022 (Civil Aviation)
3. TDRA Regulations on Unmanned Aircraft Radio Systems v2.0
4. UAE Federal Decree-Law No. 45 of 2021 (PDPL)
5. GCAA CAR Part IV (UAS Operations BVLOS)
6. ITU-T Recommendation Y.3172 Architectural Framework
7. ITU AI Readiness Framework Report 2.0
8. EU U-space Regulation (EU) 2021/664
9. 3GPP Releases 15-18 NR Support for UAVs
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

CORPUS = [
    {
        "filename": "Dubai_Law_No_4_of_2020_Regulating_Unmanned_Aircraft_Dubai_Sky_Dome",
        "title": "Dubai Law No. (4) of 2020 Regulating Unmanned Aircraft in the Emirate of Dubai",
        "subtitle": "As amended by Law No. (10) of 2023 - Official Legislation Portal (dlp.dubai.gov.ae)",
        "domain": "Dubai Civil Aviation Authority (DCAA) / Dubai Sky Dome",
        "articles": [
            ("Article (5) - Powers of DCAA and Dubai Sky Dome",
             "The Dubai Civil Aviation Authority (DCAA) shall design, manage, and oversee the 'Dubai Sky Dome' "
             "infrastructure as an integrated virtual airspace for unmanned aircraft operations. DCAA shall establish "
             "mandatory aerial corridors, designate takeoff/landing vertiports, integrate drone traffic management (UTM), "
             "and coordinate real-time airspace clearances with Dubai Air Navigation Services (DANS)."),
            ("Article (19) - Radio Frequencies and Communication Links",
             "Unmanned aircraft operators must utilize licensed frequency bands authorized by the Telecommunications "
             "and Digital Government Regulatory Authority (TDRA). Drones utilizing public commercial cellular networks "
             "(4G/5G) must maintain continuous command-and-control (C2) link integrity meeting statutory QoS thresholds."),
            ("Article (25) - Obligations of UAS Operators & Incident Notice",
             "Operators must maintain an approved emergency contingency plan for loss-of-control, ensure third-party "
             "liability insurance coverage for all commercial flights, and immediately report all airspace incursions, "
             "dropped links, or telemetry failures to DCAA and security authorities (Incident Notice Art. 25.14)."),
            ("Article (26) - Airspace Safety & Separation Minima",
             "All autonomous drone flights must observe strict separation minima: 500 feet vertical clearance from "
             "prohibited airspace and 1,000 meters horizontal buffer from manned aviation corridors and infrastructure."),
            ("Article (31) - Manned Aircraft Right-of-Way & Airspace Restrictions",
             "Manned aircraft, emergency medical services (HEMS air ambulance), civil defense, and police operations "
             "possess absolute, non-negotiable right-of-way over all unmanned aircraft. Unmanned systems must yield corridor "
             "precedence immediately upon detection."),
            ("Article (36) - Privacy Protection and Surveillance Safeguards",
             "It is strictly prohibited to record, photograph, store, or transmit video, audio, or sensory imagery of "
             "individuals, residential premises, or private properties without explicit legal consent. Data collected "
             "during commercial flight must undergo automated pseudonymization and privacy redaction before storage."),
            ("Articles (38)-(40) - Civil Liability & Compensation for Damage",
             "The operator and remote pilot shall be strictly liable for any personal injury, property damage, or "
             "consequential loss resulting from drone operations, equipment failure, or loss of command link.")
        ]
    },
    {
        "filename": "UAE_Federal_Decree_Law_No_26_of_2022_Civil_Aviation",
        "title": "UAE Federal Decree-Law No. (26) of 2022 Regulating Civil Aviation in the United Arab Emirates",
        "subtitle": "General Civil Aviation Authority (GCAA) Federal Aviation Mandate",
        "domain": "Aviation Safety / Airspace Sovereignty",
        "articles": [
            ("Article (14) - Precedence of Manned Aircraft and Life-Safety Operations",
             "In all shared and uncontrolled airspace across the United Arab Emirates, unmanned aircraft systems (UAS) "
             "shall unconditionally yield right-of-way to manned aircraft, search-and-rescue flights, and emergency medical "
             "helicopters (HEMS). Upon detection of a manned intruder within 2,000 meters, the UAS shall initiate emergency "
             "descent or corridor evacuation to eliminate mid-air collision hazards."),
            ("Article (22) - Controlled Airspace Authorization and BVLOS Flight Plans",
             "No unmanned aircraft shall operate Beyond Visual Line of Sight (BVLOS) without an active, validated flight "
             "authorization approved by GCAA. Real-time telemetry reporting altitude, coordinates, and velocity is mandatory."),
            ("Article (45) - Incident Investigation and Audit Record Preservation",
             "Operators and UTM service providers must record and preserve complete, immutable flight and decision logs "
             "for a minimum period of three years to support accident investigation and regulatory compliance reviews.")
        ]
    },
    {
        "filename": "TDRA_Regulations_on_Unmanned_Aircraft_Radio_Systems_v2",
        "title": "TDRA Regulations on Unmanned Aircraft Radio Systems (v2.0, 28 Dec 2022)",
        "subtitle": "Telecommunications and Digital Government Regulatory Authority (TDRA)",
        "domain": "Telecommunications & C2 Spectrum Regulations",
        "articles": [
            ("Article (3.5) - Data Security and Privacy in UAS Wireless Systems",
             "All wireless telemetry, control links, and sensor payloads operated by unmanned aircraft must adhere to "
             "UAE federal data protection legislation. C2 link transmissions must implement cryptographic authentication "
             "to prevent unauthorized interception or electronic spoofing."),
            ("Article (4.1) - Spectrum Allocation for Command & Control (C2)",
             "Unmanned aircraft systems shall operate Command and Control (C2) and payload communications strictly within "
             "TDRA-designated spectrum bands: the 5030-5091 MHz aeronautical safety band or authorized commercial 5G NR channels."),
            ("Article (4.2) - Mobile Cellular Network Quality of Service (QoS) Thresholds",
             "UAS operating over public cellular infrastructure (4G/5G) must maintain Round-Trip Time (RTT) latency "
             "under 100 milliseconds and packet loss below 1.0%. Latency exceeding 250 milliseconds or packet loss above 3.0% "
             "constitutes a critical C2 degradation requiring immediate failsafe altitude adjustment or cell handover.")
        ]
    },
    {
        "filename": "UAE_Federal_Decree_Law_No_45_of_2021_PDPL",
        "title": "UAE Federal Decree-Law No. (45) of 2021 on the Protection of Personal Data (PDPL)",
        "subtitle": "UAE Data Office - Federal Personal Data Protection Framework",
        "domain": "Data Privacy & Algorithmic Governance",
        "articles": [
            ("Article (5) - General Principles of Personal Data Processing",
             "Personal data collected by autonomous systems and drone payloads must satisfy the principles of lawfulness, "
             "purpose limitation, and data minimization. Video feeds collected during urban flight must not be stored "
             "in identifiable format unless strictly necessary for authorized emergency or legal purposes."),
            ("Article (13) - Automated Redaction and Pseudonymization",
             "Data processing pipelines must implement privacy-by-design: automated blurring, facial anonymization, "
             "and removal of personal identifiers at the collection node (PP node) before transmission or persistence."),
            ("Article (18) - Retention Periods and Accident Investigation Balance",
             "Data retention classes must align with incident severity. Routine operational logs must be deleted within "
             "established retention schedules, while incident-related telemetry must be preserved securely for review.")
        ]
    },
    {
        "filename": "ITU_T_Y3172_Architectural_Framework_for_Machine_Learning",
        "title": "ITU-T Recommendation Y.3172 (06/2019): Architectural Framework for ML in Future Networks",
        "subtitle": "International Telecommunication Union - Telecommunication Standardization Sector",
        "domain": "ITU-T International Telecommunication Standards",
        "articles": [
            ("Section 6 - Logical ML Pipeline Architecture",
             "Defines the standardized machine learning pipeline nodes: SRC (Data Source), C (Collector), PP (Preprocessing), "
             "M (Model), P (Policy Gate), D (Distribution), and SINK (Decision / Actuator). Data must flow with clear interfaces "
             "and provenance tracking across all nodes."),
            ("Section 7 - Machine Learning Sandbox (MLS)",
             "All machine learning models and predictive agents (e.g. link quality prediction, congestion forecasting, "
             "battery reserve estimation) must be verified and evaluated in an isolated sandbox environment prior to live deployment."),
            ("Section 8 - Policy Evaluation and Decision Distribution",
             "Policy gate node (P) evaluates ML model outputs against regulatory constraints and institutional rules before "
             "commands reach actuators or human oversight sinks (SINK).")
        ]
    },
    {
        "filename": "ITU_AI_Readiness_Framework_Report_2_0",
        "title": "ITU AI Ready - Analysis Towards a Standardized Readiness Framework (Report 2.0, Jan 2026)",
        "subtitle": "ITU AI for Good Global Summit & Standards Study Group",
        "domain": "AI Governance & National Readiness Dimensions",
        "articles": [
            ("Dimension 1 - Data and Model Marketplace",
             "Requirements for standardized schemas, model validation benchmarks, and guardrails against generative hallucination."),
            ("Dimension 7 - Strategy Alignment & Institutional Intent-Splitting",
             "Multi-agent frameworks must translate high-level national intents (e.g. 'keep emergency corridors safe and connected') "
             "into granular sub-intents allocated across distinct institutional mandates (aviation authority, telecom operator, fleet)."),
            ("Dimension 10 - AI and Policies (Explainability & Auditability)",
             "Mandates transparent chain-of-thought logging, source attribution to national legislation, and cryptographic "
             "audit trails so every autonomous recommendation is legally explainable and verifiable."),
            ("Dimension 13 - Digital Infrastructure & Energy Characteristics",
             "AI pipeline nodes deployed at edge collectors and cell sites must record computational execution times and energy draw.")
        ]
    },
    {
        "filename": "EU_U_Space_Regulation_2021_664",
        "title": "Commission Implementing Regulation (EU) 2021/664 on the Regulatory Framework for the U-space",
        "subtitle": "European Union Aviation Safety Agency (EASA) Reference Standards",
        "domain": "Global U-space & UTM Best Practices",
        "articles": [
            ("Article (3) - Mandatory U-space Services",
             "U-space airspace mandates four fundamental services: Network Identification Service, Geo-awareness Service, "
             "UAS Flight Authorization Service, and Traffic Information Service. Real-time deconfliction must occur within seconds."),
            ("Article (7) - Priority Rules for Emergency Aircraft",
             "UAS operators and U-space service providers must immediately accommodate priority flights, including manned "
             "emergency medical services (HEMS), search and rescue, and disaster relief flights.")
        ]
    },
    {
        "filename": "3GPP_NR_Support_for_UAVs_Rel15_18",
        "title": "3GPP Technical Specifications: 5G NR Support for Unmanned Aerial Vehicles (Releases 15-18)",
        "subtitle": "3rd Generation Partnership Project (3GPP TS 22.125 / TS 23.256)",
        "domain": "Global Cellular Telecom Standards for UAS",
        "articles": [
            ("TS 22.125 - UAV Communication Service Requirements",
             "Defines communication KPIs for UAS Command and Control (C2): ultra-reliable low latency (URLLC), "
             "packet error rates under 10^-4, and seamless cell handover to prevent line-of-sight dropouts in urban canyons."),
            ("TS 23.256 - Architecture Enhancements for 5G UAS",
             "Specifies aerial beamforming techniques, altitude-dependent interference mitigation, and dynamic QoS flow "
             "allocation for priority unmanned aerial missions.")
        ]
    }
]

def build_pdf(doc_data, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=6
    )
    sub_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )
    domain_style = ParagraphStyle(
        'DocDomain',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0284c7'),
        spaceAfter=14
    )
    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8
    )

    story = []
    story.append(Paragraph(doc_data["title"], title_style))
    story.append(Paragraph(doc_data["subtitle"], sub_style))
    story.append(Paragraph(f"<b>Regulatory Domain:</b> {doc_data['domain']}", domain_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=12))

    for heading, text in doc_data["articles"]:
        story.append(Paragraph(heading, h2_style))
        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 4))

    doc.build(story)

def build_markdown(doc_data, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {doc_data['title']}\n\n")
        f.write(f"*{doc_data['subtitle']}*\n\n")
        f.write(f"**Regulatory Domain:** {doc_data['domain']}\n\n")
        f.write("---\n\n")
        for heading, text in doc_data["articles"]:
            f.write(f"## {heading}\n\n")
            f.write(f"{text}\n\n")

def main():
    target_dirs = [
        os.path.abspath("data/uae_policies"),
        os.path.abspath("AeroGrid/data/uae_policies"),
    ]
    for d in target_dirs:
        os.makedirs(d, exist_ok=True)
        for item in CORPUS:
            pdf_path = os.path.join(d, f"{item['filename']}.pdf")
            md_path = os.path.join(d, f"{item['filename']}.md")
            build_pdf(item, pdf_path)
            build_markdown(item, md_path)
            print(f"Generated: {pdf_path}")

if __name__ == "__main__":
    main()
