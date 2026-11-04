# Keeping the pin and the location current

The home view is a painting of DGIST. When Mushfique is on campus, a pin sits on the building Mushfique is in (E1 to E8, R1 to R7, S1). Anywhere in the dorms, a single pin sits over the dorm area. When Mushfique is away, the caption reads "Away · city".

## How the position gets here

1. **OwnTracks** (free, open source, from Google Play) runs on the phone in HTTP mode. It sends a position when the phone has moved about 40 m, and at least every 10 minutes while moving. It uses high accuracy: balanced mode gave 100 m fixes on campus (no building pin), high accuracy gave 7 m.
2. It posts to the **relay**, `https://mushfique-screensaver.vercel.app/api/loc` (`endpoint/api/loc.js`).
   - The relay checks the phone's password (HTTP Basic, Vercel secret `LOC_PASSWORD`).
   - It writes `lat,lon,unix,accuracy` to the repository variable `LOC` using a fine-grained token (Vercel secret `GH_TOKEN`; Actions and Variables write on this repository only, 366 days).
   - It starts the workflow when the phone moved more than 40 m, or when the last reading had expired.
3. The **workflow** (`location.py`) turns `LOC` into a building code, "dorms", "campus" or a city. Only that result is published.

## What is public and what is not

- `LOC` is a repository variable, which the public cannot see. The token lives only on Vercel, and the phone holds only the relay password.
- `location.json` on the `output` branch holds the code, zone or city. That branch is force-pushed each run, so it keeps no history.
- A reading older than 6 hours is ignored, so a stale pin never stays on a building.
- A fix less accurate than 75 m places no building pin (only "DGIST").

## Setup (done once, on 4 November 2026)

- The relay password and the OwnTracks config (`owntracks.otrc`, plus the same config as an `owntracks:///config?inline=` link) live in `~/.config/dgist-location/` on the PC, outside every repository.
- The token was made from GitHub's pre-filled page by `sim/set_relay_token.py`. The token goes from a small window straight to Vercel and is never shown or saved anywhere else.
- On the phone (`sim/phone.py` over Wireless debugging):
  - Install OwnTracks.
  - Grant location all the time and notifications.
  - Remove its battery limits (Doze whitelist, background allowed).
  - Open the config link and import it. OwnTracks 2.5.9 accepts the link directly; newer versions put this behind Preferences → Remote control → "Allow configuration by URI and config file".

## Renewing or changing

- **Token expires (after 366 days):** run `python sim/set_relay_token.py` again.
- **Relay code changed:** run `python sim/deploy_relay.py`. It deploys from a copy outside git, because Vercel blocks deploys whose git commit author is not on the Vercel account.
- **New phone:** repeat the phone steps with the same config link.
- **By hand:** Actions tab → screensaver → Run workflow, with a city and a two-letter country code. A city never places a campus pin.
