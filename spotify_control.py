import time
import numpy as np
import sounddevice as sd
import pygame
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
import psutil
from threading import Thread
from collections import deque

# Configuration
TARGET_APP = "Spotify.exe"  # Replace with your app's executable name (e.g., "firefox.exe")
MP3_PATH = r"C:\laragon\www\sound-control\playback.mp3"  # Replace with your MP3 file path
SILENCE_THRESHOLD = 0.01  # Amplitude threshold for silence (adjust if needed)
SILENCE_DURATION = 1.0  # Silence duration in seconds (1000ms)
FADE_DURATION = 1.0  # Fade in/out duration in seconds
MP3_PLAY_DURATION = 26.0  # MP3 playback duration in seconds
SAMPLE_RATE = 44100  # Audio sampling rate
CHECK_INTERVAL = 0.1  # How often to check audio (seconds)
CHECK_LOOP = 0.1
AUDIO_WINDOW = deque(maxlen=int(SILENCE_DURATION / CHECK_LOOP))  # approx 1 sec window


def get_app_volume_session(app_name):
    """Find the audio session for the target app."""
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.name().lower() == app_name.lower():
            return session._ctl.QueryInterface(ISimpleAudioVolume)
    return None

def set_volume(session, volume, fade_duration=0):
    """Set the volume of an audio session with optional fade."""
    if session is None:
        return
    if fade_duration > 0:
        steps = 50
        current_volume = session.GetMasterVolume()
        for i in range(steps + 1):
            intermediate_volume = current_volume + (volume - current_volume) * (i / steps)
            session.SetMasterVolume(min(max(intermediate_volume, 0.0), 1.0), None)
            time.sleep(fade_duration / steps)
    else:
        session.SetMasterVolume(min(max(volume, 0.0), 1.0), None)

def play_mp3_with_fade(mp3_path, play_duration, fade_duration):
    """Play MP3 with fade-in and fade-out."""
    pygame.mixer.init()
    pygame.mixer.music.load(mp3_path)
    pygame.mixer.music.set_volume(0.0)
    pygame.mixer.music.play()
    
    # Fade in
    steps = 50
    for i in range(steps + 1):
        pygame.mixer.music.set_volume(i / steps)
        time.sleep(fade_duration / steps)
    
    # Play for remaining duration
    time.sleep(play_duration - 2 * fade_duration)
    
    # Fade out
    for i in range(steps, -1, -1):
        pygame.mixer.music.set_volume(i / steps)
        time.sleep(fade_duration / steps)
    
    pygame.mixer.music.stop()
    pygame.mixer.quit()

def is_app_running(app_name):
    """Check if the target app is running."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == app_name.lower():
            return True
    return False

def audio_callback(indata, frames, time_info, status):
    global audio_level
    current_max = np.max(np.abs(indata))
    AUDIO_WINDOW.append(current_max)
    audio_level = max(AUDIO_WINDOW)

# def audio_callback(indata, frames, time_info, status):
#     """Callback to process audio data."""
#     global audio_level
#     audio_level = np.max(np.abs(indata))

# def monitor_audio():
#     """Monitor the audio output of the system."""
#     with sd.InputStream(samplerate=SAMPLE_RATE, channels=2, callback=audio_callback):
#         while True:
#             time.sleep(CHECK_INTERVAL)

def monitor_audio():
    global audio_level
    # Find loopback input device (what-you-hear)
    device_info = None
    for device in sd.query_devices():
        if "loopback" in device['name'].lower() or "stereo mix" in device['name'].lower():
            device_info = device
            break

    if not device_info:
        raise RuntimeError("No loopback device found. Enable 'Stereo Mix' or a virtual cable.")

    with sd.InputStream(samplerate=SAMPLE_RATE,
                        channels=2,
                        dtype='float32',
                        callback=audio_callback,
                        device=device_info['index']):
        while True:
            time.sleep(CHECK_LOOP)


def main():
    global audio_level
    audio_level = 0
    
    # Start audio monitoring in a separate thread
    audio_thread = Thread(target=monitor_audio)
    audio_thread.daemon = True
    audio_thread.start()
    
    while True:
        if not is_app_running(TARGET_APP):
            time.sleep(1)
            continue
        
        session = get_app_volume_session(TARGET_APP)
        if session is None:
            time.sleep(1)
            continue
        
        # Check for silence
        silence_start = None
        print(audio_level, silence_start)
        while True:
            # print('seen', silence_start, audio_level, None)
            if audio_level < SILENCE_THRESHOLD:
                if silence_start is None:
                    print(audio_level)
                    silence_start = time.time()
                elif time.time() - silence_start >= SILENCE_DURATION:
                    # print(audio_level, time.time(), silence_start)
                    break
            else:
                silence_start = None
            time.sleep(CHECK_INTERVAL)
        
        # Fade down app volume
        set_volume(session, 0.0, FADE_DURATION)
        
        # Play MP3
        mp3_thread = Thread(target=play_mp3_with_fade, args=(MP3_PATH, MP3_PLAY_DURATION, FADE_DURATION))
        mp3_thread.start()
        
        # Wait for MP3 to finish
        mp3_thread.join()
        
        # Fade app volume back up
        set_volume(session, 1.0, FADE_DURATION)
        
        # Small delay to avoid immediate retrigger
        time.sleep(1)

if __name__ == "__main__":
    main()