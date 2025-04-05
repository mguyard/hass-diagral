# [1.2.0-beta.3](https://github.com/mguyard/hass-diagral/compare/v1.2.0-beta.2...v1.2.0-beta.3) (2025-04-05)


### Bug Fixes

* **webhook:** 🐛 Avoid error with inactive cloud subscription for webhook creation ([8b06aa3](https://github.com/mguyard/hass-diagral/commit/8b06aa33eb4c0fef14f6d4424185fd6d22420d80)), closes [#42](https://github.com/mguyard/hass-diagral/issues/42)

# [1.2.0-beta.2](https://github.com/mguyard/hass-diagral/compare/v1.2.0-beta.1...v1.2.0-beta.2) (2025-04-01)


### Bug Fixes

* **alarm_control_panel:** 🐛 Fix code support for `TRIGGERED` state ([eb2f30a](https://github.com/mguyard/hass-diagral/commit/eb2f30a6d848383098e5a938fca218d7cd9f662d))

# [1.2.0-beta.1](https://github.com/mguyard/hass-diagral/compare/v1.1.0...v1.2.0-beta.1) (2025-04-01)


### Features

* **config:** ✨ Allow support of pincode starting with one or more 0 ([1b6777f](https://github.com/mguyard/hass-diagral/commit/1b6777fe0447876a7290bc40395f7cc8451df7c3)), closes [#38](https://github.com/mguyard/hass-diagral/issues/38)

# [1.1.0](https://github.com/mguyard/hass-diagral/compare/v1.0.0...v1.1.0) (2025-03-27)


### Bug Fixes

* **alarm_control_panel:** 🐛 improve alarm state handling ([3b9e3f5](https://github.com/mguyard/hass-diagral/commit/3b9e3f5bfe448a8d93d12c290127587f4fa53f23))
* **diagral:** ✨ Fix forgotten condition for property `code_arm_required` ([d2eed6a](https://github.com/mguyard/hass-diagral/commit/d2eed6a29ab398bdd4da58b7d702380ea010adda))
* **diagral:** 🐛 Flatten anomaly names into details for better clarity ([a51db28](https://github.com/mguyard/hass-diagral/commit/a51db2854ae579d8b37258b5a3515ef8970d71a4))
* **diagral:** 🐛 Handle missing user information in event processing ([3861c16](https://github.com/mguyard/hass-diagral/commit/3861c16bb0acd692a6e3db24b4847fc749f760a8))
* **diagral:** 🐛 Handle optional user information in event processing ([1abc896](https://github.com/mguyard/hass-diagral/commit/1abc8964eedd48a1af27752457938c24c6bacaa7))
* **diagral:** 🐛 Remove unnecessary call to `async_update_listeners` ([568c5f4](https://github.com/mguyard/hass-diagral/commit/568c5f4ca7f80f15fff11b13885ad595cb437e1d))
* **diagral:** 🐛 Revolve anomaly details following previous commit ([6116f88](https://github.com/mguyard/hass-diagral/commit/6116f88d917d29c7c5c0d84b3350dcce5fcd980d))
* **diagral:** 🐛 update `pydiagral` requirement to version 1.5.2 ([e4b3614](https://github.com/mguyard/hass-diagral/commit/e4b3614a159e06d58bbd784ba4b72ffec42ac5d5))
* **diagral:** 🐛 Update callback type for `async_add_entities` ([66763e2](https://github.com/mguyard/hass-diagral/commit/66763e29cd03b959a132f52ea881175453bb4f37)), closes [home-assistant/core#138201](https://github.com/home-assistant/core/issues/138201)
* **diagral:** 🐛 Update callback type for `async_add_entities` ([85e393d](https://github.com/mguyard/hass-diagral/commit/85e393df3ac05208bface8401dba63258edf1d82))
* **webhook:** 🐛 fix webhook registration logic ([73ba0d7](https://github.com/mguyard/hass-diagral/commit/73ba0d784aeb62313e1c366695abeb73d50d2099))
* **webhook:** 🐛 improve logging for webhook data handling ([8a47783](https://github.com/mguyard/hass-diagral/commit/8a477838669054124d26c35a33e6c905c3f9ed12))
* **webhook:** 🐛 Improve webhook registration logic ([05257c7](https://github.com/mguyard/hass-diagral/commit/05257c7fea690a0feff92963b9c02b357497e175))
* **webhook:** 🐛 Resolve webhook registration/deletion with NabuCasa ([569733d](https://github.com/mguyard/hass-diagral/commit/569733dcec4fde0c1ee4fb6acb3e19bc466b1613))
* **webhook:** 🔗 Fix issue with webhook registration and HA Cloud ([cb87f68](https://github.com/mguyard/hass-diagral/commit/cb87f6856e49ceddc6888887c732c8d0ef52e0c0))
* **webhook:** 🔗 Handle existing webhook subscriptions gracefully ([b180994](https://github.com/mguyard/hass-diagral/commit/b180994854669a199b1f085261b045e5a28d554f))
* **webhook:** 🔗 Improve webhook registration handling ([0687699](https://github.com/mguyard/hass-diagral/commit/0687699678b86ddd00276ffd1d85dbf166434148))
* **webhook:** 🔧 Fix webhook issue for Home Assistant Cloud ([bcaa5e5](https://github.com/mguyard/hass-diagral/commit/bcaa5e5ce744090d1f922dc652abb99e6ee29527))
* **webhook:** 🔧 Use `async_create_cloudhook` for webhook registration ([48356cd](https://github.com/mguyard/hass-diagral/commit/48356cd0494d997e3d6f4d0eb844d5c8b19b8ef0))


### Features

* **alarm_control_panel:** ✨ enhance code requirement logic for arming ([cf6d49c](https://github.com/mguyard/hass-diagral/commit/cf6d49ce53bb31d9521801cc20ccd554b6e5bc36))
* **diagral:** ✨ Add active groups sensor and enhance logging ([4c27dda](https://github.com/mguyard/hass-diagral/commit/4c27ddabe342c505d127a9ceeb56f5aa4000ec39))
* **diagral:** ✨ Add alarmpanel_code configuration option and refactor config_flow ([55fa23e](https://github.com/mguyard/hass-diagral/commit/55fa23e0bd8bc420b721908f808a69c64d0e8461))
* **diagral:** ✨ Add catching of username in STATUS events ([76274a8](https://github.com/mguyard/hass-diagral/commit/76274a8e45c82986e144f2b9dca2ab95f2c8c73a))
* **diagral:** ✨ Add group information to binary sensor state attributes ([e9776dc](https://github.com/mguyard/hass-diagral/commit/e9776dc27c48c2093d04e327ac3f06b7c7730884))
* **diagral:** ✨ Refactor `validate_input` to use `TryConnectResult` ([d449f35](https://github.com/mguyard/hass-diagral/commit/d449f35b53fdb364813b75328ab3b57fbbab0749))
* **diagral:** ✨ replace `triggered binary_sensor` by triggered support in alarm_control_panel ([841dec2](https://github.com/mguyard/hass-diagral/commit/841dec2cffde38c0bdeb63e2df829cd92c9c5247))
* **diagral:** ✨ Update configuration and add alarm panel options ([302dc97](https://github.com/mguyard/hass-diagral/commit/302dc97c1772fb1f17d23d4fc5ef09a3eefa0eac))
* **diagral:** ✨ Update service names and descriptions for clarity ([51389e2](https://github.com/mguyard/hass-diagral/commit/51389e2216a0e2336dfa78fac3b0e198259c84dc))
* **docs:** 📚 Add webhook documentation and related content ([74c6384](https://github.com/mguyard/hass-diagral/commit/74c63840474efe81e58d1a895fc4b515a11c71fc))
* **hacs:** 🔧 Update Home Assistant version to 2025.2.0 ([4648701](https://github.com/mguyard/hass-diagral/commit/464870114a26fd1eaa9b49aa79a85648a2aaa8fb))
* **webhook:** 🔗 Add webhook registration and unregistration action ([94bab40](https://github.com/mguyard/hass-diagral/commit/94bab40f14b894a8302ee32f6ac3606b5aabcb1c))

# [1.1.0-beta.15](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.14...v1.1.0-beta.15) (2025-03-22)


### Bug Fixes

* **diagral:** 🐛 update `pydiagral` requirement to version 1.5.2 ([e4b3614](https://github.com/mguyard/hass-diagral/commit/e4b3614a159e06d58bbd784ba4b72ffec42ac5d5))

# [1.1.0-beta.14](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.13...v1.1.0-beta.14) (2025-03-15)


### Features

* **alarm_control_panel:** ✨ enhance code requirement logic for arming ([cf6d49c](https://github.com/mguyard/hass-diagral/commit/cf6d49ce53bb31d9521801cc20ccd554b6e5bc36))

# [1.1.0-beta.13](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.12...v1.1.0-beta.13) (2025-03-14)


### Features

* **diagral:** ✨ replace `triggered binary_sensor` by triggered support in alarm_control_panel ([841dec2](https://github.com/mguyard/hass-diagral/commit/841dec2cffde38c0bdeb63e2df829cd92c9c5247))

# [1.1.0-beta.12](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.11...v1.1.0-beta.12) (2025-03-09)


### Bug Fixes

* **alarm_control_panel:** 🐛 improve alarm state handling ([3b9e3f5](https://github.com/mguyard/hass-diagral/commit/3b9e3f5bfe448a8d93d12c290127587f4fa53f23))
* **webhook:** 🐛 fix webhook registration logic ([73ba0d7](https://github.com/mguyard/hass-diagral/commit/73ba0d784aeb62313e1c366695abeb73d50d2099))
* **webhook:** 🐛 improve logging for webhook data handling ([8a47783](https://github.com/mguyard/hass-diagral/commit/8a477838669054124d26c35a33e6c905c3f9ed12))

# [1.1.0-beta.11](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.10...v1.1.0-beta.11) (2025-03-09)


### Bug Fixes

* **webhook:** 🐛 Improve webhook registration logic ([05257c7](https://github.com/mguyard/hass-diagral/commit/05257c7fea690a0feff92963b9c02b357497e175))

# [1.1.0-beta.10](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.9...v1.1.0-beta.10) (2025-03-08)


### Bug Fixes

* **webhook:** 🐛 Resolve webhook registration/deletion with NabuCasa ([569733d](https://github.com/mguyard/hass-diagral/commit/569733dcec4fde0c1ee4fb6acb3e19bc466b1613))

# [1.1.0-beta.9](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.8...v1.1.0-beta.9) (2025-03-04)


### Bug Fixes

* **diagral:** 🐛 Handle missing user information in event processing ([3861c16](https://github.com/mguyard/hass-diagral/commit/3861c16bb0acd692a6e3db24b4847fc749f760a8))
* **diagral:** 🐛 Handle optional user information in event processing ([1abc896](https://github.com/mguyard/hass-diagral/commit/1abc8964eedd48a1af27752457938c24c6bacaa7))


### Features

* **diagral:** ✨ Add group information to binary sensor state attributes ([e9776dc](https://github.com/mguyard/hass-diagral/commit/e9776dc27c48c2093d04e327ac3f06b7c7730884))

# [1.1.0-beta.8](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.7...v1.1.0-beta.8) (2025-03-03)


### Bug Fixes

* **diagral:** ✨ Fix forgotten condition for property `code_arm_required` ([d2eed6a](https://github.com/mguyard/hass-diagral/commit/d2eed6a29ab398bdd4da58b7d702380ea010adda))


### Features

* **hacs:** 🔧 Update Home Assistant version to 2025.2.0 ([4648701](https://github.com/mguyard/hass-diagral/commit/464870114a26fd1eaa9b49aa79a85648a2aaa8fb))

# [1.1.0-beta.7](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.6...v1.1.0-beta.7) (2025-03-02)


### Features

* **diagral:** ✨ Add alarmpanel_code configuration option and refactor config_flow ([55fa23e](https://github.com/mguyard/hass-diagral/commit/55fa23e0bd8bc420b721908f808a69c64d0e8461))
* **diagral:** ✨ Refactor `validate_input` to use `TryConnectResult` ([d449f35](https://github.com/mguyard/hass-diagral/commit/d449f35b53fdb364813b75328ab3b57fbbab0749))
* **diagral:** ✨ Update configuration and add alarm panel options ([302dc97](https://github.com/mguyard/hass-diagral/commit/302dc97c1772fb1f17d23d4fc5ef09a3eefa0eac))

# [1.1.0-beta.6](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.5...v1.1.0-beta.6) (2025-02-26)


### Bug Fixes

* **webhook:** 🔗 Improve webhook registration handling ([0687699](https://github.com/mguyard/hass-diagral/commit/0687699678b86ddd00276ffd1d85dbf166434148))

# [1.1.0-beta.5](https://github.com/mguyard/hass-diagral/compare/v1.1.0-beta.4...v1.1.0-beta.5) (2025-02-26)


### Bug Fixes

* **webhook:** 🔗 Handle existing webhook subscriptions gracefully ([b180994](https://github.com/mguyard/hass-diagral/commit/b180994854669a199b1f085261b045e5a28d554f))

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
