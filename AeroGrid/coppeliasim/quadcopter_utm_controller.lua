--[[
================================================================================
AeroGrid UTM - CoppeliaSim Quadcopter ROS 2 Lua Child Script
================================================================================
Target: CoppeliaSim Quadcopter Model with ROS 2 Humble bridge
Subscribes to: /aerogrid/utm_commands (std_msgs/msg/String)

Requirements implemented:
1. sysCall_init: Detects simROS2, subscribes to /aerogrid/utm_commands,
   resolves the Quadcopter target object, and initializes target altitude to 2.0m.
2. utm_command_callback: Uses Lua string matching on incoming JSON payload:
   - "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION" -> Sets target Z to 0.05m (ground level)
   - "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER" -> Drops target Z by 0.5m
3. Logs all received commands and actuation triggers via sim.addLog.
4. sysCall_cleanup: Cleanly shuts down the ROS 2 subscriber on simulation stop.
================================================================================
--]]

function sysCall_init()
    sim = require('sim')

    -- 1. Resolve Target Object Handle (Compatible with standard CoppeliaSim quadcopters)
    -- Look for target dummy object: Quadcopter_target or target child
    targetObj = -1
    local candidateNames = {'/Quadcopter_target', './target', '../target', ':target', '/target'}
    for _, name in ipairs(candidateNames) do
        targetObj = sim.getObject(name, {noError = true})
        if targetObj ~= -1 then
            break
        end
    end

    -- Fallback to self object if separate target dummy is not used
    if targetObj == -1 then
        targetObj = sim.getObject('.')
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Target dummy not found. Using Quadcopter base as target object.")
    else
        sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Found target object handle: %d", targetObj))
    end

    -- 2. Set Default Target Altitude (2.0 meters)
    local pos = sim.getObjectPosition(targetObj, -1)
    pos[3] = 2.0
    sim.setObjectPosition(targetObj, -1, pos)
    sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Initialized target altitude to %.2fm (X: %.2f, Y: %.2f)", pos[3], pos[1], pos[2]))

    -- 3. Detect simROS2 Plugin
    if not simROS2 then
        sim.addLog(sim.verbosity_scripterrors, "[AeroGrid] ERROR: simROS2 plugin is NOT loaded! Please enable ROS 2 Humble in CoppeliaSim.")
        return
    end

    -- 4. Subscribe to /aerogrid/utm_commands
    sub = simROS2.createSubscription('/aerogrid/utm_commands', 'std_msgs/msg/String', 'utm_command_callback')
    sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Successfully subscribed to topic: /aerogrid/utm_commands")
end

-- Callback triggered when a new operational command is received from ROS 2
function utm_command_callback(msg)
    local payload = msg.data
    sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Received ROS 2 Command Payload: %s", payload))

    -- Check if target object handle is valid
    if targetObj == -1 then
        sim.addLog(sim.verbosity_scripterrors, "[AeroGrid] ERROR: Invalid target object handle. Cannot actuate.")
        return
    end

    -- Read current target position in world coordinates
    local pos = sim.getObjectPosition(targetObj, -1)

    -- Case 1: Emergency Descent & Corridor Evacuation (Manned Traffic / HEMS Priority)
    if string.find(payload, "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION") then
        local prevZ = pos[3]
        pos[3] = 0.05 -- Set to ground level
        sim.setObjectPosition(targetObj, -1, pos)
        sim.addLog(sim.verbosity_scriptinfos, string.format(
            "[AeroGrid] >>> ACTUATION TRIGGERED: EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION <<<\n" ..
            "  -> Grounding Quadcopter for Airspace Evacuation!\n" ..
            "  -> Target Z changed from %.2fm to %.2fm (Ground Level)",
            prevZ, pos[3]
        ))

    -- Case 2: Urban Canyon 5G Shadowing / C2 Degraded (Drop Altitude by 0.5m)
    elseif string.find(payload, "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER") then
        local prevZ = pos[3]
        pos[3] = math.max(0.05, pos[3] - 0.5) -- Drop by 0.5m (bounded at ground level)
        sim.setObjectPosition(targetObj, -1, pos)
        sim.addLog(sim.verbosity_scriptinfos, string.format(
            "[AeroGrid] >>> ACTUATION TRIGGERED: DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER <<<\n" ..
            "  -> Lowering flight altitude envelope to regain 5G gNodeB Line-of-Sight!\n" ..
            "  -> Target Z dropped by 0.5m from %.2fm to %.2fm",
            prevZ, pos[3]
        ))

    -- Case 3: Other commands (e.g. Battery Divert / Maintain Corridor)
    else
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Command logged. No Z-axis override required for current directive.")
    end
end

function sysCall_cleanup()
    if simROS2 and sub then
        simROS2.shutdownSubscription(sub)
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Closed ROS 2 subscription to /aerogrid/utm_commands.")
    end
end
