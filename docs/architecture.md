graph TD
    subgraph Human Interaction
        HUI[Human Interface Unit] -- Manual Commands --> CAL
    end

    subgraph Perception
        MAVSDK_I --> TP[Telemetry Processor]
        MAVSDK_I --> CP[Camera Processor (Mock)]
    end

    subgraph State Management
        TP -- Processed Telemetry --> SCM
        CP -- Visual Insights --> SCM[State & Context Manager]
    end

    subgraph Decision Making
        SCM -- Comprehensive Contextual Prompt --> LDE[LLM Decision Engine (Ollama)]
    end

    subgraph Command Flow
        LDE -- LLM Recommended Autonomous Command --> CAL[Command Arbitration Logic]
        CAL -- Prioritized Drone Command --> CEU[Command Execution Unit]
        CEU -- MAVSDK API Calls --> MAVSDK_I[MAVSDK Interface]
    end

    MAVSDK_I -- Bidirectional (Raw Telemetry / Drone Actions) --> DH[Drone Hardware (SITL)]

    style HUI fill:#ecfdf5,stroke:#34d399,stroke-width:2px,color:#065f46
    style TP fill:#eff6ff,stroke:#60a5fa,stroke-width:2px,color:#1e40af
    style CP fill:#eff6ff,stroke:#60a5fa,stroke-width:2px,color:#1e40af
    style SCM fill:#f3e8ff,stroke:#a78bfa,stroke-width:2px,color:#5b21b6
    style LDE fill:#e0f2fe,stroke:#38bdf8,stroke-width:2px,color:#0284c7
    style CAL fill:#fffbeb,stroke:#fbbf24,stroke-width:2px,color:#b45309
    style CEU fill:#fee2e2,stroke:#ef4444,stroke-width:2px,color:#b91c1c
    style MAVSDK_I fill:#e2e8f0,stroke:#94a3b8,stroke-width:2px,color:#475569
    style DH fill:#cbd5e1,stroke:#64748b,stroke-width:2px,color:#334155
