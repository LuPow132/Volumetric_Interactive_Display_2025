import bpy
import bmesh
import socket
import struct
import gzip
import numpy as np
from mathutils import Vector
from collections import defaultdict
import threading
import time

# --- CONFIGURATION ---
HOST_IP = '192.168.1.40'  # Your Raspberry Pi IP
PORT = 0x5658

VOX_X = 128
VOX_Y = 128
VOX_Z = 64

# Capture volume bounds (adjust to your needs)
# Use cubic volume for proper aspect ratio
CAPTURE_MIN = Vector((-5, -5, -2.5))
CAPTURE_MAX = Vector((5, 5, 2.5))

# Performance settings
VOXEL_SAMPLE_RATE = 1.0  # 1.0 = sample every voxel, 0.5 = every other voxel
SURFACE_THICKNESS = 1    # How many voxel layers thick surfaces are
ENABLE_INTERIOR_FILL = False  # Fill solid objects (expensive)
MAX_POINTS_PER_FRAME = 100000  # Limit points to prevent overload

# --- COLOR CONVERSION ---
def rgb_to_332(r, g, b):
    """Convert RGB float (0-1) to 332 format (RRR GG BB)"""
    r_bits = int(r * 7) & 0x07
    g_bits = int(g * 3) & 0x03
    b_bits = int(b * 3) & 0x03
    return (r_bits << 5) | (g_bits << 3) | b_bits

def world_to_voxel(world_pos):
    """Convert world coordinates to voxel coordinates with aspect ratio correction"""
    # Calculate world space dimensions
    world_width_x = CAPTURE_MAX.x - CAPTURE_MIN.x
    world_width_y = CAPTURE_MAX.y - CAPTURE_MIN.y
    world_width_z = CAPTURE_MAX.z - CAPTURE_MIN.z
    
    # Calculate aspect ratios (relative to Z which is smallest)
    aspect_x = VOX_X / VOX_Z  # 128/64 = 2.0
    aspect_y = VOX_Y / VOX_Z  # 128/64 = 2.0
    aspect_z = 1.0
    
    # Apply aspect correction to world coordinates
    # This makes circles appear as circles on the display
    corrected_x = (world_pos.x - CAPTURE_MIN.x) / world_width_x
    corrected_y = (world_pos.y - CAPTURE_MIN.y) / world_width_y
    corrected_z = (world_pos.z - CAPTURE_MIN.z) / world_width_z
    
    # Scale to voxel space
    vox_x = int(corrected_x * VOX_X)
    vox_y = int(corrected_y * VOX_Y)
    vox_z = int(corrected_z * VOX_Z)
    
    return vox_x, vox_y, vox_z

def is_in_bounds(vox_x, vox_y, vox_z):
    """Check if voxel coordinates are valid"""
    return 0 <= vox_x < VOX_X and 0 <= vox_y < VOX_Y and 0 <= vox_z < VOX_Z

def get_object_color(obj):
    """Extract color from object material"""
    if obj.active_material and obj.active_material.use_nodes:
        nodes = obj.active_material.node_tree.nodes
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                base_color = node.inputs['Base Color'].default_value
                return base_color[0], base_color[1], base_color[2]
    
    # Fallback to viewport color
    if hasattr(obj, 'color'):
        return obj.color[0], obj.color[1], obj.color[2]
    
    return 1.0, 1.0, 1.0  # White default

