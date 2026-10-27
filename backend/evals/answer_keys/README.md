# Answer keys (DO NOT feed to the app)

Organizer-provided ground truth for the synthetic datasets. Moved out of `docs/`
so the app's file discovery can never read them and leak answers.

| File | Dataset |
|---|---|
| `ground_truth.json` | `docs/spec26_synthetic_data/` (parts 2280-2284) |
| `ground_truth_batch2.json` | `docs/spec26_batch2_hard/` (parts 3001-3004) |

Use only for building the golden set / scoring. The IGES models under
`docs/**/iges/` are generated from these by `tools/generate_iges.py`.
