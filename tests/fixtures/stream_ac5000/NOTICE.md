# Third-party test fixtures

The `*_masked.json` files in this directory are copied unchanged from
[shuette42/ecoflow-energy-ha](https://github.com/shuette42/ecoflow-energy-ha),
`tests/fixtures/stream_ac5000/` (commit `6830cd3649c1a4f3603d9379157fba5ee88e1f63`).
They are real MQTT frames from STREAM 5000 (ES21) and STREAM AC 5000 (ES22)
units, contributed by users of that project, with serials and other
identifiers masked by its author. Each file's `note` field describes where its
frames come from.

| File | Content |
| --- | --- |
| `es21_pv_masked.json` | Single ES21 with PV, day and night frames; serial masked to `XXXXXXXXXXXXXXXX` |
| `es21_frames_masked.json` | Single ES21, evening frames without PV; serial masked to `XXXXXXXXXXXXXXXX` |
| `es21_pair_pv_masked.json` | Linked ES21 pair with PV, both units' entries in the master's frames |
| `es21_pair_pv_both_connections_masked.json` | Same pair, frames from both units' connections, night and day |
| `es22_push_capture_masked.json` | Single ES22 without PV, pushes; serial masked to `XXXXXXXXXXXXXXXX` |
| `es22_get_reply_masked.json` | Single ES22 without PV, full-state reply; serial masked to `XXXXXXXXXXXXXXXX` |
| `es22_ultra_pv_pair_masked.json` | ES22 without PV linked to a Stream Ultra (BK11) that carries the PV |

They are used under the MIT licence of that project:

```
MIT License

Copyright (c) 2026 shuette42

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
