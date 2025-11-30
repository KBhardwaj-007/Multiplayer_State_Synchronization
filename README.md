# Multiplayer Coin Collector

A real-time multiplayer game with authoritative server and client-side interpolation, designed to handle simulated network latency.

## Requirements

- Python 3.8+
- `websockets`
- `pygame`

**Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## How to Run

1. **Start the Server:**
   ```bash
   python server.py
   ```
   The server will start on `ws://localhost:8765`.

2. **Start Clients:**
   Open two separate terminal windows and run:
   ```bash
   python client.py
   ```
   We can specify a custom server URI if needed:
   ```bash
   python client.py ws://localhost:8765
   ```

3. **Gameplay:**
   - The game starts automatically when 2 players connect.
   - Use **WASD** or **Arrow Keys** to move.
   - Collect coins to score points.
   - The server simulates **200ms latency** for all network traffic (Bidirectional: 200ms Uplink + 200ms Downlink).
   - Clients use **Snapshot Interpolation** to ensure smooth movement despite the latency.

## Architecture

### Server (`server.py`)
- **Authoritative:** Manages all game state (player positions, scores, coins).
- **Latency Simulation:** 
  - **Downlink:** Delays state broadcasts by 200ms.
  - **Uplink:** Delays processing client inputs by 200ms.
- **Tick Rate:** Runs at **120 ticks per second** for high-precision simulation.
- **Coin Logic:** Spawns 5 coins on start. New coins spawn every 5 seconds.
- **Auto-Shutdown:** Server automatically closes when all players disconnect.
- **Protocol:** Uses WebSockets for communication. JSON messages for state updates.

### Client (`client.py`)
- **Rendering:** Uses Pygame for visualization. Runs at 120 FPS.
- **Interpolation:** Implements a history buffer (350ms) to store past server states. Renders entities delayed by the buffer amount to interpolate smoothly between known states.
- **Prediction:** Does *not* use client-side prediction (per requirements), relying purely on interpolation of authoritative server state.

## Implementation Details

- **Interpolation:** The client maintains a buffer of state snapshots. It renders the game state from `current_time - interpolation_delay`. It finds the two snapshots surrounding this render time and linearly interpolates between them.
- **Collision:** All collision detection happens on the server.
- **Security:** Clients only send input vectors (WASD/Arrows). They cannot report scores or positions directly.
