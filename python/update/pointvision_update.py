import ctypes
import os
import mmap
import threading
import numpy as np
import asyncio
import struct
import gzip
from collections import deque

# --- CONFIGURATION ---
# These must match your C driver exactly
voxels_x = 128
voxels_y = 128
voxels_z = 64
voxels_count = voxels_x * voxels_y * voxels_z

class voxel_double_buffer_t(ctypes.Structure):
    _fields_ = [("buffers", ctypes.c_uint8 * voxels_z * voxels_x * voxels_y * 2),
                ("page", ctypes.c_uint8),
                ("bpc",  ctypes.c_uint8),
                ("flags",  ctypes.c_uint16),
                ("rpm", ctypes.c_uint16),
                ("uspf", ctypes.c_uint16)]

# Use deque with maxlen=1 for automatic dropping of old frames
frame_queue = deque(maxlen=1)
queue_lock = threading.Lock()

# Pre-allocate reusable buffer for point data
point_buffer = np.empty((voxels_count, 4), dtype=np.uint8)

def process_data():
    """Optimized processing thread with minimal allocations"""
    print("[Thread] Processing thread started...")
    
    try:
        # Open shared memory once
        shm_fd = os.open("/dev/shm/vortex_double_buffer", os.O_RDWR)
        shm_mm = mmap.mmap(shm_fd, ctypes.sizeof(voxel_double_buffer_t), 
                          mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        buffer = voxel_double_buffer_t.from_buffer(shm_mm)
        print("[Thread] Shared Memory Connected Successfully!")
        
        # Pre-compute buffer offset for faster access
        buffer_size = voxels_count
        
        # Cache the voxel array views (only create once per page)
        voxel_views = [
            np.ctypeslib.as_array(buffer.buffers[0]).reshape((voxels_y, voxels_x, voxels_z)),
            np.ctypeslib.as_array(buffer.buffers[1]).reshape((voxels_y, voxels_x, voxels_z))
        ]
        
        frame_count = 0
        last_print = 0
        
        while True:
            # Non-blocking queue check
            data = None
            with queue_lock:
                if frame_queue:
                    data = frame_queue.popleft()
            
            if data is None:
                # Small sleep to prevent CPU spinning
                threading.Event().wait(0.001)
                continue
            
            try:
                # Get inactive page
                current_page = buffer.page
                write_page = 1 - current_page
                
                # Get view for writing
                voxels = voxel_views[write_page]
                
                # Fast clear using numpy
                voxels.fill(0)
                
                # Parse point data
                num_points = len(data) // 4
                
                if num_points == 0:
                    continue
                
                # Reuse pre-allocated buffer if possible
                if num_points <= len(point_buffer):
                    point_data = np.frombuffer(data, dtype=np.uint8).reshape(-1, 4)
                else:
                    point_data = np.frombuffer(data, dtype=np.uint8).reshape(-1, 4)
                
                # Extract coordinates (vectorized)
                x = point_data[:, 0]
                y = point_data[:, 1]
                z = point_data[:, 2]
                pix = point_data[:, 3]
                
                # Vectorized bounds checking
                valid_mask = (x < voxels_x) & (y < voxels_y) & (z < voxels_z)
                num_invalid = np.sum(~valid_mask)
                
                if num_invalid > 0:
                    # Only filter if there are invalid points
                    x = x[valid_mask]
                    y = y[valid_mask]
                    z = z[valid_mask]
                    pix = pix[valid_mask]
                    
                    if num_invalid > 10:  # Only warn if significant
                        print(f"[Thread] Warning: Filtered {num_invalid} out-of-bound points")
                
                # Fast assignment using advanced indexing
                if len(x) > 0:
                    voxels[y, x, z] = pix
                
                # Atomic page flip
                buffer.page = write_page
                
                # Performance monitoring (every 100 frames)
                frame_count += 1
                if frame_count - last_print >= 100:
                    print(f"[Thread] Processed {frame_count} frames ({len(x)} points)")
                    last_print = frame_count
            
            except Exception as e:
                print(f"[Thread] Error processing frame: {e}")
                import traceback
                traceback.print_exc()

    except FileNotFoundError:
        print("\n[Thread] CRITICAL ERROR: '/dev/shm/vortex_double_buffer' NOT FOUND.")
        print("          Did you run the C driver (sudo ./vortex) first?")
    except Exception as e:
        print(f"[Thread] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

async def handle_client(reader, writer):
    """Optimized client handler with better buffer management"""
    peer = writer.get_extra_info('peername')
    print(f"[Server] Client connected from {peer}")
    
    try:
        while True:
            # 1. Read Header (8 bytes)
            header = await reader.readexactly(8)
            
            # 2. Validate signature
            if header[:4] != b'\xff\xff\xff\xff':
                print("[Server] Error: Invalid header signature.")
                break

            # 3. Extract length
            packet_length = struct.unpack('!I', header[4:])[0]
            
            # Sanity check packet length (prevent memory attacks)
            if packet_length > 10_000_000:  # 10MB max
                print(f"[Server] Error: Packet too large ({packet_length} bytes)")
                break
            
            # 4. Read Payload
            compressed_data = await reader.readexactly(packet_length)
            
            # 5. Decompress in background (non-blocking for network)
            try:
                decompressed = gzip.decompress(compressed_data)
                
                # Only keep latest frame (drop old ones)
                with queue_lock:
                    frame_queue.append(decompressed)
                    
            except gzip.BadGzipFile:
                print("[Server] Error: Bad GZIP data.")
                continue
            except Exception as e:
                print(f"[Server] Decompression error: {e}")
                continue

    except asyncio.IncompleteReadError:
        print(f"[Server] Client {peer} disconnected (stream ended).")
    except ConnectionResetError:
        print(f"[Server] Client {peer} connection reset.")
    except Exception as e:
        print(f"[Server] Connection Error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass
        print(f"[Server] Connection from {peer} closed.")

async def main():
    """Main server with optimized settings"""
    host = '0.0.0.0'  # Listen on ALL interfaces
    port = 0x5658
    
    print(f"[Main] Voxel Receiver starting...")
    print(f"[Main] Display: {voxels_x}x{voxels_y}x{voxels_z}")
    print(f"[Main] Listening on {host}:{port}")
    
    # Start processing thread
    proc_thread = threading.Thread(target=process_data, daemon=True)
    proc_thread.start()
    
    # Create server with optimized settings
    server = await asyncio.start_server(
        handle_client, 
        host, 
        port,
        backlog=5,  # Limit connection queue
    )
    
    async with server:
        print("[Main] Server ready!")
        await server.serve_forever()

if __name__ == "__main__":
    try:
        # Set higher priority for better real-time performance
        try:
            import psutil
            p = psutil.Process()
            p.nice(-10)  # Higher priority (requires sudo on Linux)
            print("[Main] Running with elevated priority")
        except:
            pass
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n[Main] Stopping server...")
    except Exception as e:
        print(f"[Main] Fatal error: {e}")
        import traceback
        traceback.print_exc()
