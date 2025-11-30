import asyncio
import json
import random
import time
from dataclasses import dataclass, asdict
from typing import Dict, Set, Optional
import websockets

# Configuration
GAME_WIDTH, GAME_HEIGHT = 500, 375
PLAYER_RADIUS = 25
COIN_RADIUS = 15
COIN_SPAWN_INTERVAL = 5.0
SIMULATION_LATENCY = 0.2 
PLAYER_SPEED = 300  
TICK_RATE = 120 
TICK_DELTA = 1.0 / TICK_RATE

# Data classes
@dataclass
class Vec2:
    x: float
    y: float
    
    def distance_to(self, other: 'Vec2') -> float:
        dx, dy = self.x - other.x, self.y - other.y
        return (dx*dx + dy*dy) ** 0.5
    
    def to_dict(self):
        return {'x': self.x, 'y': self.y}

@dataclass
class Player:
    id: str
    x: float
    y: float
    color: tuple = (255, 255, 255)
    score: int = 0
    input_x: float = 0
    input_y: float = 0
    
    def to_dict(self):
        return {
            'id': self.id, 
            'x': self.x, 
            'y': self.y, 
            'score': self.score,
            'color': self.color
        }

@dataclass
class Coin:
    id: str
    x: float
    y: float
    
    def to_dict(self):
        return {'id': self.id, 'x': self.x, 'y': self.y}

class GameServer:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.coins: Dict[str, Coin] = {}
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.player_id_map: Dict[websockets.WebSocketServerProtocol, str] = {}
        self.last_coin_spawn = time.time()
        self.coin_counter = 0
        self.game_started = False
        self.start_time = None
        self.stop_event = asyncio.Event()
        
    async def spawn_coin(self):
        coin_id = f"coin_{self.coin_counter}"
        self.coin_counter += 1
        
        x = random.randint(COIN_RADIUS, GAME_WIDTH - COIN_RADIUS)
        y = random.randint(COIN_RADIUS, GAME_HEIGHT - COIN_RADIUS)
        
        self.coins[coin_id] = Coin(id=coin_id, x=x, y=y)
        return coin_id
    
    async def update_game_state(self):
        current_time = time.time()
        
        if current_time - self.last_coin_spawn > COIN_SPAWN_INTERVAL:
            await self.spawn_coin()
            self.last_coin_spawn = current_time
        
        for player in self.players.values():
            mag = (player.input_x**2 + player.input_y**2) ** 0.5
            if mag > 0:
                vx = (player.input_x / mag) * PLAYER_SPEED
                vy = (player.input_y / mag) * PLAYER_SPEED
            else:
                vx, vy = 0, 0
            
            new_x = player.x + vx * TICK_DELTA
            new_y = player.y + vy * TICK_DELTA
            
            player.x = max(PLAYER_RADIUS, min(GAME_WIDTH - PLAYER_RADIUS, new_x))
            player.y = max(PLAYER_RADIUS, min(GAME_HEIGHT - PLAYER_RADIUS, new_y))
        
        coins_to_remove = []
        for coin_id, coin in self.coins.items():
            for player in self.players.values():
                dist = ((coin.x - player.x)**2 + (coin.y - player.y)**2) ** 0.5
                if dist < PLAYER_RADIUS + COIN_RADIUS:
                    player.score += 1
                    coins_to_remove.append(coin_id)
                    break
        
        for coin_id in coins_to_remove:
            del self.coins[coin_id]
    
    async def broadcast_state(self):
        if not self.game_started:
            return
        
        state = {
            'type': 'state_update',
            'timestamp': time.time(),
            'players': [p.to_dict() for p in self.players.values()],
            'coins': [c.to_dict() for c in self.coins.values()]
        }
        
        message = json.dumps(state)
        
        if self.connected_clients:
            async def delayed_send(client):
                try:
                    await asyncio.sleep(SIMULATION_LATENCY)
                    await client.send(message)
                except:
                    pass
            
            await asyncio.gather(
                *[delayed_send(client) for client in self.connected_clients],
                return_exceptions=True
            )
    
    async def handle_client(self, websocket):
        player_id = f"player_{len(self.players)}"
        
        player = Player(
            id=player_id,
            x=random.uniform(PLAYER_RADIUS, GAME_WIDTH - PLAYER_RADIUS),
            y=random.uniform(PLAYER_RADIUS, GAME_HEIGHT - PLAYER_RADIUS),
            color=(random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
        )
        self.players[player_id] = player
        self.connected_clients.add(websocket)
        self.player_id_map[websocket] = player_id
        
        init_msg = {
            'type': 'init',
            'player_id': player_id,
            'game_width': GAME_WIDTH,
            'game_height': GAME_HEIGHT,
            'player_radius': PLAYER_RADIUS,
            'coin_radius': COIN_RADIUS
        }
        await websocket.send(json.dumps(init_msg))
        print(f"Player {player_id} connected. Total players: {len(self.players)}")
        
        if len(self.players) == 2 and not self.game_started:
            self.game_started = True
            self.start_time = time.time()
            print("Game started!")
            
            for _ in range(5):
                await self.spawn_coin()
            
            start_msg = {'type': 'game_start'}
            await asyncio.gather(
                *[c.send(json.dumps(start_msg)) for c in self.connected_clients],
                return_exceptions=True
            )
        elif self.game_started:
            await websocket.send(json.dumps({'type': 'game_start'}))
        
        try:
            async for message in websocket:
                asyncio.create_task(self.process_delayed_message(websocket, message))
        
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.discard(websocket)
            if player_id in self.players:
                del self.players[player_id]
            del self.player_id_map[websocket]
            print(f"Player {player_id} disconnected. Total players: {len(self.players)}")
            
            if self.game_started and len(self.players) == 0:
                print("All players disconnected. Shutting down server...")
                self.stop_event.set()

    async def process_delayed_message(self, websocket, message):
        try:
            await asyncio.sleep(SIMULATION_LATENCY)
            data = json.loads(message)
            
            if data['type'] == 'input':
                pid = self.player_id_map.get(websocket)
                if pid in self.players:
                    self.players[pid].input_x = data.get('input_x', 0)
                    self.players[pid].input_y = data.get('input_y', 0)
        except Exception as e:
            print(f"Error processing message: {e}")
    
    async def game_loop(self):
        while not self.stop_event.is_set():
            if self.game_started:
                await self.update_game_state()
                await self.broadcast_state()
            await asyncio.sleep(TICK_DELTA)

async def main():
    server = GameServer()
    
    loop_task = asyncio.create_task(server.game_loop())
    
    async with websockets.serve(server.handle_client, "localhost", 8765):
        print("Server running on ws://localhost:8765")
        print("Waiting for 2 players to connect...")
        try:
            await server.stop_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            print("Shutting down...")

if __name__ == "__main__":
    asyncio.run(main())