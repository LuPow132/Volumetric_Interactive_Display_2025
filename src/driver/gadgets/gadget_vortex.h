#ifndef _GADGET_H_
#define _GADGET_H_

#define SPIN_SYNC 1

// --- HZELLER "REGULAR" MAPPING (Chain 0) ---
// These match the standard wiring.md for Raspberry Pi
#define RGB_0_R1 17
#define RGB_0_G1 18
#define RGB_0_B1 22
#define RGB_0_R2 23
#define RGB_0_G2 24
#define RGB_0_B2 25

// --- SECOND CHAIN (Not available in standard Regular wiring) ---
// "Regular" wiring supports only 1 chain. To use 2 panels, 
// chain them in series and drive them both using RGB_0.
// These are left as placeholders or custom assignments.
#define RGB_1_B1 6
#define RGB_1_G1 5
#define RGB_1_R1 12
#define RGB_1_B2 20
#define RGB_1_G2 13
#define RGB_1_R2 19

// --- ADDRESSING ---
// Mapped to Hzeller A, B, C. 
// NOTE: Standard HUB75 uses Parallel A/B/C/D, not CLK/DAT serial.
// You may need to modify your main code logic to treat these as parallel bits.
#define ADDR_CLK 7   // Mapped to Pin A
#define ADDR_DAT 8   // Mapped to Pin B
#define ADDR__EN 9   // Mapped to Pin C
// If you use a 32-row panel, you also need Pin D (GPIO 10).
#define ADDR__EN_MASK (1<<ADDR__EN)

// --- CONTROL PINS ---
// Matched to Hzeller defaults
#define RGB_BLANK  27  // OE (Output Enable)
#define RGB_CLOCK  11  // CLK (Clock)
#define RGB_STROBE 4   // LAT (Latch)

#define RGB_BLANK_MASK (1<<RGB_BLANK)
#define RGB_CLOCK_MASK (1<<RGB_CLOCK)
#define RGB_STROBE_MASK (1<<RGB_STROBE)

#define RGB_0_MASK ((1<<RGB_0_R1)|(1<<RGB_0_G1)|(1<<RGB_0_B1)|(1<<RGB_0_R2)|(1<<RGB_0_G2)|(1<<RGB_0_B2))
#define RGB_1_MASK ((1<<RGB_1_R1)|(1<<RGB_1_G1)|(1<<RGB_1_B1)|(1<<RGB_1_R2)|(1<<RGB_1_G2)|(1<<RGB_1_B2))
#define RGB_BITS_MASK (RGB_0_MASK | RGB_1_MASK)

static const int matrix_init_out[] = {RGB_0_B1, RGB_0_G1, RGB_0_R1, RGB_0_B2, RGB_0_G2, RGB_0_R2, RGB_1_B1, RGB_1_G1, RGB_1_R1, RGB_1_B2, RGB_1_G2, RGB_1_R2, ADDR_CLK, ADDR_DAT, ADDR__EN, RGB_BLANK, RGB_CLOCK, RGB_STROBE};

#define PANEL_WIDTH  128
#define PANEL_HEIGHT 64
#define PANEL_COUNT 2
#define PANEL_MULTIPLEX 2
#define PANEL_FIELD_HEIGHT (PANEL_HEIGHT / PANEL_MULTIPLEX)

#define PANEL_0_ORDER(c) (c)
#define PANEL_1_ORDER(c) (c)

#define PANEL_0_ECCENTRICITY 13.5
#define PANEL_1_ECCENTRICITY 0.375

#define VOXELS_X 128
#define VOXELS_Y 128
#define VOXELS_Z 64

#define VOXEL_Z_STRIDE 1
#define VOXEL_X_STRIDE VOXELS_Z
#define VOXEL_Y_STRIDE (VOXEL_X_STRIDE * VOXELS_X)
#define VOXELS_COUNT (VOXELS_X*VOXELS_Y*VOXELS_Z)

#define ROTATION_ZERO 286

#define CLOCK_WAITS 7

#endif
