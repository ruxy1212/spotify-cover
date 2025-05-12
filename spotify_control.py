import time
import numpy as np
import sounddevice as sd
import pygame
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
import psutil
from threading import Thread
from collections import deque
from threading import Event
import tkinter as tk
from tkinter import ttk 
import pythoncom

RUN_MONITOR = Event()
monitor_thread = None
# Configuration
TARGET_APP = "Spotify.exe"  # Replace with your app's executable name (e.g., "firefox.exe")
# MP3_PATH = r"C:\laragon\www\sound-control\playback.mp3"  # Replace with your MP3 file path
MP3_OPTIONS = {
    "Strong": r"C:\laragon\www\sound-control\playback.mp3",
    "Soft": r"C:\laragon\www\sound-control\soft.mp3"
}
selected_mp3_label = "Strong"  # default selection
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
    
    while RUN_MONITOR.is_set():
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE,
                               channels=2,
                               dtype='float32',
                               callback=audio_callback,
                               device=device_info['index']):
                while RUN_MONITOR.is_set():
                    time.sleep(CHECK_LOOP)
        except sd.PortAudioError as e:
            print(f"Audio device error: {e}. Retrying in 1 second...")
            time.sleep(1)
            if not RUN_MONITOR.is_set():
                break

    # with sd.InputStream(samplerate=SAMPLE_RATE,
    #                     channels=2,
    #                     dtype='float32',
    #                     callback=audio_callback,
    #                     device=device_info['index']):
    #     while True:
    #         time.sleep(CHECK_LOOP)


def main():
    global audio_level
    audio_level = 0
    
    pythoncom.CoInitialize()
    try:
        # Start audio monitoring in a separate thread
        audio_thread = Thread(target=monitor_audio)
        audio_thread.daemon = True
        audio_thread.start()
        
        while RUN_MONITOR.is_set():
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
            while RUN_MONITOR.is_set():
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
            
            if not RUN_MONITOR.is_set():
                set_volume(session, 1.0, FADE_DURATION)  # Restore volume before exiting
                break
            # Fade down app volume
            set_volume(session, 0.0, FADE_DURATION)
            
            # Play MP3
            # mp3_thread = Thread(target=play_mp3_with_fade, args=(MP3_PATH, MP3_PLAY_DURATION, FADE_DURATION))
            mp3_thread = Thread(target=play_mp3_with_fade, args=(MP3_OPTIONS[selected_mp3_label], MP3_PLAY_DURATION, FADE_DURATION))
            mp3_thread.start()
            
            # Wait for MP3 to finish
            mp3_thread.join()
            
            # Fade app volume back up
            set_volume(session, 1.0, FADE_DURATION)
            
            # Small delay to avoid immediate retrigger
            time.sleep(1)
    finally:
        pythoncom.CoUninitialize()

def start_monitoring(status_var, start_button, stop_button):
    global monitor_thread
    if monitor_thread and monitor_thread.is_alive():
        return  # Already running
    RUN_MONITOR.set()
    monitor_thread = Thread(target=main, daemon=True)
    monitor_thread.start()

    status_var.set("Listening")
    start_button.config(state=tk.DISABLED, bg="#cccccc", cursor="arrow")
    stop_button.config(state=tk.NORMAL, bg="#f44336", cursor="hand2")

def stop_monitoring(status_var, start_button, stop_button):
    RUN_MONITOR.clear()

    status_var.set("Not Listening")
    start_button.config(state=tk.NORMAL, bg="#4CAF50", cursor="hand2")
    stop_button.config(state=tk.DISABLED, bg="#cccccc", cursor="arrow")

def on_enter_start(event, button):
    if button["state"] != tk.DISABLED:
        button.config(bg="#45a049")  # Darker green on hover

def on_leave_start(event, button):
    if button["state"] != tk.DISABLED:
        button.config(bg="#4CAF50")  # Original green

def on_enter_stop(event, button):
    if button["state"] != tk.DISABLED:
        button.config(bg="#d32f2f")  # Darker red on hover

def on_leave_stop(event, button):
    if button["state"] != tk.DISABLED:
        button.config(bg="#f44336")  # Original red

