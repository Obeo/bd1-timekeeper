<!-- Copyright (c) 2026 Obeo -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0/. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# Changelog

All notable changes to BD-1 are documented in this file.

## Unreleased

- Complete each worked day up to its share of the weekly target, with the
  `weekly_top_up_enabled` setting or the `--weekly-target` option.

## 0.2.2 - 2026-09-18

- Marshal macOS tray updates to the main thread for compatibility with macOS 27.

## 0.2.1 - 2026-09-18

- Support Eurecia SSO flows that ask for the e-mail address before the password.

## 0.2.0 - 2026-09-03

- Merge short work interruptions, including computer restarts, up to the configured
  inactivity threshold.
- Detect Windows VPN adapters from their driver description when their connection name
  is localized or renamed.
- Notify users when a newer stable GitHub release is available for their platform.
- Set an opt-in Mattermost custom status from the detected office or remote network.
- Add a tray window for Mattermost URL, personal access token, and VPN settings.
- Add opt-in system credential storage for Eurecia passwords.
- Support Eurecia editable forms that omit Standard row markers.
- Mark remotely worked Eurecia days with a managed `Télétravail/Remote` comment.
- Prefer office network signals over remote signals when marking Eurecia days.
- Ignore work blocks shorter than one minute when exporting to Eurecia.
- Prepare the project for distribution as open source under the EPL-2.0.
