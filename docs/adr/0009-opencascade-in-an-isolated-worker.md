---
status: accepted
date: 2026-10-27
---

# 0009 OpenCascade for IGES geometry, run in an isolated worker process

## Context

Level 3 reads IGES models and uses "geometry facts you can extract reliably". IGES files from
real CAD tools carry trimmed surfaces, NURBS, exact solids, inches or millimetres, and arbitrary
orientation. Measuring them well needs a geometry kernel: sewing, solid validation, point-in-solid
tests, mass properties, tessellation and hidden-line removal. A kernel is C++ code that a hostile
or broken file can crash, hang or drive out of memory.

Options considered: a pure-Python reader of the IGES entities (light, but it re-implements a
kernel badly as soon as files carry NURBS or solids); `cadquery-ocp` with VTK (570 MB installed,
mostly visualisation the server never uses); `cadquery-ocp-novtk` (the same OpenCascade 8 kernel,
166 MB, no other dependencies). The user chose "OpenCascade required".

## Decision

- Pin `cadquery-ocp-novtk==8.0.1.1.0`. OpenCascade is LGPL-2.1 with the OCCT exception and is
  linked dynamically through the wheel.
- Only `app/geometry/` imports the kernel, and the API process never does. Every job runs in a
  `spawn`-ed `ProcessPoolExecutor` worker with a 30 s timeout and a memory cap (a Job Object on
  Windows, `RLIMIT_AS` on Linux). A timeout or crash kills the pool and a new one replaces it;
  the caller gets `ModelLimitError` or `UnreadableModelError` with a plain reason.
- The header is parsed as text before the kernel sees the file, so size, entity count and units
  are checked first, and header facts are `exact`.
- The kernel's progress output is redirected away from the log stream.
- Viewer artifacts (glTF meshes, SVG projections) are built in the same job and stored by content
  hash; the extractor version is part of their URLs so a rebuild is never hidden by a cache.

## Consequences

A bad file costs one worker, never the API. The first IGES job pays about 0.6 s to start the
worker. Linux images need the GL runtime libraries the wheel links against. Tests run the kernel
in-process for speed, and a dedicated test exercises the real pool, a crash, a timeout and the
memory cap.