def bresenham_3d(x0, y0, z0, x1, y1, z1):
    """3D Bresenham line algorithm for solid voxel lines"""
    points = []
    
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    dz = abs(z1 - z0)
    
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    sz = 1 if z0 < z1 else -1
    
    # Driving axis
    if dx >= dy and dx >= dz:
        err_y = 2 * dy - dx
        err_z = 2 * dz - dx
        while x0 != x1:
            points.append((x0, y0, z0))
            if err_y > 0:
                y0 += sy
                err_y -= 2 * dx
            if err_z > 0:
                z0 += sz
                err_z -= 2 * dx
            err_y += 2 * dy
            err_z += 2 * dz
            x0 += sx
    elif dy >= dx and dy >= dz:
        err_x = 2 * dx - dy
        err_z = 2 * dz - dy
        while y0 != y1:
            points.append((x0, y0, z0))
            if err_x > 0:
                x0 += sx
                err_x -= 2 * dy
            if err_z > 0:
                z0 += sz
                err_z -= 2 * dy
            err_x += 2 * dx
            err_z += 2 * dz
            y0 += sy
    else:
        err_x = 2 * dx - dz
        err_y = 2 * dy - dz
        while z0 != z1:
            points.append((x0, y0, z0))
            if err_x > 0:
                x0 += sx
                err_x -= 2 * dz
            if err_y > 0:
                y0 += sy
                err_y -= 2 * dz
            err_x += 2 * dx
            err_y += 2 * dy
            z0 += sz
    
    points.append((x1, y1, z1))
    return points

def clip_line_to_bounds(p0, p1):
    """
    Clip a 3D line segment to the voxel bounds using Liang-Barsky algorithm.
    Returns clipped endpoints or None if line is completely outside.
    """
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    
    dx = x1 - x0
    dy = y1 - y0
    dz = z1 - z0
    
    t_min = 0.0
    t_max = 1.0
    
    # Check each axis
    bounds = [
        (-dx, x0, 0),           # Left (x = 0)
        (dx, VOX_X - 1 - x0, 0),# Right (x = VOX_X-1)
        (-dy, y0, 1),           # Bottom (y = 0)
        (dy, VOX_Y - 1 - y0, 1),# Top (y = VOX_Y-1)
        (-dz, z0, 2),           # Front (z = 0)
        (dz, VOX_Z - 1 - z0, 2) # Back (z = VOX_Z-1)
    ]
    
    for p, q, axis in bounds:
        if p == 0:
            # Line is parallel to this plane
            if q < 0:
                return None  # Line is outside
        else:
            t = q / p
            if p < 0:
                # Entering
                t_min = max(t_min, t)
            else:
                # Exiting
                t_max = min(t_max, t)
            
            if t_min > t_max:
                return None  # Line is completely outside
    
    # Calculate clipped endpoints
    clipped_x0 = int(x0 + t_min * dx)
    clipped_y0 = int(y0 + t_min * dy)
    clipped_z0 = int(z0 + t_min * dz)
    
    clipped_x1 = int(x0 + t_max * dx)
    clipped_y1 = int(y0 + t_max * dy)
    clipped_z1 = int(z0 + t_max * dz)
    
    # Clamp to ensure within bounds (floating point safety)
    clipped_x0 = max(0, min(VOX_X - 1, clipped_x0))
    clipped_y0 = max(0, min(VOX_Y - 1, clipped_y0))
    clipped_z0 = max(0, min(VOX_Z - 1, clipped_z0))
    
    clipped_x1 = max(0, min(VOX_X - 1, clipped_x1))
    clipped_y1 = max(0, min(VOX_Y - 1, clipped_y1))
    clipped_z1 = max(0, min(VOX_Z - 1, clipped_z1))
    
    return (clipped_x0, clipped_y0, clipped_z0), (clipped_x1, clipped_y1, clipped_z1)

