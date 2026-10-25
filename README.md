<p align="center">
  <img src="https://brands.home-assistant.io/_/diagral/icon@2x.png" width="200" alt="Diagral" />
</p>
<h1 align="center">Diagral for Home Assistant</h1>
<p align="center">
  Arm, disarm and watch your Diagral alarm from Home Assistant, with intrusion alerts in real time.
</p>
<p align="center">
  <img src="https://img.shields.io/github/v/release/mguyard/hass-diagral?display_date=published_at&label=Stable" alt="Last Stable Release">
  <img src="https://img.shields.io/github/v/release/mguyard/hass-diagral?include_prereleases&filter=*-beta.*&display_name=release&label=Beta" alt="Last Beta Release">
  <img src="https://img.shields.io/github/license/mguyard/hass-diagral?color=0080ff" alt="License">
  <a href="https://codecov.io/gh/mguyard/hass-diagral"><img src="https://codecov.io/gh/mguyard/hass-diagral/graph/badge.svg?token=GKQZDY2KTO" alt="Codecov"></a>
</p>
<p align="center">
  <img src="https://github.com/mguyard/hass-diagral/actions/workflows/home-assistant.yaml/badge.svg" alt="Home Assistant validation">
  <img src="https://github.com/mguyard/hass-diagral/actions/workflows/release.yaml/badge.svg" alt="Release">
  <img src="https://img.shields.io/github/issues-search/mguyard/hass-diagral?query=label%3Abug%20is%3Aissue%20is%3Aopen&label=Open%20Bugs" alt="Open Bugs">
  <img src="https://img.shields.io/github/issues-pr/mguyard/hass-diagral" alt="Open PRs">
</p>

## Features

- **Alarm panel** — arm (away or presence mode), disarm, and arm or disarm individual groups, with or without a code.
- **Real-time updates** — Diagral pushes state changes, alerts and anomalies through a webhook: an intrusion sets the panel to `triggered` at once.
- **Automations** — every notification is fired as a `DIAGRAL_EVENT` and shown in the activity log.
- **Sensors** — anomalies with the device that raised them, active groups, webhook status and Diagral cloud connectivity.
- **Repairs and diagnostics** — webhook problems are explained in **Settings > System > Repairs**, and the diagnostics file helps find the cause of an issue without exposing your credentials.

## Requirements

- Home Assistant 2026.8 or later.
- A Diagral alarm with a connectivity module (DIAG56AAX, or DIAG59AAX inside a DIAG99AGX).
- A Diagral eOne account, the one used by the mobile application.
- For real-time updates: a Home Assistant reachable from the Internet over HTTPS, or a [Home Assistant Cloud](https://www.nabucasa.com) subscription. Without it, the state is refreshed every 5 minutes.

## Installation

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mguyard&repository=hass-diagral&category=Integration)

`Diagral` is a default HACS repository: search for it in HACS, download it, restart Home Assistant, then add the integration from **Settings > Devices & services**. See [Installation](https://docs.page/mguyard/hass-diagral/integration) and [Setup](https://docs.page/mguyard/hass-diagral/integration/setup).

## Documentation

The full documentation is published for each release channel:

- [Stable](https://docs.page/mguyard/hass-diagral)
- [Beta](https://docs.page/mguyard/hass-diagral~beta)

## Getting help

1. Check the [FAQ](https://docs.page/mguyard/hass-diagral/faq).
2. Download the diagnostics file and read the [diagnostics guide](https://docs.page/mguyard/hass-diagral/issues/diagnostics): it often points to the cause.
3. If the problem remains, [open an issue](https://github.com/mguyard/hass-diagral/issues/new/choose) with the diagnostics file attached.

## Contributing

Contributions are welcome: read the [contributing guide](CONTRIBUTING.md) first. Pull requests target the `dev` branch.

The integration talks to the Diagral cloud through [pydiagral](https://github.com/mguyard/pydiagral), maintained by the same author: a problem with the Diagral API is fixed there.

If this integration is useful to you, you can [sponsor its development](https://github.com/sponsors/mguyard).

## Disclaimer

This project is independent and not affiliated with Diagral or the Atraltech Group.
An alarm is a security system: connecting it to a home automation platform is your decision, and you use this integration at your own risk.

Released under the [GPL-3.0 license](LICENSE).
