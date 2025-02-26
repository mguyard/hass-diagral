# [1.1.0-beta.4](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.3...v1.1.0-beta.4) (2025-02-26)


### Bug Fixes

* **webhook:** 🔗 Fix issue with webhook registration and HA Cloud ([cb87f68](https://github.com/mguyard/hass-diagral/commit/cb87f6856e49ceddc6888887c732c8d0ef52e0c0))

# [1.1.0-beta.3](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.2...v1.1.0-beta.3) (2025-02-26)


### Bug Fixes

* **webhook:** 🔧 Fix webhook issue for Home Assistant Cloud ([bcaa5e5](https://github.com/mguyard/hass-diagral/commit/bcaa5e5ce744090d1f922dc652abb99e6ee29527))


### Features

* **docs:** 📚 Add webhook documentation and related content ([74c6384](https://github.com/mguyard/hass-diagral/commit/74c63840474efe81e58d1a895fc4b515a11c71fc))
* **webhook:** 🔗 Add webhook registration and unregistration action ([94bab40](https://github.com/mguyard/hass-diagral/commit/94bab40f14b894a8302ee32f6ac3606b5aabcb1c))

# [1.1.0-beta.2](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.1...v1.1.0-beta.2) (2025-02-26)


### Bug Fixes

* **webhook:** 🔧 Use `async_create_cloudhook` for webhook registration ([48356cd](https://github.com/mguyard/hass-diagral/commit/48356cd0494d997e3d6f4d0eb844d5c8b19b8ef0))

# [1.1.0-beta.1](https://github.com/mguyard/hass-diagral/compare/v1.0.1-beta.2...v1.1.0-beta.1) (2025-02-26)


### Bug Fixes

* **diagral:** 🐛 Flatten anomaly names into details for better clarity ([a51db28](https://github.com/mguyard/hass-diagral/commit/a51db2854ae579d8b37258b5a3515ef8970d71a4))
* **diagral:** 🐛 Remove unnecessary call to `async_update_listeners` ([568c5f4](https://github.com/mguyard/hass-diagral/commit/568c5f4ca7f80f15fff11b13885ad595cb437e1d))
* **diagral:** 🐛 Revolve anomaly details following previous commit ([6116f88](https://github.com/mguyard/hass-diagral/commit/6116f88d917d29c7c5c0d84b3350dcce5fcd980d))


### Features

* **diagral:** ✨ Add active groups sensor and enhance logging ([4c27dda](https://github.com/mguyard/hass-diagral/commit/4c27ddabe342c505d127a9ceeb56f5aa4000ec39))
* **diagral:** ✨ Add catching of username in STATUS events ([76274a8](https://github.com/mguyard/hass-diagral/commit/76274a8e45c82986e144f2b9dca2ab95f2c8c73a))
* **diagral:** ✨ Update service names and descriptions for clarity ([51389e2](https://github.com/mguyard/hass-diagral/commit/51389e2216a0e2336dfa78fac3b0e198259c84dc))

## [1.0.1-beta.2](https://github.com/mguyard/hass-diagral/compare/v1.0.1-beta.1...v1.0.1-beta.2) (2025-02-25)


### Bug Fixes

* **diagral:** 🐛 Update callback type for `async_add_entities` ([66763e2](https://github.com/mguyard/hass-diagral/commit/66763e29cd03b959a132f52ea881175453bb4f37)), closes [home-assistant/core#138201](https://github.com/home-assistant/core/issues/138201)

## [1.0.1-beta.1](https://github.com/mguyard/hass-diagral/compare/v1.0.0...v1.0.1-beta.1) (2025-02-24)


### Bug Fixes

* **diagral:** 🐛 Update callback type for `async_add_entities` ([85e393d](https://github.com/mguyard/hass-diagral/commit/85e393df3ac05208bface8401dba63258edf1d82))

# 1.0.0 (2025-02-24)


### Features

* ✨ Add initial integration files and configuration ([8a284db](https://github.com/mguyard/hass-diagral/commit/8a284dbcb2baf8f1de2e4278111fb36bcd30df4b))
