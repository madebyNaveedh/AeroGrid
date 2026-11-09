# AeroGrid - CoppeliaSim 3D Digital Twin Integration

There are two ways to connect AeroGrid to CoppeliaSim. **Method 1 (ZeroMQ) is the recommended, zero-effort method.**

---

## Method 1: Python ZeroMQ Remote API (Zero Script Editing — Recommended)

With ZeroMQ, **you do not need to edit or swap any scripts in CoppeliaSim!**
The factory Quadcopter retains its built-in PID rotor controller, and Python directs its target altitude and waypoints over ZeroMQ port 23000.

### Steps:
1. Start CoppeliaSim:
   ```bash
   cd ~/AIforGood
   ./coppeliaSim.sh
   ```
2. In CoppeliaSim:
   - In the left Model Browser, drag `robots` -> `mobile` -> **Quadcopter** into the scene.
   - **Do NOT edit its script.**
   - Click the **Play** button.
3. Launch AeroGrid:
   ```bash
   ./run_aerogrid.sh
   ```
4. In the AeroGrid PyQt5 window:
   - Click **Connect CoppeliaSim ZMQ** (or it auto-connects).
   - Click **1: HEMS Emergency** -> The Quadcopter smoothly lands on the ground ($0.05\,\text{m}$).
   - Click **2: Urban 5G Shadow** -> The Quadcopter descends by $0.5\,\text{m}$ to regain line-of-sight.
   - Click **3: Battery Divert** -> The Quadcopter reroutes towards Vertiport Pad 1.

---

## Why Did the Drone Fall Earlier?
In CoppeliaSim, the default `Quadcopter` child script contains the flight PID algorithm that computes rotor speeds for each propeller (`sim.setJointTargetVelocity`). If that script is completely replaced by a custom script with no motor loop, the propellers produce zero thrust and the drone drops under gravity.

With Method 1 (ZeroMQ), Python only adjusts the target dummy position (`/Quadcopter_target`), letting the Quadcopter's built-in motors fly it smoothly without crashing!

