# restride-heatmap

Live plantar-pressure heatmap for the ReStride 16-sensor resistive insole, read by an nRF54L15 DK.

```
insole (16 sensors) -> 3-bit NAND decoder + 4x 74HC4066 (2 banks x 8) -> AIN4 / AIN5
  -> nRF54L15 SAADC -> UART (DK VCOM) -> host/heatmap.py
```

- `firmware/`: Zephyr (nRF Connect SDK) app. Scans all 16 sensors at 50 Hz, prints ASCII frames.
- `host/`: Python viewer (`heatmap.py`), fake data (`simulate.py`), sensor map (`layout.json`).
- `docs/`: as-built wiring (`wiring.md`), schematic, the original handoff.

## Try it with no hardware

```
cd host
pip install -r requirements.txt
python heatmap.py --sim
```

Keys: `t` tare, `s` PNG snapshot, `r` start/stop CSV recording, `v` show live values, `q` quit.
`--left` mirrors the insole for a left foot; `--vmax` sets the colour-scale maximum (mS, default 0.1).

## Hardware

1. Build the breadboard from `docs/wiring.md` and `docs/insole_mux_schematic.svg`.
2. **Set the DK's nRF VDD to 3.3 V in Board Configurator** (nRF Connect for Desktop). The 74HC parts need >= 2 V and the default may be 1.8 V.
3. Do the multimeter check of the insole and the mux logic check (wiring.md sections 1 and 6) before connecting the two.

## Firmware

```
cd firmware
west build -b nrf54l15dk/nrf54l15/cpuapp --pristine
west flash
# mux logic check instead of the scan:
west build -b nrf54l15dk/nrf54l15/cpuapp --pristine -- -DCONFIG_RESTRIDE_MUX_SELFTEST=y
```

Tunables (Kconfig, `-DCONFIG_...=`): `RESTRIDE_FRAME_PERIOD_MS` (20), `RESTRIDE_MUX_SETTLE_US` (50), `RESTRIDE_OVERSAMPLING` (2 = 4x), `RESTRIDE_RREF_OHMS` (10000, only reported to the host).

**Not yet built or run.** No nRF Connect SDK was installed when this was written. Check first:
- the overlay macros `NRF_SAADC_AIN4`, `NRF_SAADC_AIN5`, `NRF_SAADC_VDD` against `zephyr/include/zephyr/dt-bindings/adc/` in your SDK, and that `ADC_GAIN_1_4` with the internal 0.9 V reference gives 3.6 V full scale (>= 3.3 V). The host and firmware both assume 3.6 V / 4096 counts (`ADC_FULL_MV`, `ADC_COUNTS`).
- that oversampling works with two channels in one sequence; if `adc_read` fails, set `RESTRIDE_OVERSAMPLING=0`.
- that nothing else claims P2.06 / P2.08 / P2.10 and tracing is off.

## Serial protocol

```
I,restride-heatmap,<fw>,channels=16,rref=10000,map=2-3-4-5-7-8-9-10-12-13-15-16-17-18-19-20   (boot, repeated every 5 s)
F,<seq>,<t_ms>,<vdd_mv>,<r0>,...,<r15>                                                       (every frame)
```

`rN` is the raw count of channel N (FPC pin `map[N]`). 115200 baud is enough for 50 Hz; use 1 Mbaud above ~100 Hz.
The I line is repeated (the handoff said once) so the host can auto-detect the port after boot.

## Run the viewer on hardware

```
python heatmap.py                  # auto-detects the DK VCOM (tries both J-Link ports)
python heatmap.py --port COM7 --log out.csv
```

Pressure index = sensor conductance: `ratio = raw / vdd_count`, `R = Rref (1 - ratio) / ratio`, `G = 1/R`, minus the tare. Ratiometric, so VDD and ADC-scale errors cancel. The 16 points are interpolated with a thin-plate RBF onto a 100 x 250 grid and masked to the insole outline.

## Open questions (see handoff section 8)

FPC pitch and pin-1 end; what pins 6/14 connect to inside the insole; sensor resistance range (tune `R_ref`, 4.7 k-22 k); left or right foot and photo orientation (check `layout.json` against the real part); BLE (NUS) later, so keep frame formatting separate from the transport.
"# restride_heatmap" 
