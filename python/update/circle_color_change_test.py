import socket
import struct
import gzip
import time
import math
import pygame
import sys

# --- CONFIGURATION ---
HOST_IP = '192.168.1.38'  # <--- REPLACE with your Pi's IP
PORT = 0x5658

# Display Size
VOX_X = 128
VOX_Y = 128
VOX_Z = 64

# --- COLOR DEFINITIONS (RRR GG BB) ---
COLORS = [
    0xE0,  # Red     (111 00 00)
    0x1C,  # Green   (000 111 00)
    0x03,  # Blue    (000 00 11)
    0xFC,  # Yellow  (111 111 00)
    0x1F,  # Cyan    (000 111 11)
    0xE3,  # Magenta (111 00 11)
    0xFF,  # White   (111 111 11)
]

def generate_sphere_packet(cx, cy, cz, radius, color):
    """
    Generates a solid 3D sphere at center (cx, cy, cz).
    """
    points = []
    
    # Optimization: Only scan the bounding box
    min_x = int(max(0, cx - radius))
    max_x = int(min(VOX_X, cx + radius + 1))
    
    min_y = int(max(0, cy - radius))
    max_y = int(min(VOX_Y, cy + radius + 1))
    
    min_z = int(max(0, cz - radius))
    max_z = int(min(VOX_Z, cz + radius + 1))

    radius_sq = radius * radius

    for x in range(min_x, max_x):
        for y in range(min_y, max_y):
            for z in range(min_z, max_z):
                # Distance formula
                if (x - cx)**2 + (y - cy)**2 + (z - cz)**2 <= radius_sq:
                    points.append((x, y, z, color))

    # Pack into binary
    raw_data = bytearray()
    for p in points:
        raw_data.extend(struct.pack('BBBB', *p))

    # Compress
    compressed = gzip.compress(raw_data)
    header = b'\xff\xff\xff\xff'
    length = struct.pack('>I', len(compressed))
    
    return header + length + compressed

def main():
    # 1. Init Pygame
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    pygame.display.set_caption("Press SPACE to Change Color")
    font = pygame.font.SysFont("Arial", 24)

    # 2. Connect to Raspberry Pi
    print(f"Connecting to {HOST_IP}:{PORT}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST_IP, PORT))
        print("Connected! Press SPACEBAR to change colors.")
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    # 3. Animation State
    t = 0.0
    sphere_radius = 8
    
    # Start with the first color (Red)
    color_index = 0
    current_color = COLORS[color_index]

    running = True
    clock = pygame.time.Clock()

    while running:
        # --- A. INPUT HANDLING ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            # Detect Key Press
            if event.type == pygame.KEYDOWN:
                # Cycle to the next color in the list
                color_index = (color_index + 1) % len(COLORS)
                current_color = COLORS[color_index]
                print(f"Color changed! Index: {color_index}")

        # --- B. ANIMATION LOGIC (ORBIT) ---
        orbit_radius_xy = 35 
        orbit_radius_z = 20
        
        center_x = VOX_X / 2
        center_y = VOX_Y / 2
        center_z = VOX_Z / 2
        
        pos_x = center_x + orbit_radius_xy * math.cos(t)
        pos_y = center_y + orbit_radius_xy * math.sin(t)
        pos_z = center_z + orbit_radius_z * math.sin(t)

        # --- C. SEND DATA ---
        try:
            packet = generate_sphere_packet(pos_x, pos_y, pos_z, sphere_radius, current_color)
            sock.sendall(packet)
        except Exception as e:
            print(f"Transmission Error: {e}")
            break

        # --- D. UPDATE PC WINDOW ---
        screen.fill((0, 0, 0))
        
        # Display instructions
        text_info = font.render(f"Color: {hex(current_color)}", True, (255, 255, 255))
        text_instr = font.render("Press SPACE to switch", True, (150, 150, 150))
        
        screen.blit(text_info, (20, 20))
        screen.blit(text_instr, (20, 60))
        
        # Draw a little preview circle in the corner
        pygame.draw.circle(screen, (255, 255, 255), (350, 50), 20)

        pygame.display.flip()
        
        # Increment time and wait
        t += 0.05
        clock.tick(30) # 30 FPS

    sock.close()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