def create_gui():
    global selected_mp3_label
    window = tk.Tk()
    window.title("Sound Monitor Controller")
    window.geometry("300x450")
    window.configure(bg="#2c2c2c")

    # Title with extra space above
    title = tk.Label(window, text="Spotify Cover", font=("Arial", 18, "bold"), bg="#2c2c2c", fg="#ffffff")
    title.pack(pady=(20, 10))  # Increased top padding

    selection_label = tk.Label(window, text="Select Sound:", bg="#2c2c2c", fg="white", font=("Arial", 12))
    selection_label.pack()
    mp3_var = tk.StringVar(value="Strong")
    mp3_dropdown = ttk.Combobox(window, textvariable=mp3_var, values=list(MP3_OPTIONS.keys()), state="readonly")
    mp3_dropdown.pack(pady=(0, 10))

    # When user selects a different sound
    def on_selection_change(event):
        global selected_mp3_label
        selected_mp3_label = mp3_var.get()

    mp3_dropdown.bind("<<ComboboxSelected>>", on_selection_change)

    slider_label = tk.Label(window, text="Silence Duration (sec):", bg="#2c2c2c", fg="white", font=("Arial", 12))
    slider_label.pack(pady=(5, 0))

    # Slider widget
    silence_slider = tk.Scale(window, from_=1.0, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, length=200, bg="#2c2c2c", fg="white", troughcolor="#444", highlightthickness=0)
    silence_slider.set(SILENCE_DURATION)
    silence_slider.pack()

    def on_slider_change(val):
        global SILENCE_DURATION
        global AUDIO_WINDOW
        SILENCE_DURATION = float(val)
        AUDIO_WINDOW = deque(maxlen=int(SILENCE_DURATION / CHECK_LOOP))

    silence_slider.config(command=on_slider_change)

    # Status Label
    status_var = tk.StringVar(value="Not Listening")
    status_label = tk.Label(window, textvariable=status_var, font=("Arial", 14), bg="#2c2c2c", fg="#00ff00")
    status_label.pack(pady=10)

    # Buttons Frame
    button_frame = tk.Frame(window, bg="#2c2c2c")
    button_frame.pack(pady=10)

    # Start Button
    start_button = tk.Button(
        button_frame, 
        text="Start Listening", 
        width=15, 
        command=lambda: start_monitoring(status_var, start_button, stop_button), 
        bg="#4CAF50", 
        fg="white", 
        font=("Arial", 12),
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        cursor="hand2"
    )
    start_button.pack(pady=5)
    start_button.bind("<Enter>", lambda e: on_enter_start(e, start_button))
    start_button.bind("<Leave>", lambda e: on_leave_start(e, start_button))

    # Stop Button (initially disabled)
    stop_button = tk.Button(
        button_frame, 
        text="Stop Listening", 
        width=15, 
        command=lambda: stop_monitoring(status_var, start_button, stop_button), 
        bg="#cccccc", 
        fg="white", 
        font=("Arial", 12),
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        cursor="arrow",
        state=tk.DISABLED
    )
    stop_button.pack(pady=5)
    stop_button.bind("<Enter>", lambda e: on_enter_stop(e, stop_button))
    stop_button.bind("<Leave>", lambda e: on_leave_stop(e, stop_button))

    window.mainloop()

# def create_gui():
#     window = tk.Tk()
#     window.title("Sound Monitor Controller")
#     window.geometry("300x300")
#     window.configure(bg="#2c2c2c")

#     # Title
#     title = tk.Label(window, text="Spotify Cover", font=("Arial", 18, "bold"), bg="#2c2c2c", fg="#ffffff")
#     title.pack(pady=10)

#     # Status Label
#     status_var = tk.StringVar(value="Not Listening")
#     status_label = tk.Label(window, textvariable=status_var, font=("Arial", 14), bg="#2c2c2c", fg="#00ff00")
#     status_label.pack(pady=10)

#     # Buttons Frame
#     button_frame = tk.Frame(window, bg="#2c2c2c", cursor="hand2")
#     button_frame.pack(pady=10)

#     # Start Button
#     start_button = tk.Button(
#         button_frame, 
#         text="Start Listening", 
#         width=15, 
#         command=lambda: start_monitoring(status_var, start_button, stop_button), 
#         bg="#4CAF50", 
#         fg="white", 
#         font=("Arial", 12),
#         relief="flat"
#     )
#     start_button.pack(pady=5)

#     # Stop Button (initially disabled)
#     stop_button = tk.Button(
#         button_frame, 
#         text="Stop Listening", 
#         width=15, 
#         command=lambda: stop_monitoring(status_var, start_button, stop_button), 
#         bg="#cccccc", 
#         fg="white", 
#         font=("Arial", 12),
#         relief="flat",
#         state=tk.DISABLED
#     )
#     stop_button.pack(pady=5)

#     window.mainloop()

if __name__ == "__main__":
    # main()
    create_gui()