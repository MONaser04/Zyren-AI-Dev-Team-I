import mss
import io
import asyncio
from PIL import Image

try:
    import pygetwindow as gw
    GW_AVAILABLE = True
except ImportError:
    GW_AVAILABLE = False
    print("Warning: pygetwindow not installed. Window selection won't be available.")

def get_window_rect(title):
    if not GW_AVAILABLE:
        return None
    try:
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return None
        win = windows[0]
        # Return mss compatible dict
        return {"top": win.top, "left": win.left, "width": win.width, "height": win.height}
    except Exception as e:
        print(f"Error getting window {title}: {e}")
        return None

def select_capture_target():
    """
    Prompt the user via CLI to select what to share.
    """
    print("\n--- Screen Share Selection ---")
    print("1. Entire Desktop (All Monitors combined)")
    
    with mss.mss() as sct:
        monitors = sct.monitors
        # monitors[0] is a dict of all monitors combined
        # monitors[1] is the first monitor, etc.
        for i in range(1, len(monitors)):
            print(f"{i + 1}. Monitor {i} ({monitors[i]['width']}x{monitors[i]['height']})")
            
        window_options = []
        if GW_AVAILABLE:
            print("\n--- Open Windows ---")
            all_titles = gw.getAllTitles()
            window_options = [t for t in all_titles if t.strip()]
            start_idx = len(monitors) + 1
            for i, title in enumerate(window_options):
                print(f"{start_idx + i}. Window: {title}")
                
        while True:
            try:
                choice = int(input("\nEnter the number of the screen/window to share (or 0 to disable): "))
                if choice == 0:
                    print("Selected: Screen Sharing Disabled")
                    return None
                elif choice == 1:
                    print("Selected: Entire Desktop")
                    return {"type": "monitor", "index": 0}
                elif 1 < choice <= len(monitors):
                    print(f"Selected: Monitor {choice - 1}")
                    return {"type": "monitor", "index": choice - 1}
                elif GW_AVAILABLE and len(monitors) < choice <= len(monitors) + len(window_options):
                    win_title = window_options[choice - len(monitors) - 1]
                    print(f"Selected: Window '{win_title}'")
                    return {"type": "window", "title": win_title}
                else:
                    print("Invalid choice, please try again.")
            except ValueError:
                print("Please enter a valid number.")

class ScreenCaster:
    def __init__(self, target_config, screen_config):
        self.sct = mss.mss()
        self.target_config = target_config
        self.screen_config = screen_config

    def capture_jpeg(self):
        # Determine the rect to grab
        monitor = None
        
        if self.target_config["type"] == "monitor":
            monitor = self.sct.monitors[self.target_config["index"]]
        elif self.target_config["type"] == "window":
            monitor = get_window_rect(self.target_config["title"])
            if monitor is None:
                # Fallback to primary monitor if window was closed or not found
                monitor = self.sct.monitors[1] if len(self.sct.monitors) > 1 else self.sct.monitors[0]

        # 1. Grab the screen pixels
        sct_img = self.sct.grab(monitor)
        
        # 2. Convert raw BGRA pixels to PIL Image (RGB)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # Read from config
        max_res = tuple(self.screen_config.get("max_resolution", [1280, 720]))
        quality = self.screen_config.get("quality", 80)
        
        # 3. Resize to save bandwidth and reduce latency
        img.thumbnail(max_res)
        
        return img

async def screen_share_loop(session, target_config, screen_config):
    """
    Captures the screen and sends it to the Gemini Live session based on config.
    """
    if target_config is None:
        return
        
    fps = screen_config.get("fps", 1)
    print(f"Starting screen sharing ({fps} FPS)...")
    caster = ScreenCaster(target_config, screen_config)
    try:
        while True:
            # Capture frame in a separate thread so we don't block the asyncio loop
            img = await asyncio.to_thread(caster.capture_jpeg)
            
            # Send the frame to the Gemini Live API as a video frame
            await session.send_realtime_input(video=img)
            
            # Wait for next frame
            await asyncio.sleep(1.0 / fps)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[screen_share_loop] Error: {e}")
        raise
