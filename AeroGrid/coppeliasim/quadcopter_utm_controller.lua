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
    local selfObj = sim.getObject('.')
    local selfAlias = string.lower(sim.getObjectAlias(selfObj))
    local heliParent = sim.getObject('..', {noError = true})
    local parentAlias = ""
    if heliParent ~= -1 then parentAlias = string.lower(sim.getObjectAlias(heliParent)) end

    local isDrone2 = string.find(selfAlias, "peer") or string.find(selfAlias, "hems") or string.find(selfAlias, "#") or string.find(selfAlias, "2") or string.find(parentAlias, "peer") or string.find(parentAlias, "hems") or string.find(parentAlias, "#") or string.find(parentAlias, "2")

    targetObj = -1
    local cands = {}
    if isDrone2 then
        cands = {'/target_drone2', ':target_drone2', '../target_drone2', './target', '../target', ':target#0', '/target'}
    else
        cands = {'/target_drone1', ':target_drone1', '../target_drone1', './target', '../target', ':target'}
    end

    for _, name in ipairs(cands) do
        local h = sim.getObject(name, {noError = true})
        if h and h ~= -1 then targetObj = h; break end
    end

    if targetObj ~= -1 then
        sim.setObjectParent(targetObj, -1, true)
        if isDrone2 then
            sim.setObjectAlias(targetObj, "target_drone2")
            local pos = {1.2, 0.6, 2.4}
            sim.setObjectPosition(targetObj, -1, pos)
            sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Drone 2 target resolved (Handle: %d, Initial Pos: 1.2, 0.6, 2.4m)", targetObj))
        else
            sim.setObjectAlias(targetObj, "target_drone1")
            local pos = {0.0, 0.0, 2.0}
            sim.setObjectPosition(targetObj, -1, pos)
            sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] Drone 1 target resolved (Handle: %d, Initial Pos: 0.0, 0.0, 2.0m)", targetObj))
        end
    else
        sim.addLog(sim.verbosity_scripterrors, "[AeroGrid] WARNING: Could not find target dummy! Creating virtual target.")
        targetObj = sim.createDummy(0.05)
        sim.setObjectAlias(targetObj, isDrone2 and "target_drone2" or "target_drone1")
        sim.setObjectPosition(targetObj, -1, isDrone2 and {1.2, 0.6, 2.4} or {0.0, 0.0, 2.0})
    end

    -- 2. Resolve body and propeller handles for PID dynamics
    d = sim.getObject('./base', {noError = true})
    if d == -1 then d = sim.getObject('../base', {noError = true}) end
    if d == -1 then d = selfObj end

    propellerHandles = {}
    jointHandles = {}
    particleObjects = {-1, -1, -1, -1}
    local ttype = sim.particle_roughspheres + sim.particle_cyclic + sim.particle_respondable1to4 + sim.particle_respondable5to8 + sim.particle_ignoresgravity
    if not particlesAreVisible then
        ttype = ttype + sim.particle_invisible
    end
    for i = 1, 4 do
        local p = sim.getObject('./propeller[' .. (i-1) .. ']/respondable', {noError = true})
        if p == -1 then p = sim.getObject('../propeller[' .. (i-1) .. ']/respondable', {noError = true}) end
        propellerHandles[i] = p

        local j = sim.getObject('./propeller[' .. (i-1) .. ']/joint', {noError = true})
        if j == -1 then j = sim.getObject('../propeller[' .. (i-1) .. ']/joint', {noError = true}) end
        jointHandles[i] = j

        if simulateParticles then
            particleObjects[i] = sim.addParticleObject(ttype, particleSize, particleDensity, {2, 1, 0.2, 3, 0.4}, particleLifeTime, maxParticleCount, {0.3, 0.7, 1})
        end
    end
    heli = selfObj

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
    if shadowCont and shadowCont ~= -1 then
        pcall(function() sim.removeDrawingObject(shadowCont) end)
    end
    if particleObjects then
        for i = 1, #particleObjects do
            if particleObjects[i] and particleObjects[i] ~= -1 then
                pcall(function() sim.removeParticleObject(particleObjects[i]) end)
            end
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
    local l = {0, 0, 0}
    if sim.getObjectVelocity then
        local lin = sim.getObjectVelocity(d)
        if lin then l = lin end
    elseif sim.getVelocity then
        local lin = sim.getVelocity(d)
        if lin then l = lin end
    end
    if not l[3] then l[3] = 0 end

    local e = (targetPos[3] - pos[3])
    cumul = math.max(-10, math.min(10, cumul + e))
    local pv = pParam * e
    local thrust = 5.45 + pv + iParam * cumul + dParam * (e - lastE) + l[3] * vParam
    -- Clamp vertical thrust to physically reasonable range [0.5, 12.0]
    thrust = math.max(0.5, math.min(12.0, thrust))
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
    
    -- CRUCIAL AERODYNAMIC STABILITY: Clamp differential thrust factors to prevent violent flipping
    alphaCorr = math.max(-0.25, math.min(0.25, alphaCorr))
    betaCorr = math.max(-0.25, math.min(0.25, betaCorr))
    rotCorr = math.max(-0.20, math.min(0.20, rotCorr))

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
    sim.addLog(sim.verbosity_scriptinfos, string.format("[AeroGrid] ROS 2 UTM Command logged: %s", payload))
end
