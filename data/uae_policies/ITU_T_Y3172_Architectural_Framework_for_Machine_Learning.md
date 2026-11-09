# ITU-T Recommendation Y.3172 (06/2019): Architectural Framework for ML in Future Networks

*International Telecommunication Union - Telecommunication Standardization Sector*

**Regulatory Domain:** ITU-T International Telecommunication Standards

---

## Section 6 - Logical ML Pipeline Architecture

Defines the standardized machine learning pipeline nodes: SRC (Data Source), C (Collector), PP (Preprocessing), M (Model), P (Policy Gate), D (Distribution), and SINK (Decision / Actuator). Data must flow with clear interfaces and provenance tracking across all nodes.

## Section 7 - Machine Learning Sandbox (MLS)

All machine learning models and predictive agents (e.g. link quality prediction, congestion forecasting, battery reserve estimation) must be verified and evaluated in an isolated sandbox environment prior to live deployment.

## Section 8 - Policy Evaluation and Decision Distribution

Policy gate node (P) evaluates ML model outputs against regulatory constraints and institutional rules before commands reach actuators or human oversight sinks (SINK).

