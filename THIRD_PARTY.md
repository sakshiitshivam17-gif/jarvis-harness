# Third-party components

JARVIS is MIT licensed (see `LICENSE`). It bundles or downloads third-party
work at setup time; that work keeps its own license.

| Component | Where | License | Notes |
| --- | --- | --- | --- |
| [trycua/cua](https://github.com/trycua/cua) — CUA driver | `tools/cua-driver/` (downloaded) | MIT | Computer-use driver: window enumeration, accessibility trees, input delivery. |
| [rhasspy/piper](https://github.com/rhasspy/piper) | `tools/piper/` (downloaded) | MIT | Local neural speech synthesis. |
| [piper-voices](https://huggingface.co/rhasspy/piper-voices) | `tools/piper/voices/` (downloaded) | per voice card | `en_GB-alan-medium`, `hi_IN-pratham-medium`. Check each voice card before redistribution. |
| [RapidOCR / onnxruntime](https://github.com/RapidAI/RapidOCR) | pip | Apache-2.0 / MIT | On-device OCR for screen reading. |
| [edge-tts](https://github.com/rany2/edge-tts) | pip (optional) | GPL-3.0 | Cloud voice fallback. |
| Orbitron, Rajdhani | `web/fonts/` | SIL OFL 1.1 | Bundled webfonts, latin subset. |

The CUA driver can optionally load an AGPL-licensed perception extension
(`cua-perception`, based on OmniParser). It is not installed by default; if you
add it, review its notices before redistributing or hosting JARVIS publicly.

JARVIS talks to the DeepSeek API for its neural core. That is a service, not a
bundled component, and is optional.
