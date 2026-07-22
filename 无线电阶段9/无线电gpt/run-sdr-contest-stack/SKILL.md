---
name: run-sdr-contest-stack
description: Design, inspect, build, run, and diagnose software-defined-radio competition links, especially offline NanoSDR/PlutoSDR file-transfer contests with co-channel interference. Use for RadioConda or GNU Radio setup, local SDR/API inventory, Pluto access through pyadi-iio/libiio/gr-iio/SoapySDR, modem and FEC selection, IQ capture and analysis, interference-resilient link testing, authorized TX/RX automation, decoded-payload scoring, or preparation of two-computer contest systems.
---

# Run SDR Contest Stack

Treat RadioConda as an environment, not as the radio API. Select a callable API beneath it, build a reproducible offline chain, and optimize correct delivered payload bytes rather than a single clean-channel BER number.

## Start with the contest contract

1. Extract exact authorized frequency ranges, bandwidth, power/gain limits, round duration, payload format, scoring rule, permitted feedback, permitted frequency changes, and whether deliberate waveforms are allowed.
2. Record the physical topology: SDR model/revision, TX/RX assignment, antenna/filter for each band, cable or over-the-air path, and which non-SDR interfaces must remain disabled.
3. Mark unknown limits as unknown. Never infer an authorized band from “433 MHz” or “2.4 GHz” filter labels.
4. Keep receive-only inspection available even when transmit authorization is incomplete.

For the pictured competition, use the assumptions in [references/competition-workflow.md](references/competition-workflow.md), but replace them with the full rulebook when supplied.

## Inventory before choosing tools

Run the bundled probe with the current RadioConda/Python interpreter:

```bash
python scripts/probe_sdr_stack.py --versions --json -
```

Add `--hardware` only when attached SDR discovery is in scope. The hardware probes are read-only; they do not transmit.

Interpret the result in this order:

1. Prefer `pyadi-iio` for short scripted Pluto/NanoSDR capture and controlled finite-buffer transmission.
2. Prefer GNU Radio with `gr-iio` for complete streaming modem, synchronization, FEC, visualization, and custom blocks.
3. Prefer `libiio` for device discovery, low-level attributes, buffers, and driver diagnosis.
4. Prefer SoapySDR only when cross-vendor portability materially helps; avoid adding an abstraction layer to a Pluto-only baseline without a reason.
5. Use SDRangel REST only when its ready-made server/plugins fit better than a custom GNU Radio flowgraph.
6. Use GUI-only tools for human diagnosis, not as the Agent’s primary control path.

Read [references/software-api-catalog.md](references/software-api-catalog.md) when selecting or installing packages. Read [references/pluto-api-patterns.md](references/pluto-api-patterns.md) before generating device code.

## Build in increasing-risk stages

1. Implement framing and decoding against generated arrays or files.
2. Add channel models for AWGN, carrier-frequency offset, sample-rate offset, clipping, multipath, burst interference, narrowband interference, and co-channel signals.
3. Replay captured IQ and require deterministic decode results.
4. Test through a properly attenuated cabled RF path or approved shielded setup. Never directly cable a transmitter output into a receiver input without a verified attenuation/power budget.
5. Run authorized over-the-air tests only after validating the plan and checking antennas/filters.
6. Test from a cold offline boot with all forbidden interfaces disabled.

Do not begin with machine learning. Establish a deterministic synchronization, filtering, soft-demodulation, FEC, interleaving, CRC, deduplication, and reassembly baseline first. Add learned interference classification or parameter selection only when it beats that baseline on held-out captures and can run fully offline.

## Gate every RF transmission

Copy the example plan and constraint files, replace placeholders with rulebook and hardware values, and validate before starting a sink or calling `tx()`:

```bash
python scripts/validate_radio_plan.py \
  --plan assets/radio-plan.example.json \
  --constraints assets/contest-constraints.example.json
```

Require the validator to pass for `cable` and `ota` modes. Treat validation as necessary but not sufficient: confirm the correct physical output, band-pass filter, antenna/dummy load, attenuation, and emergency stop mechanism.

For cyclic buffers, always define a finite test duration and execute the stop/cleanup path in `finally`. Do not widen Pluto firmware tuning limits for 433 MHz or 2.4 GHz; both are inside the official factory-qualified Pluto range. Change firmware configuration only when the actual board, rules, and user request require it.

## Optimize the link as a system

Use this default processing order, changing it only with measured evidence:

```text
bytes -> segmentation/sequence -> CRC -> FEC -> interleave -> whitening
      -> framing/preamble -> modulation/pulse shaping -> SDR TX

SDR RX -> channel selection/DC-IQ handling -> detection/synchronization
       -> CFO/SRO/equalization -> soft demodulation -> deinterleave/FEC
       -> CRC -> deduplicate/reorder -> decoded bytes
```

Keep these invariants:

- Include payload length, sequence number, coding/modulation identifier, and header protection.
- Keep preamble/header more robust than payload.
- Prefer soft information into the FEC decoder.
- Separate acquisition failures, header failures, FEC failures, CRC failures, duplicates, and missing frames in metrics.
- Preserve the raw random input and received output exactly; never “repair” scoring files with assumptions not present on air.
- Tune for correct bytes per unit contest time, including overhead, reacquisition, repeats, and dropped buffers.

## Record and score every run

For each run, save:

- immutable plan and constraint JSON;
- software versions and detected device URI/serial;
- transmitted payload hash and frame manifest;
- optional IQ capture with SigMF or Digital RF metadata;
- decoded bytes, packet log, underrun/overflow counters, and timing;
- exact configuration and aggregate score.

Compare a reference random file with a decoded file:

```bash
python scripts/compare_payloads.py reference.bin decoded.bin --search-window 0 --json -
```

Use `--search-window` only when the scoring contract permits an unknown leading byte offset. Do not use offset search to hide a framing or reassembly defect.

## Agent execution rules

- Prefer Python APIs, generated source, JSON/YAML configuration, and CLI calls over GUI automation.
- Use explicit device URI or serial when two SDRs may be visible.
- Keep TX and RX programs independently restartable because the two contest laptops cannot rely on a side channel.
- Start subprocesses with bounded timeouts, capture logs, and expose a deterministic stop action.
- Inspect current API signatures locally before emitting code; package versions in RadioConda may lag upstream documentation.
- Do not install, update, or solve packages during a contest run. Freeze and test the environment beforehand.
- Do not activate Wi-Fi, Bluetooth, Ethernet, serial, cloud APIs, or another feedback channel when the rules allow only SDR communication.
- Never silently change firmware, calibration data, USB drivers, OS network state, or FPGA images.

## Deliver a useful result

Return, as applicable:

1. the detected software/hardware inventory and gaps;
2. the selected API with a short rationale;
3. reproducible TX, RX, simulation, and scoring commands;
4. explicit assumptions and unresolved rule constraints;
5. measured results, failure categories, and the next highest-value experiment.
