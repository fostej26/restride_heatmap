# ReStride: 16-Sensor Resistive Insole Heatmap on nRF54L15 DK

**Handoff for coding agent** · Rev B · 2026-11-24 · Target: `nrf54l15dk/nrf54l15/cpuapp` (nRF Connect SDK / Zephyr)

**Changes in Rev B:**
- The real insole FPC pinout replaces the placeholder sensor layout.
- The mux is now built on a breadboard: a NAND-gate decoder driving 74HC4066 analog switches, arranged as 2 banks × 8 on AIN4 and AIN5. It replaces the CD74HC4067.
- Mux selection now uses 3 address lines instead of 4.
- Schematic: `insole_mux_schematic.svg` (with a PNG copy), in this same folder.

---

## 1. Goal

Read the 16 resistive pressure sensors in the ReStride insole with the nRF54L15's SAADC, stream the frames to a PC over the DK's USB virtual COM port, and render a **live, interpolated plantar-pressure heatmap** shaped like the insole.

Deliverables:

1. `firmware/`: a Zephyr app that drives the 3-bit mux address, scans all 16 sensors at 50 Hz or faster, and streams frames over UART (VCOM).
2. `host/`: a Python app that draws a live heatmap of the insole, with the sensors at their real positions.
3. `host/simulate.py`: a fake-frame generator, so the host app can be developed without hardware.
4. `docs/wiring.md`: the as-built wiring, kept in step with `insole_mux_schematic.svg`.
5. A root `README.md` with the build, flash, wiring and run steps.

Suggested root: `C:/develop/restride-heatmap/`. Copy this file and the schematic into `docs/`.

---

## 2. Reference documents (read before writing code)

