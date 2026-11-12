## Door (IN / OUT)

| Clip | direction | hand count | system | matched (+-2 s) | missed | extra |
|---|---|---|---|---|---|---|
| shop1 | IN | 5 | 4 | 4 | 1 | 0 |
| shop1 | OUT | 2 | 2 | 2 | 0 | 0 |

- shop1 IN missed near [20.0] s

## Queue count

| Clip | labelled points | span | MAE (people) | exact (inside range) | worst |
|---|---|---|---|---|---|
| shop1 | 19 | 5-95 s | 0.26 | 14/19 | -1 at 15 s |
| market | 30 | 0-290 s | 0.30 | 23/30 | -3 at 0 s |
| cafe | 12 | 10-285 s | 0.75 | 4/12 | -2 at 60 s |

## Alerts

| Clip | type | expected | system | found | missed | wrong |
|---|---|---|---|---|---|---|
| shop1 | queue | 1 | 1 | 1 | 0 | 0 |
| shop1 | empty_counter | 0 | 0 | 0 | 0 | 0 |
| market | queue | 2 | 2 | 2 | 0 | 0 |
| market | empty_counter | 0 | 0 | 0 | 0 | 0 |

- market queue: expected 108-165 s
- market queue: expected 82-95 s
- market queue: system 107-162 s, peak 4
- market queue: system 79-96 s, peak 4
- shop1 queue: expected 0-82 s
- shop1 queue: system 1-85 s, peak 7
