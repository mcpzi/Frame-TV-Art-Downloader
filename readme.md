# Frame TV Art (pyscript)

Home Assistant [pyscript](https://github.com/custom-components/pyscript) app that fetches artwork/wallpaper images from several free online sources (or a local folder), crops/resizes them to fit a Samsung Frame TV, and uploads + selects them as the current Art Mode image.

## How it works

1. One or more **image sources** are tried in random order (`frame_tv_native/image_sources_native.py`). Each source
   returns a candidate image URL/path.
2. The candidate is downloaded and passed through `prepare_frame_image()`
   (`frame_tv_native/image_prep_native.py`), which:
   - rejects portrait/square images,
   - rejects images smaller than **1920x1080**,
   - rejects images whose aspect ratio is too far from 16:9 (`aspect_ratio_tolerance`),
   - center-crops and resizes surviving images to **3840x2160**.
3. If an image passes validation it's uploaded to the TV and selected as the active art
   (`frame_tv_native/samsung_api_native.py`, via [`samsungtvws`](https://github.com/xchwarze/samsung-tv-ws-api)).
4. If a source's candidate is rejected, it retries (up to `max_attempts_per_source` times) before moving on to the next source.

## Requirements

- Home Assistant with the [pyscript](https://hacs-pyscript.readthedocs.io/) custom integration installed (via HACS or
  manually).
- Python packages available to pyscript: `requests`, `Pillow`, `samsungtvws`.
- A Samsung Frame TV on the same network, in Art Mode, reachable by IP/hostname.

## Installation

1. Copy this folder's contents into your Home Assistant `config` directory so you end up with:

   ```
   /config/pyscript/frame_tv_art.py
   /config/pyscript_modules/frame_tv_native/__init__.py
   /config/pyscript_modules/frame_tv_native/image_sources_native.py
   /config/pyscript_modules/frame_tv_native/image_prep_native.py
   /config/pyscript_modules/frame_tv_native/samsung_api_native.py
   ```

2. Install the extra Python dependencies pyscript needs (e.g. via HA's `requirements` or a `venv` pip install,
   depending on how you run Home Assistant):

   ```
   pip install samsungtvws Pillow requests
   ```

3. Enable the required pyscript options in `configuration.yaml`:

   ```yaml
   pyscript:
     allow_all_imports: true
     hass_is_global: true
   ```

4. Restart Home Assistant (or reload pyscript) so `frame_tv_art.py` is picked up. Three new actions should appear under the `pyscript` domain (see below).
   
5. On the **first** upload, the TV will show a pairing prompt — accept it on the TV remote. The resulting token is cached in the file configured by `token_file` so future calls don't need re-pairing.

## Configuration

Edit the `CONFIG` dict at the top of `frame_tv_art.py`:

```python
CONFIG = {
    "tv_host": "192.168.1.141",
    "token_file": "/config/pyscript/.samsungtvws_token",
    "aspect_ratio_tolerance": 0.428,
    "max_attempts_per_source": 10,
    "enabled_sources": [
        "bing_wallpapers",
        "nga_landscapes",
        "met_japanese_prints",
        "met_european_landscapes",
    ],
    "media_folder_path": "/media/frame",
}
```

| Key                       | Description                                                                 |
|---------------------------|-------------------------------------------------------------------------------|
| `tv_host`                 | IP/hostname of the Frame TV. Can be overridden per-call.                     |
| `token_file`              | Where the TV pairing token is cached.                                        |
| `aspect_ratio_tolerance`  | How far from 16:9 (`3840/2160`) an image's ratio may be before it's rejected. |
| `max_attempts_per_source` | Retries per source before moving to the next one.                            |
| `enabled_sources`         | Which sources to use, and in what pool to randomly pick from (see below).    |
| `media_folder_path`       | Folder scanned recursively for `media_folder` source images.                 |

### Available sources (`enabled_sources`)

| Name                      | Description                                                              |
|---------------------------|----------------------------------------------------------------------------|
| `bing_wallpapers`         | Daily Bing wallpapers (native 16:9, almost always passes the filters).     |
| `nga_landscapes`          | National Gallery of Art — Monet/Sisley/Pissarro/Renoir landscape searches. |
| `met_japanese_prints`     | The Met — Japanese woodblock landscape prints, public domain only.        |
| `met_european_landscapes` | The Met — European landscape paintings, public domain only.               |
| `smithsonian_landscapes`  | Smithsonian Open Access. Requires `SMITHSONIAN_API_KEY` env var — silently disabled without it. |
| `media_folder`            | Random local `.jpg`/`.jpeg`/`.png` file under `media_folder_path`.        |

**Tip:** a lot of famous paintings are portrait-oriented and will be rejected. Sources/queries biased toward
landscapes, seascapes, interiors, architecture, panoramic photos, and wide museum scans work best.

## Actions (services)

### `pyscript.frame_tv_art_refresh`

Try the enabled sources (in random order) and upload the first image that passes validation.

| Parameter         | Type    | Default | Description                                                   |
|-------------------|---------|---------|-----------------------------------------------------------------|
| `source_override` | string  | *(all)* | Restrict to a single source name instead of trying all enabled ones. Must also be listed in `enabled_sources`, otherwise the call fails with "No enabled sources available". |
| `tv_host`         | string  | config default | Override the target TV for this call.                  |
| `dry_run`         | boolean | `false` | Fetch/validate/crop but skip the actual TV upload.             |

**Examples** (Developer Tools → Actions, or in an automation/script):

```yaml
# Basic refresh, using whatever is enabled in CONFIG
action: pyscript.frame_tv_art_refresh
```

```yaml
# Only pull from the Met's European landscapes
action: pyscript.frame_tv_art_refresh
data:
  source_override: met_european_landscapes
```

```yaml
# Target a different (e.g. second) Frame TV
action: pyscript.frame_tv_art_refresh
data:
  tv_host: 192.168.1.150
```

```yaml
# Dry run — see what would be picked without uploading anything
action: pyscript.frame_tv_art_refresh
data:
  dry_run: true
```

```yaml
# Combine: dry-run test of a specific source on a specific TV
action: pyscript.frame_tv_art_refresh
data:
  source_override: nga_landscapes
  tv_host: 192.168.1.150
  dry_run: true
```

Example automation — refresh the art every hour:

```yaml
automation:
  - alias: "Frame TV — hourly art refresh"
    trigger:
      - platform: time_pattern
        hours: "/1"
    action:
      - action: pyscript.frame_tv_art_refresh
```

### `pyscript.frame_tv_art_test_source`

Run the full fetch/validate/crop pipeline for one named source **without uploading**, useful for debugging why a source keeps failing.

| Parameter     | Type   | Default | Description                          |
|---------------|--------|---------|------------------------------------------|
| `source_name` | string | *(required)* | Must match one of the enabled source names. |
| `tv_host`     | string | config default | Unused for upload here, but accepted for consistency. |

```yaml
action: pyscript.frame_tv_art_test_source
data:
  source_name: bing_wallpapers
```

```yaml
action: pyscript.frame_tv_art_test_source
data:
  source_name: smithsonian_landscapes
```

Valid `source_name` values: `bing_wallpapers`, `nga_landscapes`, `met_japanese_prints`, `met_european_landscapes`, `smithsonian_landscapes`, `media_folder` (must also be listed in `enabled_sources` to be recognized).

### `pyscript.frame_tv_art_upload_file`

Upload a specific local image file directly, bypassing all sources.

| Parameter   | Type   | Default | Description                              |
|-------------|--------|---------|--------------------------------------------|
| `file_path` | string | *(required)* | Absolute path to a `.jpg`/`.jpeg`/`.png` file readable by Home Assistant. |
| `tv_host`   | string | config default | Override the target TV for this call. |

```yaml
action: pyscript.frame_tv_art_upload_file
data:
  file_path: /config/www/frame/sunset.jpg
```

```yaml
action: pyscript.frame_tv_art_upload_file
data:
  file_path: /config/www/frame/sunset.jpg
  tv_host: 192.168.1.150
```

All three actions are registered with `supports_response: optional`, so they can be called either way:

- **With a response** — from Developer Tools → Actions, tick **"Response data"** to see the result (`success`,
  `source`, `original_size`, `final_size`, `selected_image`, `message`, etc.) directly in the UI. From a
  script/automation, capture it with `response_variable`:

  ```yaml
  action: pyscript.frame_tv_art_refresh
  response_variable: frame_result
  ```

- **Without a response** — e.g. a Lovelace card `tap_action` (`perform-action`), which has no way to request a
  response. This works fine and simply discards the result; check the Home Assistant logs if you need to see what
  happened.

  ```yaml
  tap_action:
    action: perform-action
    perform_action: pyscript.frame_tv_art_refresh
    target: {}
  ```

## Troubleshooting

- **Pairing prompt keeps reappearing**: make sure `token_file` points to a writable path and isn't being wiped between restarts.
- **A source never returns anything**: call `pyscript.frame_tv_art_test_source` for that source and check the Home Assistant logs — the `message` field explains rejections (portrait, too small, aspect ratio, etc.).
- **Smithsonian source always fails**: set the `SMITHSONIAN_API_KEY` environment variable for the Home Assistant process before restarting.
- **Every image looks the same source**: sources are shuffled per run; if one source (e.g. `bing_wallpapers`) dominates, its images may simply be passing validation far more often than the others. Try narrowing`aspect_ratio_tolerance` or testing other sources individually.
