--[[
================================================================================
AeroGrid UTM - Complete Quadcopter Flight Controller & ROS 2 / ZeroMQ Bridge
================================================================================
Target: CoppeliaSim Quadcopter Model
Maintains full Quadcopter PID aerodynamic stabilization, propeller thrust, and
maneuver physics, while responding dynamically to:
1. Direct ZeroMQ target position commands from AeroGrid Python Mission Control
2. ROS 2 Humble topic: /aerogrid/utm_commands (std_msgs/msg/String)
================================================================================
--]]

sim = require('sim')

function sysCall_init() 
    particlesAreVisible = true
    simulateParticles = true
    fakeShadow = true
    
    particleCountPerSecond = 430
    particleSize = 0.005
    particleDensity = 8500
    particleScatteringAngle = 30
    particleLifeTime = 0.5
    maxParticleCount = 50

    -- 1. Detach manipulation target sphere to world coordinates:
    targetObj = -1
    local candidateNames = {'../target', './target', ':target', '/target', '/Quadcopter/target'}
    for _, name in ipairs(candidateNames) do
        local h = sim.getObject(name, {noError = true})
        if h and h ~= -1 then
            targetObj = h
            break
        end
    end

    if targetObj ~= -1 then
        sim.setObjectParent(targetObj, -1, true)
        -- Initialize target altitude to 2.0m for nominal cruise
        local pos = sim.getObjectPosition(targetObj, -1)
        pos[3] = 2.0
        sim.setObjectPosition(targetObj, -1, pos)
        sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Target dummy resolved (Handle: %d, Initial Z: %.2fm)", targetObj, pos[3]))
    else
        sim.addLog(sim.verbosity_scripterrors, "[AeroGrid] WARNING: Could not find target dummy! Creating virtual target.")
        targetObj = sim.createDummy(0.05)
        sim.setObjectAlias(targetObj, "target")
        sim.setObjectPosition(targetObj, -1, {0.0, 0.0, 2.0})
    end

    -- 2. Resolve body and propeller handles for PID dynamics
    d = sim.getObject('../base', {noError = true})
    if d == -1 then d = sim.getObject('.') end

    propellerHandles = {}
    jointHandles = {}
    particleObjects = {-1, -1, -1, -1}
    local ttype = sim.particle_roughspheres + sim.particle_cyclic + sim.particle_respondable1to4 + sim.particle_respondable5to8 + sim.particle_ignoresgravity
    if not particlesAreVisible then
        ttype = ttype + sim.particle_invisible
    end
    for i = 1, 4 do
        propellerHandles[i] = sim.getObject('../propeller[' .. (i-1) .. ']/respondable', {noError = true})
        jointHandles[i] = sim.getObject('../propeller[' .. (i-1) .. ']/joint', {noError = true})
        if simulateParticles then
            particleObjects[i] = sim.addParticleObject(ttype, particleSize, particleDensity, {2, 1, 0.2, 3, 0.4}, particleLifeTime, maxParticleCount, {0.3, 0.7, 1})
        end
    end
    heli = sim.getObject('..', {noError = true})
    if heli == -1 then heli = sim.getObject('.') end

    pParam = 2
    iParam = 0
    dParam = 0
    vParam = -2

    cumul = 0
    lastE = 0
    pAlphaE = 0
    pBetaE = 0
    psp2 = 0
    psp1 = 0
    prevEuler = 0

    if fakeShadow then
        shadowCont = sim.addDrawingObject(sim.drawing_discpts + sim.drawing_cyclic + sim.drawing_25percenttransparency + sim.drawing_50percenttransparency + sim.drawing_itemsizes, 0.2, 0, -1, 1)
    end

    -- 3. Initialize ROS 2 Humble subscriber if simROS2 is present
    if simROS2 then
        sub = simROS2.createSubscription('/aerogrid/utm_commands', 'std_msgs/msg/String', 'utm_command_callback')
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Subscribed to ROS 2 topic: /aerogrid/utm_commands")
    else
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] simROS2 plugin not loaded. Operating via ZeroMQ Remote API mode.")
    end
end

function sysCall_cleanup() 
    if shadowCont then
        sim.removeDrawingObject(shadowCont)
    end
    for i = 1, #particleObjects do
        if particleObjects[i] ~= -1 then
            sim.removeParticleObject(particleObjects[i])
        end
    end
end 

-- Real-time Aerodynamic Stabilization & PID Trajectory Tracking
function sysCall_actuation() 
    local pos = sim.getObjectPosition(d, -1)
    if fakeShadow and shadowCont then
        local itemData = {pos[1], pos[2], 0.002, 0, 0, 0, 1, 0.2}
        sim.addDrawingObjectItem(shadowCont, itemData)
    end
    
    -- Vertical PID control:
    local targetPos = sim.getObjectPosition(targetObj, -1)
    local l = sim.getVelocity(heli)
    local e = (targetPos[3] - pos[3])
    cumul = cumul + e
    local pv = pParam * e
    local thrust = 5.45 + pv + iParam * cumul + dParam * (e - lastE) + l[3] * vParam
    lastE = e
    
    -- Horizontal PID control: 
    local sp = sim.getObjectPosition(targetObj, d)
    local m = sim.getObjectMatrix(d, -1)
    local vx = {1, 0, 0}
    vx = sim.multiplyVector(m, vx)
    local vy = {0, 1, 0}
    vy = sim.multiplyVector(m, vy)
    local alphaE = (vy[3] - m[12])
    local alphaCorr = 0.25 * alphaE + 2.1 * (alphaE - pAlphaE)
    local betaE = (vx[3] - m[12])
    local betaCorr = -0.25 * betaE - 2.1 * (betaE - pBetaE)
    pAlphaE = alphaE
    pBetaE = betaE
    alphaCorr = alphaCorr + sp[2] * 0.005 + 1 * (sp[2] - psp2)
    betaCorr = betaCorr - sp[1] * 0.005 - 1 * (sp[1] - psp1)
    psp2 = sp[2]
    psp1 = sp[1]
    
    -- Rotational Yaw control:
    local euler = sim.getObjectOrientation(d, targetObj)
    local rotCorr = euler[3] * 0.1 + 2 * (euler[3] - prevEuler)
    prevEuler = euler[3]
    
    -- Apply calculated thrust to the 4 propellers:
    handlePropeller(1, thrust * (1 - alphaCorr + betaCorr + rotCorr))
    handlePropeller(2, thrust * (1 - alphaCorr - betaCorr - rotCorr))
    handlePropeller(3, thrust * (1 + alphaCorr - betaCorr + rotCorr))
    handlePropeller(4, thrust * (1 + alphaCorr + betaCorr - rotCorr))
