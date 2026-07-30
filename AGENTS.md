# Repository agent guidelines

## GUI screenshot updates

- Check whether GUI screenshots need regeneration when changes affect the
  dashboard, navigation, channel tables, streaming indicators, visible
  localization, typography, colors, spacing, or window layout.
- Do not regenerate screenshots for backend-only or non-visual changes.
- Keep GUI screenshot generators, fixtures, and demo assets under
  `scripts/gui_showcase/`.
- Screenshot tooling must not be imported by production modules under
  `desktop_ui/`, `service/`, `utils/`, or `main.py`.
- Exclude `scripts/gui_showcase/` from Docker build contexts and GUI packaging
  artifacts. Exclude screenshot-specific validation tests from Docker images,
  and do not add fixtures or generated assets to PyInstaller `datas`.
- Demo generation must use temporary directories and must not modify user
  configuration, `config/`, or `output/`.
- Generate both Chinese and English screenshots, then verify demo data,
  service status, stream states, local logos, collapsed navigation, window
  focus, and native title-bar controls.
- Visually inspect generated screenshots before staging or committing them.
- CI may report stale screenshots or validate fixtures, but must not
  automatically commit regenerated binary assets.
- When packaging rules change, verify that screenshot tooling is absent from
  both Docker images and GUI distributions.
