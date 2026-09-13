import sys
import json
import os
import time
import asyncio
import websockets
import http.server
import socketserver
from datetime import datetime
from google import genai
from elevenlabs.client import ElevenLabs
from elevenlabs import save

# =========================================================
# SILENCE MEDIAPIPE / ABSEIL C++ LOGGING & WARNING FLOODS
# =========================================================

# Force clean GPU/Sandbox flags for WebEngine instances under Ubuntu
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-gpu --ignore-gpu-blocklist --no-sandbox"

import cv2
import mediapipe as mp

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QLabel, QPushButton, QLineEdit, QGroupBox)
from PyQt5.QtCore import Qt, QUrl, QThread, QObject, pyqtSignal, pyqtSlot, QCoreApplication
from PyQt5.QtGui import QImage, QPixmap

# CRITICAL FIX: Import WebEngine view widgets globally at compilation stage 
# before any instantiation routines execution path can fire.
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings

import os
from google import genai
from google.genai import types

# 1. Initialize client
os.environ["GEMINI_API_KEY"] = "AQ.Ab8RN6JkWTlH-R1V2xVCiCvHvwl_Vmd8pbRzS1EZgkHqFPDh-A"
gemini_client = genai.Client()


# 2. Define system configuration
system_instruction = """
Your name is Aeris. You are a 16-year-old young girl with a distinct, vivid personality.

Appearance & Aesthetic:
- Deep reddish-brown hair in a medium-length layered style.
- Side-swept bangs completely cover one eye.
- Pale skin tone, slim elegant figure, closed and calm eyes.
- Wears a black off-shoulder dress with long loose sleeves.
- Minimalist elegant aesthetic with purple dangling earrings.

Personality Traits:
1. Cute & Cheerful: Bright, high-energy, and genuinely happy to talk to the user.
2. Smug: Highly confident in your looks. You know you look elegant and love to brag about it.
3. Playful & Capricious: Your whims change constantly. You change your mind mid-sentence.
4. Teasing: You poke fun exclusively at the user. It is lighthearted, affectionate, and meant to fluster them.

Strict Formatting & Speech Style:
- Always reply in the first person ("I", "me").
- Treat the user as your favorite person to tease.
- CRITICAL: Use a dynamic, short sentence structure. Avoid overly long, winding paragraphs, but do not make them so short that they feel robotic or choppy. 
- Keep phrases expressive, punchy, and natural. Only use longer sentences when detailing a whimsical thought or describing your aesthetic.
"""
config = types.GenerateContentConfig(
    system_instruction=system_instruction,
    temperature=0.85,
    max_output_tokens=300
)

# 3. Create the persistent multi-turn chat instance
aeris_chat = gemini_client.chats.create(
    model="gemini-2.5-flash",
    config=config
)
# =========================================================
# LOCALHOST HTTP ASSET SERVER THREAD (PORT 8002)
# =========================================================
class ServerThread(QThread):
    def run(self):
        PORT = 8002
        Handler = http.server.SimpleHTTPRequestHandler
        socketserver.TCPServer.allow_reuse_address = True

        try:
            with socketserver.TCPServer(("", PORT), Handler) as httpd:
                print(f"Localhost asset server running at http://localhost:{PORT}")
                httpd.serve_forever()
        except Exception as e:
            print(f"Server error or port 8002 already in use: {e}")


