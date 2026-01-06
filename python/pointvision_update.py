import ctypes
import os
import mmap
import threading
import queue
import numpy as np
import asyncio
import struct
import gzip

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

data_queue = queue.Queue(maxsize=2)

def process_data(data_queue):
    print("[Thread] Processing thread started...")
    try:
        shm_fd = os.open("/dev/shm/vortex_double_buffer", os.O_RDWR)
        shm_mm = mmap.mmap(shm_fd, ctypes.sizeof(voxel_double_buffer_t), mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        buffer = voxel_double_buffer_t.from_buffer(shm_mm)
        print("[Thread] Shared Memory Connected Successfully!")

        while True:
            data = data_queue.get() 
            try:
                page = 1 - buffer.page
                ctypes.memset(ctypes.byref(buffer, page * voxels_count), 0, voxels_count)
                
                point_data = np.frombuffer(data, dtype=np.uint8).reshape(-1, 4)
                x = point_data[:, 0]
                y = point_data[:, 1]
                z = point_data[:, 2]
                pix = point_data[:, 3]
                
                # Safety Check: Remove points that are out of bounds
                valid_mask = (x < voxels_x) & (y < voxels_y) & (z < voxels_z)
                if not np.all(valid_mask):
                    print(f"[Thread] Warning: Ignoring {np.sum(~valid_mask)} out-of-bound points")
                    x, y, z, pix = x[valid_mask], y[valid_mask], z[valid_mask], pix[valid_mask]

                voxels = np.ctypeslib.as_array(buffer.buffers[page]).reshape((128,128,64))
                voxels[y, x, z] = pix
                buffer.page = page
            
            except Exception as e:
                print(f"[Thread] Error processing frame: {e}")

    except FileNotFoundError:
        print("\n[Thread] CRITICAL ERROR: '/dev/shm/vortex_double_buffer' NOT FOUND.")
        print("          Did you run the C driver (sudo ./vortex) first?")
    except Exception as e:
        print(f"[Thread] CRITICAL ERROR: {e}")

async def handle_client(reader, writer):
    print(f"[Server] Client connected from {writer.get_extra_info('peername')}")
    try:
        while True:
            # 1. Read Header (8 bytes)
            header = await reader.readexactly(8)
            if header[:4] != b'\xff\xff\xff\xff':
                print("[Server] Error: Invalid header signature.")
                break

            # 2. Read Length
            packet_length = struct.unpack('!I', header[4:])[0]
            
            # 3. Read Payload
            data = await reader.readexactly(packet_length)
            
            # 4. Process
            try:
                decompressed = gzip.decompress(data)
                if not data_queue.full():
                    data_queue.put(decompressed)
            except gzip.BadGzipFile:
                print("[Server] Error: Bad GZIP data.")
                continue

    except asyncio.IncompleteReadError:
        print("[Server] Client disconnected (Stream ended unexpectedly).")
    except Exception as e:
        print(f"[Server] Connection Error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        print("[Server] Connection closed.")

async def main():
    host = '0.0.0.0' # Listen on ALL interfaces
    port = 0x5658
    
    print(f"[Main] Server listening on {host}:{port}")
    
    proc_thread = threading.Thread(target=process_data, args=(data_queue,), daemon=True)
    proc_thread.start()

    server = await asyncio.start_server(handle_client, host, port)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Main] Stopping server...")
