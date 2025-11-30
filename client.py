import asyncio
import json
import pygame
import websockets
import sys
import time
from typing import Dict, List, Optional

pygame.init()

RENDER_FPS = 120
INTERPOLATION_OFFSET = 0.35
SERVER_URI = "ws://localhost:8765"

class GameClient:
    def __init__(self):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.player_id: Optional[str] = None
        self.game_width: int = 500
        self.game_height: int = 375
        self.player_radius: int = 25
        self.coin_radius: int = 20
        self.game_started = False
        
        self.state_buffer: List[dict] = []
        self.current_display_state = {"players": {}, "coins": []}
        
        self.screen: Optional[pygame.Surface] = None
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 18)
        self.small_font = pygame.font.SysFont("Arial", 14)
        
        self.keys_pressed = set()
        self.running = True
        
    async def connect(self):
        try:
            self.websocket = await websockets.connect(SERVER_URI, ping_interval=None)
            print(f"Connected to server at {SERVER_URI}")
        except Exception as e:
            print(f"Failed to connect: {e}")
            sys.exit(1)
    
    async def receive_messages(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_type = data.get('type')
                
                if msg_type == 'init':
                    self.player_id = data['player_id']
                    self.game_width = data['game_width']
                    self.game_height = data['game_height']
                    self.player_radius = data['player_radius']
                    self.coin_radius = data['coin_radius']
                    
                    if self.screen:
                        self.screen = pygame.display.set_mode((self.game_width, self.game_height))
                        
                    print(f"Initialized as {self.player_id}")
                
                elif msg_type == 'game_start':
                    self.game_started = True
                    print("Game started!")
                
                elif msg_type == 'state_update':
                    self.state_buffer.append(data)
                    if len(self.state_buffer) > 40:
                        self.state_buffer.pop(0)
        
        except websockets.exceptions.ConnectionClosed:
            print("Disconnected from server")
            self.running = False
        except Exception as e:
            print(f"Receive error: {e}")
            self.running = False
    
    def get_interpolated_state(self):
        render_time = time.time() - INTERPOLATION_OFFSET
        
        if len(self.state_buffer) < 2:
            if self.state_buffer:
                latest = self.state_buffer[-1]
                players_dict = {p['id']: p for p in latest['players']}
                return {"players": players_dict, "coins": latest['coins']}
            return self.current_display_state

        prev_state = None
        next_state = None

        for i in range(len(self.state_buffer) - 1, -1, -1):
            if self.state_buffer[i]['timestamp'] <= render_time:
                prev_state = self.state_buffer[i]
                if i + 1 < len(self.state_buffer):
                    next_state = self.state_buffer[i+1]
                break
        
        if not prev_state:
            state = self.state_buffer[0]
            players_dict = {p['id']: p for p in state['players']}
            return {"players": players_dict, "coins": state['coins']}
            
        if not next_state:
            state = prev_state
            players_dict = {p['id']: p for p in state['players']}
            return {"players": players_dict, "coins": state['coins']}

        time_diff = next_state['timestamp'] - prev_state['timestamp']
        alpha = 0 if time_diff == 0 else (render_time - prev_state['timestamp']) / time_diff
        
        interpolated_players = {}
        
        prev_players = {p['id']: p for p in prev_state['players']}
        next_players = {p['id']: p for p in next_state['players']}
        
        for pid, next_p_data in next_players.items():
            if pid in prev_players:
                prev_p_data = prev_players[pid]
                x = prev_p_data['x'] + (next_p_data['x'] - prev_p_data['x']) * alpha
                y = prev_p_data['y'] + (next_p_data['y'] - prev_p_data['y']) * alpha
                
                interpolated_players[pid] = {
                    "x": x, "y": y,
                    "score": next_p_data['score'],
                    "color": next_p_data.get('color', (255, 255, 255)),
                    "id": pid
                }
            else:
                interpolated_players[pid] = next_p_data

        return {"players": interpolated_players, "coins": next_state['coins']}
    
    async def send_input(self):
        while self.running:
            if self.websocket and self.game_started:
                input_x, input_y = 0, 0
                
                if pygame.K_LEFT in self.keys_pressed or pygame.K_a in self.keys_pressed:
                    input_x -= 1
                if pygame.K_RIGHT in self.keys_pressed or pygame.K_d in self.keys_pressed:
                    input_x += 1
                if pygame.K_UP in self.keys_pressed or pygame.K_w in self.keys_pressed:
                    input_y -= 1
                if pygame.K_DOWN in self.keys_pressed or pygame.K_s in self.keys_pressed:
                    input_y += 1
                
                message = {
                    'type': 'input',
                    'input_x': input_x,
                    'input_y': input_y
                }
                
                try:
                    await self.websocket.send(json.dumps(message))
                except:
                    pass
            
            await asyncio.sleep(1.0 / 60.0)
    
    def setup_display(self):
        self.screen = pygame.display.set_mode((self.game_width, self.game_height))
        pygame.display.set_caption("Multiplayer Coin Collector")
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
            elif event.type == pygame.KEYUP:
                self.keys_pressed.discard(event.key)
    
    def render(self):
        self.screen.fill((30, 30, 30))
        
        render_state = self.get_interpolated_state()
        
        for coin in render_state['coins']:
            cx = int(coin['x'])
            cy = int(coin['y'])
            pygame.draw.circle(self.screen, (255, 215, 0), (cx, cy), self.coin_radius)
            pygame.draw.circle(self.screen, (200, 170, 0), (cx, cy), self.coin_radius, 1)
        
        players = render_state['players']
        for pid, p in players.items():
            color = tuple(p.get('color', (255, 100, 100)))
            center_x = int(p['x'])
            center_y = int(p['y'])
            
            if pid == self.player_id:
                pygame.draw.circle(self.screen, (255, 255, 255), (center_x, center_y), self.player_radius + 3, 2)
            
            pygame.draw.circle(self.screen, color, (center_x, center_y), self.player_radius)
            
            score_text = self.small_font.render(f"P{pid[-4:]}: {p['score']}", True, (255, 255, 255))
            self.screen.blit(score_text, (center_x - 20, center_y - 35))

        if self.game_started:
            info_text = self.font.render(f"Simulated Latency: 200ms", True, (200, 200, 200))
            self.screen.blit(info_text, (10, self.game_height - 30))
            
            legend_y = 10
            legend_x = 10
            title = self.font.render("SCORES:", True, (255, 255, 255))
            self.screen.blit(title, (legend_x, legend_y))
            legend_x += title.get_width() + 15
            
            sorted_players = sorted(players.items(), key=lambda x: x[0])
            
            for pid, p in sorted_players:
                if pid == self.player_id:
                    color = (100, 200, 255)
                    name = "YOU"
                else:
                    color = (255, 100, 100)
                    name = f"P{pid[-4:]}"
                
                score_text = self.font.render(f"{name}: {p['score']}", True, color)
                self.screen.blit(score_text, (legend_x, legend_y))
                legend_x += score_text.get_width() + 15
                
        else:
            waiting_text = self.font.render("Waiting for players...", True, (200, 200, 200))
            self.screen.blit(waiting_text, (self.game_width // 2 - 80, self.game_height // 2))
    
        pygame.display.flip()

    async def run(self):
        await self.connect()
        self.setup_display()
        
        asyncio.create_task(self.receive_messages())
        asyncio.create_task(self.send_input())
        
        while self.running:
            self.handle_events()
            self.render()
            self.clock.tick(RENDER_FPS)
            await asyncio.sleep(0.001)
        
        pygame.quit()

if __name__ == "__main__":
    client = GameClient()
    asyncio.run(client.run())