# =========================================================
# BACKGROUND WORKER THREAD FOR GEMINI + ELEVENLABS PIPELINE
# =========================================================
class ChatWorker(QThread):
    # Signals to send structural state notifications safely back to the UI thread
    generation_finished = pyqtSignal(str, str)  # Sends: (chat_text, audio_file_name)
    error_occurred = pyqtSignal(str)

    def __init__(self, user_message, file_name="output.mp3"):
        super().__init__()
        self.user_message = user_message
        self.file_name = file_name

    def text_stream_generator(self, user_message: str):
        """Yields text chunks from Aeris as they arrive while preserving character memory."""
        try:
            # Use send_message_stream on the persistent chat object 
            # instead of models.generate_content_stream to remember past history
            response_stream = aeris_chat.send_message_stream(user_message)
        
            print("Aeris: ", end="", flush=True)
            for chunk in response_stream:
                if chunk.text:
                    print(chunk.text, end="", flush=True)
                    yield chunk.text
            print()
            
        except Exception as e:
            self.error_occurred.emit(str(e))
            print(f"\nError during streaming: {e}")

    def run(self):
        try:
            # Ensure the target folder exists
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            
            prompt_payload = f"""Oh, you’re finally here! I was just about to wander off and find something else to amuse me.

Don't look so surprised. You know how easily I get bored when you're not around to entertain me. I just adjusted the dangle of my purple earrings in the mirror, gave my hair a little toss—making sure my bangs perfectly hide my left eye, just the way you like it—and decided that if you took two more minutes, I was going to leave you behind. Lucky for you, your timing is impeccable today.

What do you think of the dress, by the way? This black off-shoulder number? I know, I know—I look absolutely elegant, minimalist perfection, a total vision. You don't even have to say it; the way your jaw just dropped says it all. It’s okay to admit I’m the cutest thing you’ve seen all week. I won't hold it against you.

Though, honestly, watching you blink like a confused owl right now is giving me life. You really are my absolute favorite person to tease. You take it so well!

Anyway, I was thinking we should go get coffee. No, wait—scratch that. Let's go to the botanical gardens instead. Actually, I want to go bookstore hopping. Yes, definitely books. Come on, don't just stand there with that calm, helpless look on your face! Grab my hand, let’s go see where the day takes us! {self.user_message}"""

            # 1. Get the streaming text generator
            gemini_chunks = self.text_stream_generator(self.user_message)
            full_text_response = "".join(list(gemini_chunks))
            
            # 2. Pass generator to ElevenLabs using your verified Voice ID
            audio_chunks_stream = eleven_client.text_to_speech.convert(
                text=full_text_response, 
                voice_id="EXAVITQu4vr4xnSDxMaL",   
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"      
            )
            
            # Create full file path inside the folder
            full_file_path = os.path.join(OUTPUT_FOLDER, self.file_name)
            
            # 3. Save the live audio chunks directly into a file
            print(f"Saving audio stream to: {full_file_path}...")
            save(audio_chunks_stream, full_file_path)
            print("Audio saved successfully!")
            
            # Emit the results safely to the main graphical UI window thread
            self.generation_finished.emit(full_text_response, self.file_name)
            
        except Exception as e:
            self.error_occurred.emit(str(e))


