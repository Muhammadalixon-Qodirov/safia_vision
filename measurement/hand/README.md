# Hand labels (you fill these)

Honest measurement is graded, so these labels must be your own, made by watching
the clips. After filling them and running the system, run
`python measurement/compare.py` to produce the tables for the main README.

- **door_counts.csv** — watch each clip once and count people IN and OUT at the
  door by hand. One row per source.
- **queue_labels.csv** — every 10 seconds, pause and count how many people are in
  the queue zone; write it in `hand_queue`. Do at least 2 minutes (13 rows here).
- **expected_alerts.csv** — from watching, write when you think each alert should
  fire (start/end seconds). Leave a row out if you expect none; add rows for
  extra episodes.

Speed numbers (FPS, GPU, VRAM, resolution, model, precision) and the known
failure cases come from the run itself — note them straight into the main README.