def voxelize_object(obj):
    """Convert mesh object to voxel points with smart edge clipping"""
    if obj.type != 'MESH':
        return []
    
    # Get world matrix
    mat = obj.matrix_world
    
    # Get object color
    r, g, b = get_object_color(obj)
    color = rgb_to_332(r, g, b)
    
    # Use evaluated mesh (includes modifiers)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    
    voxel_dict = {}  # Use dict to avoid duplicates
    
    try:
        # First pass: Convert all vertices to voxel space (even if out of bounds)
        # This is needed for edge calculations
        all_voxel_verts = []
        for vert in mesh.vertices:
            world_pos = mat @ vert.co
            vox_x, vox_y, vox_z = world_to_voxel(world_pos)
            all_voxel_verts.append((vox_x, vox_y, vox_z))
        
        # Track which vertices are visible (within bounds)
        visible_verts = set()
        
        # Add visible vertices
        for idx, (vox_x, vox_y, vox_z) in enumerate(all_voxel_verts):
            if is_in_bounds(vox_x, vox_y, vox_z):
                voxel_dict[(vox_x, vox_y, vox_z)] = color
                visible_verts.add(idx)
        
        # Second pass: Process edges with intelligent clipping
        for edge in mesh.edges:
            v0_idx, v1_idx = edge.vertices
            
            vox0 = all_voxel_verts[v0_idx]
            vox1 = all_voxel_verts[v1_idx]
            
            v0_visible = v0_idx in visible_verts
            v1_visible = v1_idx in visible_verts
            
            # Case 1: Both vertices visible - draw the line
            if v0_visible and v1_visible:
                if is_in_bounds(*vox0) and is_in_bounds(*vox1):
                    line_points = bresenham_3d(*vox0, *vox1)
                    for pt in line_points:
                        voxel_dict[pt] = color
            
            # Case 2: At least one vertex visible or line passes through bounds
            # Use line clipping to render partial edges
            else:
                clipped = clip_line_to_bounds(vox0, vox1)
                if clipped is not None:
                    clipped_p0, clipped_p1 = clipped
                    # Draw the clipped portion
                    line_points = bresenham_3d(*clipped_p0, *clipped_p1)
                    for pt in line_points:
                        if is_in_bounds(*pt):
                            voxel_dict[pt] = color
        
        # Optional: Fill faces for solid appearance
        if SURFACE_THICKNESS > 1:
            for face in mesh.polygons:
                # Get face center
                center = mat @ face.center
                vox_c = world_to_voxel(center)
                
                if is_in_bounds(*vox_c):
                    # Add thickness around face center
                    for dx in range(-SURFACE_THICKNESS//2, SURFACE_THICKNESS//2 + 1):
                        for dy in range(-SURFACE_THICKNESS//2, SURFACE_THICKNESS//2 + 1):
                            for dz in range(-SURFACE_THICKNESS//2, SURFACE_THICKNESS//2 + 1):
                                px = vox_c[0] + dx
                                py = vox_c[1] + dy
                                pz = vox_c[2] + dz
                                if is_in_bounds(px, py, pz):
                                    voxel_dict[(px, py, pz)] = color
    
    finally:
        obj_eval.to_mesh_clear()
    
    # Convert dict to list
    points = [(x, y, z, c) for (x, y, z), c in voxel_dict.items()]
    
    return points

def generate_packet(points):
    """Create compressed packet for transmission"""
    # Limit points to prevent overload
    if len(points) > MAX_POINTS_PER_FRAME:
        points = points[:MAX_POINTS_PER_FRAME]
    
    # Pack into binary
    raw_data = bytearray()
    for p in points:
        raw_data.extend(struct.pack('BBBB', *p))
    
    # Compress
    compressed = gzip.compress(raw_data, compresslevel=1)  # Fast compression
    header = b'\xff\xff\xff\xff'
    length = struct.pack('>I', len(compressed))
    
    return header + length + compressed

# --- NETWORK THREAD ---
class VoxelSender:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.thread = None
        self.packet_queue = []
        self.lock = threading.Lock()
        
    def connect(self):
        """Establish connection to receiver"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            print(f"✓ Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def send_packet(self, packet):
        """Queue packet for sending"""
        with self.lock:
            # Keep only latest packet to reduce lag
            self.packet_queue = [packet]
    
    def _send_loop(self):
        """Background thread for sending packets"""
        while self.running:
            packet = None
            with self.lock:
                if self.packet_queue:
                    packet = self.packet_queue.pop(0)
            
            if packet:
                try:
                    self.sock.sendall(packet)
                except Exception as e:
                    print(f"✗ Send error: {e}")
                    break
            else:
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
    
    def start(self):
        """Start background sender thread"""
        if self.connect():
            self.running = True
            self.thread = threading.Thread(target=self._send_loop, daemon=True)
            self.thread.start()
            return True
        return False
    
    def stop(self):
        """Stop sender and close connection"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.sock:
            self.sock.close()
        print("✓ Disconnected")

# --- GLOBAL SENDER ---
sender = None

# --- BLENDER MODAL OPERATOR ---
class VOXEL_OT_stream(bpy.types.Operator):
    """Stream Blender scene to voxel display"""
    bl_idname = "voxel.stream"
    bl_label = "Stream to Voxel Display"
    
    _timer = None
    
    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            # Voxelize all visible mesh objects in capture volume
            all_points = []
            
            for obj in context.scene.objects:
                if obj.type == 'MESH' and not obj.hide_render and not obj.hide_viewport:
                    # Quick bounds check
                    bbox_min = Vector((min(v[i] for v in obj.bound_box) for i in range(3)))
                    bbox_max = Vector((max(v[i] for v in obj.bound_box) for i in range(3)))
                    
                    # Transform to world space
                    bbox_min = obj.matrix_world @ bbox_min
                    bbox_max = obj.matrix_world @ bbox_max
                    
                    # Check if object intersects capture volume
                    if not (bbox_max.x < CAPTURE_MIN.x or bbox_min.x > CAPTURE_MAX.x or
                            bbox_max.y < CAPTURE_MIN.y or bbox_min.y > CAPTURE_MAX.y or
                            bbox_max.z < CAPTURE_MIN.z or bbox_min.z > CAPTURE_MAX.z):
                        points = voxelize_object(obj)
                        all_points.extend(points)
            
            # Send to display
            if sender and all_points:
                packet = generate_packet(all_points)
                sender.send_packet(packet)
            
            # Update status
            context.area.tag_redraw()
        
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        global sender
        
        # Initialize sender
        sender = VoxelSender(HOST_IP, PORT)
        if not sender.start():
            self.report({'ERROR'}, "Failed to connect to display")
            return {'CANCELLED'}
        
        # Setup timer for updates
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.033, window=context.window)  # ~30 FPS
        wm.modal_handler_add(self)
        
        self.report({'INFO'}, "Streaming started. Press ESC to stop.")
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        global sender
        
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
        
        if sender:
            sender.stop()
            sender = None
        
        self.report({'INFO'}, "Streaming stopped")

# --- UI PANEL ---
class VOXEL_PT_panel(bpy.types.Panel):
    """Panel for voxel display streaming"""
    bl_label = "Voxel Display Stream"
    bl_idname = "VOXEL_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Voxel'
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Capture Volume:")
        box.label(text=f"Min: {CAPTURE_MIN}")
        box.label(text=f"Max: {CAPTURE_MAX}")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Display Resolution:")
        box.label(text=f"{VOX_X} × {VOX_Y} × {VOX_Z}")
        
        layout.separator()
        
        if sender and sender.running:
            layout.label(text="● Streaming Active", icon='REC')
            layout.operator("voxel.stream", text="Stop (ESC)")
        else:
            layout.label(text="○ Idle", icon='PAUSE')
            layout.operator("voxel.stream", text="Start Stream")

# --- REGISTRATION ---
classes = (
    VOXEL_OT_stream,
    VOXEL_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    global sender
    if sender:
        sender.stop()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
    print("✓ Voxel Display addon loaded!")
    print(f"  Connect to: {HOST_IP}:{PORT}")
    print(f"  Capture volume: {CAPTURE_MIN} to {CAPTURE_MAX}")
