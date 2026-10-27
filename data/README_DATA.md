# Data — read this first

The raw OULAD CSVs are **not committed to this repository**.

- **Licence:** OULAD is released by The Open University under
  **CC BY 4.0**, which permits redistribution with attribution. Redistribution
  is not the problem — size is: the files total ~464 MB uncompressed and
  `studentVle.csv` alone is ~433 MB, far beyond sensible git hosting.
- **Get the data:** run `python src/01_download_data.py`. It downloads the
  December-2015 release from the UCI Machine Learning Repository mirror
  (dataset 349, DOI https://doi.org/10.24432/C5KK69), verifies the zip's
  SHA-256 against the pinned value in the script, and extracts the seven
  CSVs plus `OULAD.names` into this folder.
- **Canonical source:** The Open University's own page,
  https://analyse.kmi.open.ac.uk/open_dataset (now redirecting to
  https://research.stem.open.ac.uk/ouanalyse/), offers the same dataset
  behind a request form. The UCI zip used here is byte-identical in
  structure to that release — its file timestamps are the original
  September/December 2015 ones, and every row count matches the
  documentation bundled inside it (see `src/00_verify_data.py` and
  `outputs/data_verification.json`).
- **One quirk of this release:** missing values are coded as `?`
  (an empty `date_unregistration`, some assessment scores, some
  `imd_band` values). The analysis scripts read with `na_values="?"`;
  if you load the CSVs yourself and forget this, the date and score
  columns will silently load as strings.
- **Citation:** Kuzilek, J., Hlosta, M., & Zdrahal, Z. (2017).
  *Open University Learning Analytics dataset.* Scientific Data, 4, 170171.