end 

function handlePropeller(index, particleVelocity)
    local propellerRespondable = propellerHandles[index]
    local propellerJoint = jointHandles[index]
    if not propellerRespondable or propellerRespondable == -1 then return end

    local propeller = sim.getObjectParent(propellerRespondable)
    local particleObject = particleObjects[index]
    local maxParticleDeviation = math.tan(particleScatteringAngle * 0.5 * math.pi / 180) * particleVelocity
    local notFullParticles = 0

    local t = sim.getSimulationTime()
    if propellerJoint and propellerJoint ~= -1 then
        sim.setJointPosition(propellerJoint, t * 10)
    end
    local ts = sim.getSimulationTimeStep()
    
    local m = sim.getObjectMatrix(propeller, -1)
    local particleCnt = 0
    local pos = {0, 0, 0}
    local dir = {0, 0, 1}
    
    local requiredParticleCnt = particleCountPerSecond * ts + notFullParticles
    notFullParticles = requiredParticleCnt % 1
    requiredParticleCnt = math.floor(requiredParticleCnt)
    while (particleCnt < requiredParticleCnt) do
        local x = (math.random() - 0.5) * 2
        local y = (math.random() - 0.5) * 2
        if (x * x + y * y <= 1) then
            if simulateParticles and particleObject ~= -1 then
                pos[1] = x * 0.08
                pos[2] = y * 0.08
                pos[3] = -particleSize * 0.6
                dir[1] = pos[1] + (math.random() - 0.5) * maxParticleDeviation * 2
                dir[2] = pos[2] + (math.random() - 0.5) * maxParticleDeviation * 2
                dir[3] = pos[3] - particleVelocity * (1 + 0.2 * (math.random() - 0.5))
                local pWorld = sim.multiplyVector(m, pos)
                local dWorld = sim.multiplyVector(m, dir)
                sim.addParticleObjectItem(particleObject, {pWorld[1], pWorld[2], pWorld[3], dWorld[1], dWorld[2], dWorld[3]})
            end
            particleCnt = particleCnt + 1
        end
    end

    -- Apply reactive force onto the propeller body:
    local totalExertedForce = particleCnt * particleDensity * particleVelocity * math.pi * particleSize * particleSize * particleSize / (6 * ts)
    local force = {0, 0, totalExertedForce}
    m[4] = 0
    m[8] = 0
    m[12] = 0
    force = sim.multiplyVector(m, force)
    local rotDir = 1 - math.fmod(index, 2) * 2
    local torque = {0, 0, rotDir * 0.002 * particleVelocity}
    torque = sim.multiplyVector(m, torque)
    sim.addForceAndTorque(propellerRespondable, force, torque)
end

-- Callback for ROS 2 /aerogrid/utm_commands
function utm_command_callback(msg)
    local payload = msg.data
    sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] ROS 2 Command: %s", payload))

    if targetObj == -1 then return end
    local pos = sim.getObjectPosition(targetObj, -1)

    -- Case 1: HEMS Emergency Evacuation
    if string.find(payload, "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION") or string.find(payload, "EVACUATION") then
        pos[3] = 0.05
        sim.setObjectPosition(targetObj, -1, pos)
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Action: EMERGENCY EVACUATION -> Landing at 0.05m")

    -- Case 2: 5G Shadowing Handover
    elseif string.find(payload, "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER") or string.find(payload, "5G_CELL_HANDOVER") then
        pos[3] = math.max(0.05, pos[3] - 0.5)
        sim.setObjectPosition(targetObj, -1, pos)
        sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Action: 5G HANDOVER -> Altitude adjusted to %.2fm", pos[3]))

    -- Case 3: Battery Divert to Vertiport 1
    elseif string.find(payload, "DIVERT") or string.find(payload, "VERTIPORT") then
        sim.setObjectPosition(targetObj, -1, {-2.0, 1.5, 0.8})
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Action: BATTERY DIVERT -> Heading to Vertiport Pad 1 (-2.0, 1.5, 0.8)")

    -- Case 4: Nominal Cruise
    elseif string.find(payload, "MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR") or string.find(payload, "NOMINAL") then
        sim.setObjectPosition(targetObj, -1, {0.0, 0.0, 2.0})
        sim.addLog(sim.verbosity_scriptinfos, "[AeroGrid] Action: NOMINAL CRUISE -> Holding 2.0m hover")
    end
end
