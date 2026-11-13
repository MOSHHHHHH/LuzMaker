# Self-hosted PDF assets

- `jspdf.umd.min.js`: jsPDF 4.2.1, from the npm `jspdf@4.2.1` distribution.
  Upstream: https://github.com/parallax/jsPDF — MIT license included.
- `bidi.min.js`: bidi-js 1.0.3, from npm `bidi-js@1.0.3`.
  Upstream: https://github.com/lojjic/bidi-js — MIT license included.
- `LuzSans-Regular.ttf`, `LuzSans-Bold.ttf`: subsets of DejaVu Sans 2.37,
  from the distribution's `fonts-dejavu-core` package. The original font license
  and copyright notices are in `FONT-LICENSE.txt`. Subsets retain Latin, Greek,
  Cyrillic, Hebrew, Arabic, punctuation, arrows and a visible missing-symbol box.

These are loaded only when PDF export is requested. No CDN is required.
