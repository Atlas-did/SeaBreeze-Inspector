# clean_binary_v5_2_adjudicated

This is the runnable v5.2 dataset with human-reviewed label policy and separate ID/OOD roles.

- `images/val` is ID validation and may be used for best-checkpoint selection.
- `images/test` is the frozen OOD test and must not be used for tuning.
- 23 boxes in DJI_0234-0251 were adjudicated: keep 22, remove one 10px clipped fragment.
- The same boundary-fragment rule removed 26 boxes globally across all roles.
- Green markers remain positive because the training set consistently uses that semantic.
- Elongated leading-edge regions remain positive because they are visible and persist across adjacent frames.

## Split summary

| role | folder | images | positives | backgrounds | boxes | scene groups |
|---|---|---:|---:|---:|---:|---:|
| train | train | 1950 | 375 | 1575 | 496 | 4 |
| id_val | val | 380 | 49 | 331 | 58 | 5 |
| ood_test | test | 710 | 138 | 572 | 189 | 4 |

All images are unchanged; only split assignment and documented label-line removals differ from v5.
See `label_changes.csv`, `adjudication_decisions.json`, and `split_manifest.csv`.
