# Spotify Advert Cover Script

This script monitors audio output from a Spotify app on Windows 11, and listens for the advert on teh free plan. When silence is detected for 1 second before a new track, it plays a hardcoded MP3 track and then restores the volume after a while, - when the advert is deemed to have ended.

## Requirements

- Windows 11
- Spotify windows app
- Python 3.10+
- A loopback or "Stereo Mix" audio device enabled

## Setup

```bash
git clone https://github.com/ruxy1212/spotify-cover.git
cd sound-monitor
pip install -r requirements.txt
```

## To Use
Turn on fade transition in your Spotify settings, increase it to at least 5seconds. Start the script, and enjoy without the repeated ads which can be embarrassing if being played on loudspeakers.

### Disclaimer
This script is for educational purpose only and does not in any way alter Spotify. It listens to your PC sound output, and detects when the advert is about to play, mutes it and then plays something else instead; If you want better experience without any disruptions, then subscribe to remove the ads totally.