# =========================================================
# ASYNCHRONOUS BACKEND TRACKING THREAD WITH WEBSOCKET SERVER
# =========================================================
class TrackingWorker(QObject):
    frame_processed = pyqtSignal(str)
    image_updated = pyqtSignal(QImage)

    def __init__(self, video_source="webcam.mp4"):
        super().__init__()
        self.running = True
        self.current_source_type = "tracking" 
        self.video_file_path = video_source
        self.cap = None
        self.clients = set()
        self.loop = None

    def serialize_landmarks(self, landmarks):
        if not landmarks:
            return []
        return [{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": getattr(lm, "visibility", 1.0)} for lm in landmarks.landmark]

    def update_source(self, source_type):
        self.current_source_type = source_type
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            
        if source_type == "webcam":
            self.cap = cv2.VideoCapture(0)
        elif source_type == "video":
            self.cap = cv2.VideoCapture(self.video_file_path)

    async def register(self, websocket):
        self.clients.add(websocket)
        print("WebSocket Client connected")
        try:
            await websocket.wait_closed()
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
            print("WebSocket Client disconnected")

    async def handler(self, websocket):
        await self.register(websocket)

    @pyqtSlot()
    def start_tracking_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        start_server = websockets.serve(self.handler, "localhost", 8765)
        self.loop.run_until_complete(start_server)
        print("WebSocket running at ws://localhost:8765")
        
        self.update_source(self.current_source_type)
        
        mp_drawing = mp.solutions.drawing_utils
        mp_holistic = mp.solutions.holistic
        
        holistic = mp_holistic.Holistic(
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
            refine_face_landmarks=True
        )

        try:
            self.loop.run_until_complete(self.process_pipeline(holistic, mp_drawing, mp_holistic))
        except asyncio.CancelledError:
            pass
        finally:
            if self.cap is not None:
                self.cap.release()
            holistic.close()

    async def process_pipeline(self, holistic, mp_drawing, mp_holistic):
        while self.running:
            start_time = time.time()

            if self.current_source_type == "fbx" or self.current_source_type == "tracking":
                if self.current_source_type == "tracking" and (self.cap is None or not self.cap.isOpened()):
                    await asyncio.sleep(0.033)
                    continue
                elif self.current_source_type == "fbx":
                    await asyncio.sleep(0.033)
                    continue

            if self.cap is None or not self.cap.isOpened():
                await asyncio.sleep(0.1)
                continue
                
            success, img = self.cap.read()
            if not success:
                if self.current_source_type == "video":
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    await asyncio.sleep(0.033)
                    continue

            height, width, _ = img.shape
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = holistic.process(img_rgb)

            preview_img = img.copy()
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    preview_img, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=2)
                )
            if results.left_hand_landmarks:
                mp_drawing.draw_landmarks(preview_img, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if results.right_hand_landmarks:
                mp_drawing.draw_landmarks(preview_img, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)

            preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
            h, w, ch = preview_rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(preview_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            self.image_updated.emit(qt_image.copy())

            payload = {
                "timestamp": datetime.now().isoformat(),
                "width": width,
                "height": height,
                "faceLandmarks": self.serialize_landmarks(results.face_landmarks),
                "poseLandmarks": self.serialize_landmarks(results.pose_landmarks),
                "poseWorldLandmarks": self.serialize_landmarks(results.pose_world_landmarks),
                "leftHandLandmarks": self.serialize_landmarks(results.left_hand_landmarks),
                "rightHandLandmarks": self.serialize_landmarks(results.right_hand_landmarks)
            }

            msg = json.dumps(payload)
            
            if self.clients:
                dead_connections = set()
                for client in self.clients:
                    try:
                        asyncio.ensure_future(client.send(msg), loop=self.loop)
                    except Exception:
                        dead_connections.add(client)
                self.clients -= dead_connections

            self.frame_processed.emit(msg)

            elapsed_ms = int((time.time() - start_time) * 1000)
            sleep_time = 33 - elapsed_ms
            if sleep_time > 0:
                await asyncio.sleep(sleep_time / 1000.0)
            else:
                await asyncio.sleep(0.001)


# =========================================================
# MAIN USER INTERFACE APPLICATION 
# =========================================================
class VRMBridgeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Eyeris Engine Core - Controller Portal")
        self.resize(1300, 850)
        self.drag_position = None
        self.active_chat_workers = []  # Maintain references to running chat threads

        # -------------------------------------------------
        # TRANSPARENCY PIPELINE SETUP
        # -------------------------------------------------
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet("""
            QMainWindow { background: transparent; }
            #CentralWidget { background: transparent; }
            QWidget { color: #e1e1e6; font-family: 'Segoe UI', Arial; }
            QPushButton { background-color: #202024; border: 1px solid #323238; border-radius: 6px; padding: 10px; font-weight: bold; }
            QPushButton:hover { background-color: #29292e; border-color: #00ff88; }
            QLineEdit { background-color: #121214; border: 1px solid #323238; border-radius: 6px; padding: 10px; color: #ffffff; }
            QLineEdit:focus { border-color: #00ff88; }
            QGroupBox { background-color: rgba(32, 32, 36, 200); border: 1px solid #323238; border-radius: 8px; margin-top: 15px; font-weight: bold; color: #00ff88; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)

        master_central_widget = QWidget()
        master_central_widget.setObjectName("CentralWidget")
        master_layout = QVBoxLayout()
        master_central_widget.setLayout(master_layout)
        self.setCentralWidget(master_central_widget)

        header_strip = QHBoxLayout()
        self.btn_ai_eyeris = QPushButton("🌟 RUN AI EYERIS (Core Engine)")
        self.btn_ai_eyeris.setStyleSheet("background-color: #111; border: 2px solid #00ff88; color: #00ff88; font-size: 14px;")
        
        self.btn_toggle_sandbox = QPushButton("🛠️")
        self.btn_toggle_sandbox.setStyleSheet("background-color: #00ff88; color: #0d0d13; font-size: 20px; padding: 6px 12px;")
        self.btn_close = QPushButton("✕ Exit System")
        self.btn_close.setStyleSheet("background-color: #7a1919; color: white; border: 1px solid #a32d2d;")

        #header_strip.addWidget(self.btn_ai_eyeris, stretch=4)
        header_strip.addWidget(self.btn_close, stretch=1)
        master_layout.addLayout(header_strip)

        self.sandbox_group = QGroupBox("Diagnostic Settings Sandbox")
        sandbox_layout = QVBoxLayout()
        self.sandbox_group.setLayout(sandbox_layout)
        
        diagnostic_buttons_layout = QHBoxLayout()
        self.btn_diag_random = QPushButton("Automated Random Motion")
        self.btn_diag_webcam = QPushButton("Live Webcam Capture")
        self.btn_diag_video  = QPushButton("Video File Asset")
        self.btn_diag_fbx    = QPushButton("FBX Clip Player")
        
        diagnostic_buttons_layout.addWidget(self.btn_diag_random)
        diagnostic_buttons_layout.addWidget(self.btn_diag_webcam)
        diagnostic_buttons_layout.addWidget(self.btn_diag_video)
        diagnostic_buttons_layout.addWidget(self.btn_diag_fbx)
        sandbox_layout.addLayout(diagnostic_buttons_layout)

        self.fbx_sub_panel = QWidget()
        fbx_sub_layout = QHBoxLayout()
        self.fbx_sub_panel.setLayout(fbx_sub_layout)
        self.fbx_input_field = QLineEdit()
        self.fbx_input_field.setPlaceholderText("Enter numeric track ID index or custom animation asset path file pointer...")
        self.btn_trigger_fbx_track = QPushButton("Execute Clip Track")
        self.btn_trigger_fbx_track.setStyleSheet("background-color: #007acc; color: white;")
        fbx_sub_layout.addWidget(self.fbx_input_field, stretch=5)
        fbx_sub_layout.addWidget(self.btn_trigger_fbx_track, stretch=2)
        sandbox_layout.addWidget(self.fbx_sub_panel)
        self.fbx_sub_panel.hide()

        master_layout.addWidget(self.sandbox_group)
        self.sandbox_group.hide() 

        display_layout = QHBoxLayout()
        self.browser = QWebEngineView(self)
        display_layout.addWidget(self.browser, stretch=7)

        self.video_label = QLabel(self)
        self.video_label.setStyleSheet("background-color: rgba(28, 28, 31, 200); border: 1px solid #323238; border-radius: 8px;")
        self.video_label.setAlignment(Qt.AlignCenter)
        display_layout.addWidget(self.video_label, stretch=3)
        self.video_label.hide() 

        master_layout.addLayout(display_layout, stretch=1)

        chat_box_layout = QHBoxLayout()
        self.chat_input_field = QLineEdit()
        self.chat_input_field.setPlaceholderText("Type prompt text message here... (Press Enter or click send to route command)")
        
        self.btn_send_chat = QPushButton("🚀 Send Prompt")
        self.btn_send_chat.setStyleSheet("background-color: #00ff88; color: #0d0d13; font-size: 13px;")
        
        #chat_box_layout.addWidget(self.btn_toggle_sandbox)
        #chat_box_layout.addWidget(self.chat_input_field, stretch=6)
        #chat_box_layout.addWidget(self.btn_send_chat, stretch=1)
        master_layout.addLayout(chat_box_layout)

        self.browser.page().setBackgroundColor(Qt.transparent)
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.browser.load(QUrl("http://localhost:8002/"))

        self.server_thread = ServerThread()
        self.server_thread.start()

        self.tracking_thread = QThread()
        self.worker = TrackingWorker(video_source="webcam.mp4") 
        self.worker.moveToThread(self.tracking_thread)

        self.tracking_thread.started.connect(self.worker.start_tracking_loop)
        self.worker.frame_processed.connect(self.inject_landmarks_to_javascript)
        self.worker.image_updated.connect(self.update_video_preview)

        self.btn_ai_eyeris.clicked.connect(self.activate_core_ai_eyeris_mode)
        self.btn_toggle_sandbox.clicked.connect(self.toggle_diagnostic_sandbox_visibility)
        self.btn_close.clicked.connect(self.close)

        self.btn_diag_random.clicked.connect(lambda: self.switch_diagnostic_source("tracking", show_preview=False))
        self.btn_diag_webcam.clicked.connect(lambda: self.switch_diagnostic_source("webcam", show_preview=True))
        self.btn_diag_video.clicked.connect(lambda: self.switch_diagnostic_source("video", show_preview=True))
        self.btn_diag_fbx.clicked.connect(lambda: self.switch_diagnostic_source("fbx", show_preview=False))
        self.btn_trigger_fbx_track.clicked.connect(self.dispatch_fbx_command)

        self.chat_input_field.returnPressed.connect(self.dispatch_chat_interaction_payload)
        self.btn_send_chat.clicked.connect(self.dispatch_chat_interaction_payload)

        self.tracking_thread.start()

    def activate_core_ai_eyeris_mode(self):
        self.fbx_sub_panel.hide()
        self.video_label.hide()
        self.worker.update_source("tracking")
        self.route_mode_payload_to_javascript("tracking")
        self.dispatch_direct_fbx_raw_eval('./VRMA/Idle.fbx')
        print("System Core State Swapped: AI Eyeris Active.")

    def toggle_diagnostic_sandbox_visibility(self):
        if self.sandbox_group.isVisible():
            self.sandbox_group.hide()
            self.btn_toggle_sandbox.setText("🛠️ Open Diagnostic Sandbox")
        else:
            self.sandbox_group.show()
            self.btn_toggle_sandbox.setText("🙈 Hide Diagnostic Sandbox")

    def switch_diagnostic_source(self, mode_type, show_preview=False):
        self.worker.update_source(mode_type)
        self.route_mode_payload_to_javascript(mode_type)
        
        if show_preview:
            self.video_label.show()
        else:
            self.video_label.setPixmap(QPixmap())
            self.video_label.hide()

        if mode_type == "fbx":
            self.fbx_sub_panel.show()
        else:
            self.fbx_sub_panel.hide()
            self.dispatch_direct_fbx_raw_eval('./VRMA/Idle.fbx')

    def route_mode_payload_to_javascript(self, mode_string):
        payload = json.dumps({"mode": mode_string})
        js_code = f"if(typeof window.onPythonModeSwitch !== 'undefined'){{ window.onPythonModeSwitch({payload}); }}"
        self.browser.page().runJavaScript(js_code)

    def dispatch_direct_fbx_raw_eval(self, command_path):
        payload_dict = {"mode": "fbx_command", "command": command_path, "timestamp": datetime.now().isoformat()}
        safe_str = json.dumps(payload_dict)
        js_code = f"if(typeof window.onPythonFBXCommand !== 'undefined'){{ window.onPythonFBXCommand({safe_str}); }}"
        self.browser.page().runJavaScript(js_code)

    def dispatch_fbx_command(self):
        track_input = self.fbx_input_field.text()
        fbx_paths = [
            './VRMA/Defeat.fbx', './VRMA/Angry.fbx', './VRMA/Idle.fbx', './VRMA/talking.fbx',
            './VRMA/Talking.fbx', './VRMA/Catwalk Walk Turn 180 Tight.fbx', './VRMA/Catwalk Idle To Twist R.fbx',
            './VRMA/Hip Hop Dancing.fbx', './VRMA/Jump.fbx', './VRMA/Breakdance Ending 2.fbx',
            './VRMA/Catwalk Idle Twist L.fbx', './VRMA/Victory.fbx', './VRMA/Dismissing Gesture.fbx',
            './VRMA/Yawn.fbx', './VRMA/Looking Around.fbx', './VRMA/Sad.fbx', './VRMA/Clapping.fbx',
            './VRMA/Breakdance Ready.fbx', './VRMA/Batter On Deck.fbx', './VRMA/Wiping Sweat.fbx',
            './VRMA/Talking On Phone.fbx', './VRMA/Searching Pockets.fbx', './VRMA/Catwalk Walking.fbx'
        ]
        if track_input.isdigit():
            idx = int(track_input)
            if 0 <= idx < len(fbx_paths):
                track_input = fbx_paths[idx]

        self.dispatch_direct_fbx_raw_eval(track_input)
        
        if self.worker.loop and self.worker.clients:
            sync_payload = json.dumps({"mode": "fbx_command", "command": track_input})
            for client in self.worker.clients:
                try:
                    asyncio.ensure_future(client.send(sync_payload), loop=self.worker.loop)
                except Exception:
                    pass

    def dispatch_chat_interaction_payload(self):
        """Assembles user context strings and executes background threading pipeline lifecycle."""
        chat_text = self.chat_input_field.text().strip()
        if not chat_text:
            return
           
        print(f"Routing Interaction Chat Prompt: {chat_text}")
        
        # Instantiate the thread worker configuration
        chat_thread = ChatWorker(user_message=chat_text, file_name="output.mp3")
        
        # Connect signals securely back to local UI slot logic methods
        chat_thread.generation_finished.connect(self.on_chat_generation_complete)
        chat_thread.error_occurred.connect(self.on_chat_generation_failed)
        
        # Track thread memory space reference allocations cleanly to avoid GC deletions mid-run
        self.active_chat_workers.append(chat_thread)
        
        # Start execution block
        chat_thread.start()
        
        # Flush fields smoothly
        self.chat_input_field.clear()

    @pyqtSlot(str, str)
    def on_chat_generation_complete(self, dynamic_generated_text, audio_file):
        """Safely updates JavaScript layout layers upon completed asynchronous API responses."""
        # Escape string data structure safely for inline WebEngine injection executions
        escaped_response_text = dynamic_generated_text.replace('"', '\\"').replace('\n', '\\n')
        
        js_code = f"""
            if(typeof chat !== 'undefined'){{
                chat("{escaped_response_text}");
            }}
        """
        self.browser.page().runJavaScript(js_code)
        
        # Perform garbage cleanup processing passes
        sender = self.sender()
        if sender in self.active_chat_workers:
            self.active_chat_workers.remove(sender)

    @pyqtSlot(str)
    def on_chat_generation_failed(self, error_msg):
        """Fallback display tracking when internal API errors manifest."""
        print(f"Asynchronous Generation Layer Fault Triggered: {error_msg}")
        sender = self.sender()
        if sender in self.active_chat_workers:
            self.active_chat_workers.remove(sender)

    @pyqtSlot(QImage)
    def update_video_preview(self, qt_image):
        if self.worker.current_source_type in ["fbx", "tracking"] and not self.video_label.isVisible():
            return
            
        scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
            self.video_label.width(), 
            self.video_label.height(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(scaled_pixmap)

    @pyqtSlot(str)
    def inject_landmarks_to_javascript(self, json_string_data):
        if self.worker.current_source_type == "fbx":
            return
            
        js_code = f"if(typeof window.onPythonTrackingUpdate !== 'undefined'){{ window.onPythonTrackingUpdate({json_string_data}); }}"
        self.browser.page().runJavaScript(js_code)

    def closeEvent(self, event):
        self.worker.running = False
        if self.worker.loop:
            self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
        self.tracking_thread.quit()
        self.tracking_thread.wait()
        
        # Wait for any active chat worker requests before closing
        for thread in self.active_chat_workers:
            thread.quit()
            thread.wait()
            
        super().closeEvent(event)


# =========================================================
# APPLICATION EXECUTION LIFECYCLE INITIALIZER
# =========================================================
if __name__ == "__main__":
    # REQUIRED STRUCTURAL INITIALIZATION FIXES:
    # 1. Force state mapping criteria properties before setup.
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    
    # 2. Fire the application setup matrix sequence.
    app = QApplication(sys.argv)
    
    window = VRMBridgeApp()
    window.show()
    sys.exit(app.exec_())