| Doc | Why | Link |
|---|---|---|
| nRF54L15 DK Hardware User Guide | DK pinout, power, which GPIOs are tied to buttons/LEDs/UART | https://docs.nordicsemi.com/bundle/ug_nrf54l15_dk/page/UG/nRF54L15_DK/hw_desription/hw_description.html |
| DK GPIO connector table | Default function of every header pin | https://docs.nordicsemi.com/r/bundle/ug_nrf54l15_dk/page/ug/nrf54l15_dk/hw_desription/connector_if.html |
| DK Hardware files (schematic, layout, PDF guide v1.0.0) | Verify pin conflicts | https://www.nordicsemi.com/Products/Development-hardware/nRF54L15-DK/Hardware-files |
| nRF54L15 Datasheet: SAADC | Gain, reference, acquisition time, oversampling | https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/saadc.html |
| nRF54L15 Datasheet: pin assignments | AIN ↔ GPIO mapping (fixed) | https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/chapters/pin.html-qfn40 |
| nRF54L15 Rev 2 Errata [100] | AIN pins may short during power-on reset | https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev2/page/err/nrf54l15/rev2/latest/anomaly_l15_100.html |
| 74HC00 / 74HC10 / 74HC4066 datasheets | Pinouts, logic levels, switch on-resistance at 3.3 V | Nexperia or TI product pages (use whichever manufacturer's parts are actually on the breadboard) |

---

## 3. The insole (from the annotated photo)

### 3.1 FPC tail pinout, 20 pins

| FPC pin | Function | Connect to |
|---|---|---|
| **1** | **PWR: common electrode for all sensors** | DK VDD (3.3 V) |
| **6** | **GND** | DK GND |
| **14** | **GND** | DK GND |
| **11** | **No connection** (no trace) | leave open |
| 2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 15, 16, 17, 18, 19, 20 | Sensor sense lines (16) | one 74HC4066 switch each (see §4) |

Each sensor is a resistor between FPC pin 1 (common) and its own pin. The sensor's number in the photo **is** its FPC pin number.

> **Bring-up check (do it before wiring the mux):** use a multimeter on resistance range between FPC pin 1 and each sensor pin. Unloaded it should read open or very high, and pressing the pad should drop it sharply. Also confirm that pins 6 and 14 don't read low to pin 1 or to any sensor pin. They're probably a guard/shield trace. Find out which physical end of the tail is pin 1, and record it with a photo in `docs/`.

### 3.2 Sensor positions

The photo appears to show a **right insole viewed from the top**: heel on the left, toes on the right, big-toe (medial) edge at the top. Confirm this against the physical part.

Normalized insole coordinates: `x` runs 0 medial to 1 lateral, `y` runs 0 heel to 1 toe. They were measured from the photo, accurate to about ±0.02.

| Ch | FPC pin | Region | x | y |
|---|---|---|---|---|
| 0 | 2 | Medial midfoot / arch (front) | 0.29 | 0.48 |
| 1 | 3 | Medial heel-midfoot | 0.37 | 0.33 |
| 2 | 4 | Heel lateral | 0.76 | 0.15 |
| 3 | 5 | Heel medial | 0.46 | 0.15 |
| 4 | 7 | MT1 head (medial forefoot) | 0.23 | 0.62 |
| 5 | 8 | Hallux base / medial forefoot (front) | 0.17 | 0.75 |
| 6 | 9 | Hallux (big toe) | 0.17 | 0.88 |
| 7 | 10 | Lesser toes | 0.51 | 0.90 |
| 8 | 12 | MT2–3 heads | 0.44 | 0.76 |
| 9 | 13 | Central heel-midfoot | 0.58 | 0.33 |
| 10 | 15 | Central midfoot | 0.54 | 0.48 |
| 11 | 16 | Central forefoot | 0.52 | 0.62 |
| 12 | 17 | Lateral heel-midfoot | 0.77 | 0.33 |
| 13 | 18 | Lateral midfoot | 0.81 | 0.48 |
| 14 | 19 | Lateral midfoot (front) / MT5 base | 0.82 | 0.63 |
| 15 | 20 | MT4–5 heads | 0.74 | 0.77 |

Approximate insole outline polygon, in the same coordinates (for the heatmap mask). Clockwise from the heel:

```
(0.58,0.00) (0.36,0.03) (0.30,0.08) (0.27,0.25) (0.22,0.39) (0.12,0.57) (0.03,0.76)
(0.01,0.89) (0.08,0.98) (0.28,1.00) (0.50,0.98) (0.67,0.92) (0.84,0.80) (0.98,0.62)
(0.97,0.48) (0.92,0.30) (0.91,0.12) (0.83,0.03) (0.72,0.00)
```

Put both tables in `host/layout.json`, keyed by FPC pin, so they're easy to edit. Add a `--left` flag that mirrors `x → 1 − x`.

---

## 4. Hardware: breadboard mux built from NAND gates + analog switches

### 4.1 Why it isn't NAND gates alone

A NAND gate's output is digital, either 0 V or VDD. It can't pass a sensor's analog voltage through to the ADC. So the NAND gates build the **3-to-8 address decoder**, and **74HC4066 bilateral analog switches** carry the analog signal. Both are standard breadboard DIP-14 parts.

### 4.2 Architecture: 2 banks × 8 (see `insole_mux_schematic.svg`)

- The DK has two free analog inputs, AIN4 (P1.11) and AIN5 (P1.12). They're used as two buses: **BUS_A → AIN4** and **BUS_B → AIN5**.
- A 3-bit address (A2 A1 A0) from 3 GPIOs selects one of 8 rows. Each row's select line, SELk, closes **one switch in each bank**. One address step therefore yields 2 sensors, and 8 steps cover all 16.
- This halves the decoder compared with 4-to-16: 8 three-input NANDs instead of 16 four-input ones.

Signal chain for one sensor:
```
VDD ── FPC pin 1 ── [sensor] ── FPC pin n ── 4066 switch ── BUS_x ──┬── AINx
                                                                   R_ref 10 kΩ
                                                                     GND
V_AIN = VDD × R_ref / (R_ref + R_sensor)     (more pressure → higher voltage)
```

Decoder logic for row k, with address bits b2 b1 b0 = k:
```
NAND3_k inputs: (b2 ? A2 : ~A2), (b1 ? A1 : ~A1), (b0 ? A0 : ~A0)  → output LOW only when address == k
SELk = NOT(NAND3_k)  (2-input NAND with both inputs tied)            → HIGH closes the 4066 switches for row k
~A0, ~A1, ~A2 come from three more 2-input NANDs wired as inverters.
```

### 4.3 Parts list

| Ref | Part | Qty | Use |
|---|---|---|---|
| U1–U3 | 74HC00 (quad 2-input NAND) | 3 | 3 address inverters + 8 SEL output inverters (11 of 12 gates) |
| U4–U6 | 74HC10 (triple 3-input NAND) | 3 | 8 decoder gates (8 of 9) |
| U7–U10 | 74HC4066 (quad analog switch) | 4 | 16 sensor switches. U7/U8 = bank A, U9/U10 = bank B |
| R_refA, R_refB | 10 kΩ 1 % | 2 | BUS_A and BUS_B pull-downs (tune 4.7 k–22 k to match the sensor range) |
| C1–C10 | 100 nF ceramic | 10 | one per IC, from pin 14 to pin 7 |
| J1 | 20-pin FPC → DIP breakout | 1 | measure the FPC pitch first (0.5 mm or 1.0 mm) and check whether the contacts face up or down |

Use **74HC** (or 74HCT for the gates only, though HC is preferred at 3.3 V), **not 74LS**: LS parts need 5 V. CD4011/CD4023/CD4066 will also work at 3.3 V, but CD4066 on-resistance is much higher at that supply, so increase the settle time.

All 14-pin parts: **VCC = pin 14, GND = pin 7**, both to the DK's VDD/GND rails.

### 4.4 Full netlist

**DK connections**

| DK pin | Net | Notes |
|---|---|---|
| P2.06 | A0 | Trace CLK, free when tracing isn't used |
| P2.08 | A1 | Trace[1], free when tracing isn't used |
| P2.10 | A2 | Trace[3], free when tracing isn't used |
| P1.11 | BUS_A (AIN4) | free on the DK |
| P1.12 | BUS_B (AIN5) | free on the DK |
| VDD header | VDD | **set nRF VDD = 3.3 V in Board Configurator** (74HC needs ≥ 2 V, and the default may be 1.8 V) |
| GND header | GND | also FPC pins 6 and 14 |

**Address inverters (74HC00)**

| Gate | Inputs (tied) | Output |
|---|---|---|
| U1A (pins 1,2 → 3) | A0 | ~A0 |
| U1B (pins 4,5 → 6) | A1 | ~A1 |
| U1C (pins 9,10 → 8) | A2 | ~A2 |

**Decoder (74HC10) and SEL inverters (74HC00)**

| k | A2 A1 A0 | NAND3 gate (pins in → out) | NAND3 inputs | SEL inverter (pins in → out) |
|---|---|---|---|---|
| 0 | 000 | U4A (1,2,13 → 12) | ~A2 ~A1 ~A0 | U1D (12,13 → 11) |
| 1 | 001 | U4B (3,4,5 → 6) | ~A2 ~A1 A0 | U2A (1,2 → 3) |
| 2 | 010 | U4C (9,10,11 → 8) | ~A2 A1 ~A0 | U2B (4,5 → 6) |
| 3 | 011 | U5A (1,2,13 → 12) | ~A2 A1 A0 | U2C (9,10 → 8) |
| 4 | 100 | U5B (3,4,5 → 6) | A2 ~A1 ~A0 | U2D (12,13 → 11) |
| 5 | 101 | U5C (9,10,11 → 8) | A2 ~A1 A0 | U3A (1,2 → 3) |
| 6 | 110 | U6A (1,2,13 → 12) | A2 A1 ~A0 | U3B (4,5 → 6) |
| 7 | 111 | U6B (3,4,5 → 6) | A2 A1 A0 | U3C (9,10 → 8) |

Spare gates U3D and U6C: tie all their inputs to GND.

**Analog switches (74HC4066: switch n has I/O pins Y/Z and enable E)**

Switch pin map: SW1 = Y1/Z2/E13 · SW2 = Y4/Z3/E5 · SW3 = Y8/Z9/E6 · SW4 = Y11/Z10/E12

| k | SELk drives | Bank A: FPC pin → switch → BUS_A | Bank B: FPC pin → switch → BUS_B |
|---|---|---|---|
| 0 | U7.13, U9.13 | **2** → U7.1 / U7.2 | **12** → U9.1 / U9.2 |
| 1 | U7.5, U9.5 | **3** → U7.4 / U7.3 | **13** → U9.4 / U9.3 |
| 2 | U7.6, U9.6 | **4** → U7.8 / U7.9 | **15** → U9.8 / U9.9 |
| 3 | U7.12, U9.12 | **5** → U7.11 / U7.10 | **16** → U9.11 / U9.10 |
| 4 | U8.13, U10.13 | **7** → U8.1 / U8.2 | **17** → U10.1 / U10.2 |
| 5 | U8.5, U10.5 | **8** → U8.4 / U8.3 | **18** → U10.4 / U10.3 |
| 6 | U8.6, U10.6 | **9** → U8.8 / U8.9 | **19** → U10.8 / U10.9 |
| 7 | U8.12, U10.12 | **10** → U8.11 / U8.10 | **20** → U10.11 / U10.10 |

All the Z pins of U7/U8 join to **BUS_A**, and all the Z pins of U9/U10 join to **BUS_B**. Each bus has its own 10 kΩ to GND.

**Agent action:** confirm on the DK schematic that P2.06, P2.08 and P2.10 aren't driven by the interface MCU, and make sure tracing is disabled in the build. Avoid these pins: P1.08, P1.09, P1.13 and P0.04 (buttons); P1.10, P1.14, P2.07 and P2.09 (LEDs); P1.04–P1.07 (UART/console); P2.00–P2.05 (external flash).

### 4.5 Breadboard tips

- Lay the decoder out on one half of the board and the switches on the other. Keep the BUS_A/BUS_B wires short and away from the address lines.
- Put a 100 nF capacitor on every chip, right at its pins.
- No floating CMOS inputs, ever. Any unused 74HC input or 4066 E pin goes to GND.
- Make a quick logic check before connecting the insole: step the address 0→7 with a firmware test mode, or with jumper wires to VDD/GND, and use a meter to confirm that exactly one SEL line is high at a time.

---

## 5. Firmware spec (`firmware/`)

### 5.1 Platform

- nRF Connect SDK, the latest stable version installed on this machine (v3.x expected). Board target: `nrf54l15dk/nrf54l15/cpuapp`.
- Use the Zephyr ADC API with a devicetree overlay. Only drop to `nrfx_saadc` if the frame rate can't be met.

### 5.2 Devicetree overlay (`boards/nrf54l15dk_nrf54l15_cpuapp.overlay`)

This is a sketch. Check the macro names in `zephyr/include/zephyr/dt-bindings/adc/nrf-saadc.h` in the installed SDK.

```dts
/ {
    zephyr,user {
        io-channels = <&adc 0>, <&adc 1>, <&adc 2>;
        mux-addr-gpios = <&gpio2 6 GPIO_ACTIVE_HIGH>,    /* A0 */
                         <&gpio2 8 GPIO_ACTIVE_HIGH>,    /* A1 */
                         <&gpio2 10 GPIO_ACTIVE_HIGH>;   /* A2 */
    };
};

&adc {
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    channel@0 {                       /* BUS_A, AIN4 = P1.11 */
        reg = <0>;
        zephyr,gain = "ADC_GAIN_1_4";
        zephyr,reference = "ADC_REF_INTERNAL";
        zephyr,acquisition-time = <ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)>;
        zephyr,input-positive = <NRF_SAADC_AIN4>;
        zephyr,resolution = <12>;
        zephyr,oversampling = <2>;    /* 4x */
    };
    channel@1 {                       /* BUS_B, AIN5 = P1.12 */
        reg = <1>;
        zephyr,gain = "ADC_GAIN_1_4";
        zephyr,reference = "ADC_REF_INTERNAL";
        zephyr,acquisition-time = <ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)>;
        zephyr,input-positive = <NRF_SAADC_AIN5>;
        zephyr,resolution = <12>;
        zephyr,oversampling = <2>;
    };
    channel@2 {                       /* VDD, for ratiometric correction */
        reg = <2>;
        zephyr,gain = "ADC_GAIN_1_4";
        zephyr,reference = "ADC_REF_INTERNAL";
        zephyr,acquisition-time = <ADC_ACQ_TIME_DEFAULT>;
        zephyr,input-positive = <NRF_SAADC_VDD>;   /* check the name for nRF54L */
        zephyr,resolution = <12>;
    };
};
```

- **Check in the SAADC chapter** that the internal reference × (1/gain) is ≥ 3.3 V. If it isn't, adjust the gain.
- Make sure nothing else claims P2.06, P2.08 or P2.10. Trace/ETM must be off.
- Leave the console on `uart20` (P1.04/P1.05 → VCOM).

### 5.3 Scan loop

```
every FRAME_PERIOD (default 20 ms = 50 Hz; configurable up to 100 Hz+):
    vdd = read ch2
    for k in 0..7:
        drive A2 A1 A0 = bits of k
        k_busy_wait(MUX_SETTLE_US)                 # start at 50 µs (covers NAND decoder + 4066 + bus RC), tune down
        rawA, rawB = read ch0 + ch1 in one adc_read sequence
        raw[k]     = rawA                           # bank A
        raw[k + 8] = rawB                           # bank B
    emit frame
```

- Channel index → FPC pin: `CH_TO_FPC = {2,3,4,5,7,8,9,10, 12,13,15,16,17,18,19,20}`. Put this in one header file and reuse it in the host app.
- Address changes can glitch the decoder outputs for a moment, which can briefly close the wrong switch. The settle delay before sampling takes care of this.
- Clamp negative SAADC results to 0.
- Add a **mux self-test mode** (on a Kconfig option or Button 1): hold each address for 2 s and print `k`, so the SEL lines can be checked with a meter.
- Optional: Button 1 (P1.09) → tare.

### 5.4 Frame protocol (ASCII, one line per frame)

```
I,restride-heatmap,<fw_version>,channels=16,rref=10000,map=2-3-4-5-7-8-9-10-12-13-15-16-17-18-19-20\n   (once at boot)
F,<seq>,<t_ms>,<vdd_mv>,<r0>,...,<r15>\n                                                                (every frame)
```
- `rN` is the raw count for channel N; its FPC pin is `CH_TO_FPC[N]`.
- 115200 baud is fine for 50 Hz. Use 1 Mbaud for 100 Hz or more.

### 5.5 prj.conf (starting point)

```
CONFIG_ADC=y
CONFIG_GPIO=y
CONFIG_SERIAL=y
CONFIG_CONSOLE=y
CONFIG_UART_CONSOLE=y
CONFIG_LOG=n
```

---

## 6. Host heatmap spec (`host/`)

- Python 3.11+. Dependencies: `pyserial`, `numpy`, `scipy`, `matplotlib` (switch to `pyqtgraph` if matplotlib can't keep 30 fps).
- CLI: `python heatmap.py [--port COMx] [--baud 115200] [--left] [--layout layout.json] [--log out.csv]`
  - If no port is given, auto-detect it: try both J-Link VCOM ports and look for the `I,restride-heatmap` line.
- For each frame:
  1. Parse the line, drop malformed lines and track gaps in `seq`.
  2. Compute the ratio `v/VDD` from the raw count and `vdd_mv`.
  3. `R_sensor = R_ref × (1 − ratio) / ratio`. Treat ratio ≈ 0 as "no load".
  4. Pressure index = conductance `1/R_sensor` (roughly linear in force for FSR-type sensors), minus the tare value.
  5. Interpolate the 16 points onto a ~100×250 grid (thin-plate RBF), then mask outside the outline polygon from §3.2.
- Display:
  - Insole-shaped heatmap with a fixed colour scale and key, using a perceptually uniform colormap such as `inferno`.
  - Sensor dots labelled with their **FPC pin number**; live values can show on toggle.
  - Centre-of-pressure dot with a trail, total load, frame rate and dropped-frame count.
  - Keys: `t` tare, `s` PNG snapshot, `r` start/stop CSV recording, `q` quit.
- `simulate.py`: emit fake frames that follow a walking gait (heel strike on pins 4/5 → midfoot 13/15/17/18 → forefoot 7/12/16/20 → toe-off 8/9/10).

---

## 7. Acceptance criteria

- [ ] Multimeter check of the insole (§3.1) is done, and the pin-1 orientation is documented.
- [ ] Mux self-test: for k = 0…7 exactly one SEL line is high, and it's the right one.
- [ ] `west build -b nrf54l15dk/nrf54l15/cpuapp firmware` builds cleanly and `west flash` works.
- [ ] The serial stream shows the `I,` line, then `F,` frames at the set rate with no `seq` gaps over 60 s.
- [ ] Unloaded, every channel reads near 0. Pressing each sensor raises only its own channel, and the host app shows the matching FPC pin number. This proves the decoder, the switch wiring and the channel map.
- [ ] Shifting weight from heel to toe moves the centre-of-pressure trail from pins 4/5 toward 8/9/10.
- [ ] The host app runs at 20 fps or more with the insole-shaped mask. `simulate.py` works with no hardware attached.
- [ ] `docs/wiring.md` matches the breadboard, and the README covers setting VDD to 3.3 V in Board Configurator.

---

## 8. Open questions for the human (flag them, don't block on them)

1. **FPC pitch and pin-1 end** of the tail, which decide the breakout board.
2. **What pins 6/14 (GND) connect to** inside the insole: a shield trace, or the gold pad?
3. **Sensor resistance range** loaded and unloaded, which sets `R_ref`. Start at 10 kΩ.
4. **Left or right foot**, and confirmation of the photo orientation (§3.2).
5. **Later:** move from UART to BLE (NUS). Keep the frame formatter separate from the transport.

---

## 9. Pitfalls

- NAND outputs can't carry the analog signal; only the 4066 switches can. Don't try to read a sensor through a logic gate.
- Use 74HC parts at 3.3 V, never 74LS. Set the DK's VDD to 3.3 V before powering the breadboard, and never put 5 V (P30–P32) into the circuit.
- Don't use AIN6 (P1.13, Button 0), AIN7 (P1.14, LED 3) or AIN0–3 (P1.04–P1.07, UART).
- **Bleed between channels**: increase `MUX_SETTLE_US` or the SAADC acquisition time, shorten the bus wires, or lower `R_ref`.
- **All channels moving together**: check the decoder. Probably more than one SEL line is high, or an input is floating.
- Errata [100]: AIN pins may short for about 10 µs at power-on reset. That's harmless here, because the sources are resistive.
