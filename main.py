import cv2
import streamlit as st
import csv
from utils.camera import Camera
from utils.detection import Detection
import sqlite3
import datetime
import time
import uuid  # Import the uuid module for generating unique identifiers
import random

class ExamProctor:
    def __init__(self):
        self.camera = Camera()
        self.detector = Detection()
        self.is_running = False
        self.session_id = None
        self.exam_duration = 30 * 60  # 30 minutes in seconds
        self.start_time = None
        self.violation_count = 0
        self.last_message_time = 0
        self.consecutive_multiple_faces = 0  # Counter for multiple persons
        self.consecutive_no_face = 0  # Counter for no face detected
        
        # Enhanced CSS styling with more prominent colors
        st.markdown("""
            <style>
            .normal-bg {
                background-color: #e7f3e7 !important;
                padding: 10px;
                border-radius: 5px;
                border: 2px solid #28a745;
                color: #1b5e20;
                font-weight: bold;
                margin: 10px 0;
            }
            .warning-bg {
                background-color: #fff3cd !important;
                padding: 10px;
                border-radius: 5px;
                border: 2px solid #ffc107;
                color: #856404;
                font-weight: bold;
                margin: 10px 0;
            }
            .danger-bg {
                background-color: #f8d7da !important;
                padding: 10px;
                border-radius: 5px;
                border: 2px solid #dc3545;
                color: #721c24;
                font-weight: bold;
                margin: 10px 0;
            }
            .status-message {
                font-size: 18px;
                text-align: center;
                margin: 10px 0;
            }
            .violation-warning {
                background-color: #ffe0b2;
                padding: 8px;
                border-radius: 4px;
                border-left: 4px solid #ff9800;
                margin: 5px 0;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # Initialize Streamlit placeholders
        self.status_label = st.empty()  # Placeholder for status
        self.timer_label = st.empty()  # Placeholder for timer
        self.progress_bar = st.empty()
        self.message_placeholder = st.empty()
        self.violation_label = st.empty()  # Placeholder for violations
        self.video_placeholder = st.empty()  # Placeholder for video feed
        self.bg_container = st.empty()  # New container for background updates

        # CSV file setup
        self.csv_file = "violations_log.csv"
        self.create_csv_file()

    def create_csv_file(self):
        """Create a CSV file to log violations."""
        with open(self.csv_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Violation Type", "Session ID"])  # Header row

    def log_violation(self, violation):
        """Log a violation to the CSV file."""
        with open(self.csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([datetime.datetime.now(), violation, self.session_id])  # Log the violation

    def start_exam(self):
        self.is_running = True
        self.session_id = self.create_session()
        self.start_time = time.time()
        self.status_label.text("Status: Exam in Progress")
        self.run_proctoring()

    def create_session(self):
        conn = sqlite3.connect('proctor.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO sessions (start_time, total_violations) VALUES (?, 0)''', (datetime.datetime.now(),))
        conn.commit()
        return cursor.lastrowid

    def update_ui_style(self):
        """Update UI style based on violation count"""
        if self.violation_count == 0:
            self.bg_container.markdown(
                '<div class="normal-bg status-message">✅ Status: Normal - Exam Proceeding Well</div>', 
                unsafe_allow_html=True
            )
        elif self.violation_count <= 2:
            self.bg_container.markdown(
                f'<div class="warning-bg status-message">⚠️ Warning: {self.violation_count} violation(s) detected!</div>', 
                unsafe_allow_html=True
            )
        else:
            self.bg_container.markdown(
                '<div class="danger-bg status-message">🚫 Critical: Maximum violations reached!</div>', 
                unsafe_allow_html=True
            )

    def run_proctoring(self):
        if st.button("Stop Exam", key=f"stop_exam_button_{self.session_id}"):
            self.stop_exam()
            self.status_label.text("Status: Exam Ended")
            return

        while self.is_running:
            # Check time remaining
            elapsed_time = time.time() - self.start_time
            remaining_time = max(0, self.exam_duration - elapsed_time)
            
            # Format remaining time as MM:SS
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            self.timer_label.text(f"Time Remaining: {minutes:02d}:{seconds:02d}")
            
            # Stop exam if time is up
            if remaining_time <= 0:
                st.warning("Time's up! Exam ended.")
                self.stop_exam()
                self.status_label.text("Status: Exam Ended - Time's Up")
                return

            frame = self.camera.read_frame()
            violations = self.detector.detect_violations(frame)
            
            # Check for multiple persons with enhanced warning display
            if "Multiple persons detected" in violations:
                self.consecutive_multiple_faces += 1
                st.markdown(
                    f'<div class="violation-warning">⚠️ Warning: Multiple persons detected! ({self.consecutive_multiple_faces}/3)</div>',
                    unsafe_allow_html=True
                )
                
                if self.consecutive_multiple_faces >= 3:
                    st.markdown(
                        '<div class="danger-bg">🚫 Multiple persons detected too many times. Exam automatically terminated.</div>',
                        unsafe_allow_html=True
                    )
                    self.log_violation("Multiple persons detected - Auto terminated")
                    self.stop_exam()
                    self.status_label.markdown(
                        '<div class="danger-bg status-message">❌ Status: Exam Terminated - Multiple Persons Detected</div>',
                        unsafe_allow_html=True
                    )
                    return

            # Check for no face detected with enhanced warning display
            if "No face detected" in violations:
                self.consecutive_no_face += 1
                st.markdown(
                    f'<div class="violation-warning">⚠️ Warning: Student not visible in camera! ({self.consecutive_no_face}/3)</div>',
                    unsafe_allow_html=True
                )
                
                if self.consecutive_no_face >= 3:
                    st.markdown(
                        '<div class="danger-bg">🚫 Student not visible for too long. Exam automatically terminated.</div>',
                        unsafe_allow_html=True
                    )
                    self.log_violation("Student not visible - Auto terminated")
                    self.stop_exam()
                    self.status_label.markdown(
                        '<div class="danger-bg status-message">❌ Status: Exam Terminated - Student Not Visible</div>',
                        unsafe_allow_html=True
                    )
                    return

            # Handle other violations
            if violations:
                for violation in violations:
                    if violation not in ["Multiple persons detected", "No face detected"]:
                        st.warning(f"Violation Detected: {violation} at {datetime.datetime.now()}")
                        self.log_violation(violation)
                
                # Update UI style
                self.update_ui_style()

            # Update video feed
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)
            
            time.sleep(0.03)

    def stop_exam(self):
        self.is_running = False
        self.camera.release()
        self.video_placeholder.empty()  # Clear the video feed

def main():
    st.title("Online Exam Proctoring System")
    
    if 'camera_started' not in st.session_state:
        st.session_state.camera_started = False

    if st.button("Start Exam", key="start_exam_button"):
        st.session_state.camera_started = True
        proctor = ExamProctor()
        proctor.start_exam()

if __name__ == "__main__":
    main()