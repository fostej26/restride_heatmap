# As-built wiring

Keep this in step with `insole_mux_schematic.svg` (PNG copy beside it). Tick the boxes as you build.
Pin numbers below are copied from the Rev B handoff (`RESTRIDE_INSOLE_HEATMAP_HANDOFF.md`, section 4).

**Power: set nRF VDD = 3.3 V in Board Configurator before powering the breadboard. Never put 5 V (P30-P32) into this circuit.**

## 1. Insole FPC tail (20 pins)

| FPC pin | Function | Connect to |
|---|---|---|
| 1 | Common electrode (PWR) | DK VDD (3.3 V) |
| 6, 14 | GND | DK GND |
| 11 | No connection | leave open |
| 2,3,4,5,7,8,9,10,12,13,15,16,17,18,19,20 | Sensor sense lines | one 74HC4066 switch each (section 4) |

Bring-up check before wiring (multimeter, resistance range): pin 1 to each sensor pin should read open/high unloaded and drop when pressed; pins 6 and 14 must not read low to pin 1 or to any sensor pin.

- [ ] Multimeter check done
- [ ] Pin-1 end of the tail identified; photo saved in `docs/` (`fpc_pin1.jpg`)
- [ ] FPC pitch (0.5 / 1.0 mm) and contact side recorded: ______

## 2. DK connections

| DK pin | Net | Notes |
|---|---|---|
| P2.06 | A0 | trace CLK pin, tracing off |
| P2.08 | A1 | Trace[1], tracing off |
| P2.10 | A2 | Trace[3], tracing off |
| P1.11 (AIN4) | BUS_A | |
| P1.12 (AIN5) | BUS_B | |
| VDD | VDD rail | 3.3 V |
| GND | GND rail | also FPC 6 and 14 |

Avoid: P1.08, P1.09, P1.13, P0.04 (buttons); P1.10, P1.14, P2.07, P2.09 (LEDs); P1.04-P1.07 (UART/console); P2.00-P2.05 (external flash).

## 3. Parts

U1-U3 74HC00, U4-U6 74HC10, U7-U10 74HC4066, R_refA / R_refB 10 k 1 % (BUS_A / BUS_B to GND), C1-C10 100 nF (pin 14 to pin 7 on every IC), J1 20-pin FPC breakout. All 14-pin ICs: VCC = pin 14, GND = pin 7. Use 74HC, not 74LS.

## 4. Decoder

Address inverters (74HC00): U1A (1,2 -> 3) = ~A0; U1B (4,5 -> 6) = ~A1; U1C (9,10 -> 8) = ~A2.

| k | A2A1A0 | NAND3 (pins in -> out) | inputs | SEL inverter (in -> out) |
|---|---|---|---|---|
| 0 | 000 | U4A (1,2,13 -> 12) | ~A2 ~A1 ~A0 | U1D (12,13 -> 11) |
| 1 | 001 | U4B (3,4,5 -> 6)   | ~A2 ~A1 A0  | U2A (1,2 -> 3) |
| 2 | 010 | U4C (9,10,11 -> 8) | ~A2 A1 ~A0  | U2B (4,5 -> 6) |
| 3 | 011 | U5A (1,2,13 -> 12) | ~A2 A1 A0   | U2C (9,10 -> 8) |
| 4 | 100 | U5B (3,4,5 -> 6)   | A2 ~A1 ~A0  | U2D (12,13 -> 11) |
| 5 | 101 | U5C (9,10,11 -> 8) | A2 ~A1 A0   | U3A (1,2 -> 3) |
| 6 | 110 | U6A (1,2,13 -> 12) | A2 A1 ~A0   | U3B (4,5 -> 6) |
| 7 | 111 | U6B (3,4,5 -> 6)   | A2 A1 A0    | U3C (9,10 -> 8) |

Spare gates U3D and U6C: all inputs to GND. No floating CMOS inputs anywhere (unused 4066 E pins to GND).

## 5. Analog switches (74HC4066: SW1 = Y1/Z2/E13, SW2 = Y4/Z3/E5, SW3 = Y8/Z9/E6, SW4 = Y11/Z10/E12)

| k | SELk drives | Bank A: FPC pin -> switch (to BUS_A) | Bank B: FPC pin -> switch (to BUS_B) | firmware ch (A / B) |
|---|---|---|---|---|
| 0 | U7.13, U9.13 | 2 -> U7.1 / U7.2 | 12 -> U9.1 / U9.2 | 0 / 8 |
| 1 | U7.5, U9.5 | 3 -> U7.4 / U7.3 | 13 -> U9.4 / U9.3 | 1 / 9 |
| 2 | U7.6, U9.6 | 4 -> U7.8 / U7.9 | 15 -> U9.8 / U9.9 | 2 / 10 |
| 3 | U7.12, U9.12 | 5 -> U7.11 / U7.10 | 16 -> U9.11 / U9.10 | 3 / 11 |
| 4 | U8.13, U10.13 | 7 -> U8.1 / U8.2 | 17 -> U10.1 / U10.2 | 4 / 12 |
| 5 | U8.5, U10.5 | 8 -> U8.4 / U8.3 | 18 -> U10.4 / U10.3 | 5 / 13 |
| 6 | U8.6, U10.6 | 9 -> U8.8 / U8.9 | 19 -> U10.8 / U10.9 | 6 / 14 |
| 7 | U8.12, U10.12 | 10 -> U8.11 / U8.10 | 20 -> U10.11 / U10.10 | 7 / 15 |

All Z pins of U7/U8 join BUS_A; all Z pins of U9/U10 join BUS_B. Each bus has its own 10 k to GND.

## 6. Logic check (before connecting the insole)

Flash the self-test build (`-DCONFIG_RESTRIDE_MUX_SELFTEST=y`) and watch the serial output. Every 2 s it prints the active `k`; with a meter confirm exactly one SELk is high and it is the printed one.

- [ ] k = 0 .. 7 each verified
- [ ] Unloaded, all 16 channels read near 0 in the normal build
- [ ] Pressing each sensor raises only its own channel (host shows the matching FPC pin)

Deviations from the schematic (as built): ______
