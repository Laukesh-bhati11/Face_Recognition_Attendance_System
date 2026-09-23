from flask import Flask, render_template, request, redirect, session, flash, url_for
import cv2
import face_recognition
import numpy as np
import os
from datetime import datetime
import mysql.connector
from db_connection import get_db_connection

app = Flask(__name__)
app.secret_key = "secret123"

# -------------------------------
# CONFIGURATION
# -------------------------------
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# -------------------------------
# HOME PAGE
# -------------------------------
@app.route('/')
def home():
    return render_template('index.html')


# -------------------------------
# DASHBOARD FALLBACK ROUTE
# -------------------------------
@app.route('/dashboard')
def dashboard():
    if 'student_id' in session:
        return redirect(url_for('student_dashboard'))
    elif 'teacher_id' in session:
        return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('home'))


# -------------------------------
# STUDENT SIGNUP
# -------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        roll_no = request.form.get('roll_no', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        image_file = request.files.get('face_image')

        if not name or not roll_no or not email or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for('signup'))

        if not image_file or image_file.filename == '':
            flash("Please upload your face image!", "danger")
            return redirect(url_for('signup'))

        filename = f"{roll_no}_{image_file.filename}"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(image_path)

        try:
            img = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(img)
            if len(encodings) == 0:
                flash("No face detected! Please upload a clear face photo.", "danger")
                if os.path.exists(image_path):
                    os.remove(image_path)
                return redirect(url_for('signup'))

            face_encoding = encodings[0].tobytes()
        except Exception as e:
            flash(f"Error processing face image: {str(e)}", "danger")
            return redirect(url_for('signup'))

        db = get_db_connection()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO students (name, roll_no, email, password, image, face_encoding)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, roll_no, email, password, filename, face_encoding))
            db.commit()
            flash("Signup successful! Please login.", "success")
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f"Database error: {err.msg}", "danger")
            return redirect(url_for('signup'))
        finally:
            cur.close()
            db.close()

    return render_template('signup.html')


# -------------------------------
# STUDENT LOGIN
# -------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        db = get_db_connection()
        cur = db.cursor(dictionary=True)
        try:
            # 1. First check if the user is a teacher
            cur.execute("SELECT * FROM teachers WHERE email=%s AND password=%s", (email, password))
            teacher = cur.fetchone()

            if teacher:
                session['teacher_id'] = teacher['id']
                session['teacher_name'] = teacher['name']
                session['role'] = 'teacher'
                flash("Welcome, Teacher!", "success")
                return redirect(url_for('teacher_dashboard'))

            # 2. If not a teacher, check student table
            cur.execute("SELECT * FROM students WHERE email=%s AND password=%s", (email, password))
            student = cur.fetchone()

            if student:
                session['student_id'] = student['id']
                session['student_name'] = student['name']
                session['role'] = 'student'
                flash("Login successful!", "success")
                return redirect(url_for('student_dashboard'))
            else:
                flash("Invalid email or password!", "danger")
                return redirect(url_for('login'))
        finally:
            cur.close()
            db.close()

    return render_template('student_login.html')


# -------------------------------
# STUDENT DASHBOARD
# -------------------------------
@app.route('/student_dashboard')
def student_dashboard():
    if 'student_id' not in session:
        flash("Unauthorized access! Please login.", "danger")
        return redirect(url_for('login'))
    return render_template('student_dashboard.html', name=session.get('student_name', 'Student'))


# -------------------------------
# STUDENT DETAILS PAGE
# -------------------------------
@app.route('/know_details')
def my_details():
    if 'student_id' not in session:
        flash("Please log in to view your details.", "danger")
        return redirect(url_for('login'))

    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("SELECT name, roll_no, email, section, subjects FROM students WHERE id=%s", (session['student_id'],))
        student = cur.fetchone()
        return render_template('student_details.html', student=student)
    finally:
        cur.close()
        db.close()


# -------------------------------
# SHOW ATTENDANCE (Student)
# -------------------------------
@app.route('/show_attendance')
def show_attendance():
    if 'student_id' not in session:
        flash("Please log in to view attendance.", "danger")
        return redirect(url_for('login'))

    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT date, time, status FROM attendance
            WHERE student_id=%s ORDER BY date DESC, time DESC
        """, (session['student_id'],))
        records = cur.fetchall()
        return render_template('show_attendance.html', records=records)
    finally:
        cur.close()
        db.close()


# -------------------------------
# MARK ATTENDANCE (Face Recognition)
# -------------------------------
@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'student_id' not in session:
        flash("Please log in to mark attendance.", "danger")
        return redirect(url_for('login'))

    # If GET, display the mark attendance camera launch page
    if request.method == 'GET':
        return render_template('mark_attendance.html')

    student_id = session['student_id']
    student_name = session['student_name']

    # Check if attendance already marked today
    today = datetime.now().date()
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("SELECT id FROM attendance WHERE student_id=%s AND date=%s", (student_id, today))
        already_marked = cur.fetchone()
        if already_marked:
            flash("Attendance already marked for today!", "info")
            return redirect(url_for('show_attendance'))

        cur.execute("SELECT face_encoding FROM students WHERE id=%s", (student_id,))
        data = cur.fetchone()
    finally:
        cur.close()
        db.close()

    if not data or not data[0]:
        flash("No face data found for this student. Please contact administrator.", "danger")
        return redirect(url_for('student_dashboard'))

    known_encoding = np.frombuffer(data[0], dtype=np.float64)

    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        flash("Could not access webcam. Please check your camera connection.", "danger")
        return redirect(url_for('mark_attendance'))

    recognized = False
    window_name = "Mark Attendance - Press 'q' to Exit"

    while True:
        ret, frame = cam.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locs = face_recognition.face_locations(rgb)
        face_encs = face_recognition.face_encodings(rgb, face_locs)

        for (top, right, bottom, left), enc in zip(face_locs, face_encs):
            matches = face_recognition.compare_faces([known_encoding], enc)
            if matches[0]:
                recognized = True
                # Modern Cyan/Electric Blue bounding box (BGR: 245, 175, 40)
                cv2.rectangle(frame, (left, top), (right, bottom), (245, 175, 40), 2)
                cv2.putText(frame, f"[VERIFIED: {student_name}]", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (245, 175, 40), 2)
                cv2.imshow(window_name, frame)
                cv2.waitKey(800)

                now = datetime.now()
                time_str = now.strftime("%H:%M:%S")

                db = get_db_connection()
                cur = db.cursor()
                try:
                    cur.execute("""
                        INSERT INTO attendance (student_id, date, time, status)
                        VALUES (%s, %s, %s, %s)
                    """, (student_id, now.date(), time_str, 'Present'))
                    db.commit()
                    flash("Attendance marked successfully!", "success")
                except mysql.connector.Error as err:
                    flash(f"Database error marking attendance: {err.msg}", "danger")
                finally:
                    cur.close()
                    db.close()
                break
            else:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                cv2.putText(frame, "Unknown Face", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)

        cv2.imshow(window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or recognized:
            break
        try:
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
        except Exception:
            pass

    cam.release()
    cv2.destroyAllWindows()

    if not recognized:
        flash("Face not recognized or camera was closed.", "warning")

    return redirect(url_for('show_attendance'))


# -------------------------------
# TEACHER SIGNUP
# -------------------------------
@app.route('/teacher_signup', methods=['GET', 'POST'])
def teacher_signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        subject = request.form.get('subject', '').strip()

        if not name or not email or not password:
            flash("Name, Email, and Password are required!", "danger")
            return redirect(url_for('teacher_signup'))

        db = get_db_connection()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO teachers (name, email, password, subject)
                VALUES (%s, %s, %s, %s)
            """, (name, email, password, subject))
            db.commit()
            flash("Teacher registered successfully! Please login.", "success")
            return redirect(url_for('teacher_login'))
        except mysql.connector.Error as err:
            flash(f"Registration error: {err.msg}", "danger")
            return redirect(url_for('teacher_signup'))
        finally:
            cur.close()
            db.close()

    return render_template('teacher_signup.html')


# -------------------------------
# TEACHER LOGIN
# -------------------------------
@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        db = get_db_connection()
        cur = db.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM teachers WHERE email=%s AND password=%s", (email, password))
            teacher = cur.fetchone()

            if teacher:
                session['teacher_id'] = teacher['id']
                session['teacher_name'] = teacher['name']
                session['role'] = 'teacher'
                flash("Teacher login successful!", "success")
                return redirect(url_for('teacher_dashboard'))
            else:
                flash("Invalid credentials!", "danger")
                return redirect(url_for('teacher_login'))
        finally:
            cur.close()
            db.close()

    return render_template('teacher_login.html')


# -------------------------------
# TEACHER DASHBOARD
# -------------------------------
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'teacher_id' not in session:
        flash("Please login to access teacher dashboard.", "danger")
        return redirect(url_for('teacher_login'))
    return render_template('teacher_dashboard.html', name=session.get('teacher_name', 'Teacher'))


# -------------------------------
# ADD NEW STUDENT (Teacher)
# -------------------------------
@app.route('/register_student', methods=['GET', 'POST'])
def add_student():
    if 'teacher_id' not in session:
        flash("Unauthorized access. Teacher login required.", "danger")
        return redirect(url_for('teacher_login'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        roll_no = request.form.get('roll_no', '').strip()
        section = request.form.get('section', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        if not password:
            password = roll_no

        image_file = request.files.get('image')

        face_encoding = None
        filename = None
        if image_file and image_file.filename != '':
            filename = f"{roll_no}_{image_file.filename}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(image_path)
            try:
                img = face_recognition.load_image_file(image_path)
                encs = face_recognition.face_encodings(img)
                if len(encs) > 0:
                    face_encoding = encs[0].tobytes()
            except Exception as e:
                flash(f"Warning: Could not process face image ({str(e)})", "warning")

        db = get_db_connection()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO students (name, roll_no, section, email, password, image, face_encoding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, roll_no, section, email, password, filename, face_encoding))
            db.commit()
            flash("Student added successfully!", "success")
            return redirect(url_for('teacher_dashboard'))
        except mysql.connector.Error as err:
            flash(f"Database error: {err.msg}", "danger")
            return redirect(url_for('add_student'))
        finally:
            cur.close()
            db.close()

    return render_template('register_student.html')


# -------------------------------
# VIEW ALL STUDENTS (Teacher)
# -------------------------------
@app.route('/view_students', endpoint='view_students')
@app.route('/student', endpoint='students_list')
@app.route('/show_all_students', endpoint='show_all_students')
def view_students():
    if 'teacher_id' not in session:
        flash("Teacher login required to view students.", "danger")
        return redirect(url_for('teacher_login'))

    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, name, roll_no, email, section, subjects FROM students ORDER BY id ASC")
        students = cur.fetchall()
        return render_template('know_details.html', students=students)
    finally:
        cur.close()
        db.close()


# -------------------------------
# MANAGE ATTENDANCE (Teacher)
# -------------------------------
@app.route('/manage_attendance', endpoint='manage_attendance')
@app.route('/show_attendance_all', endpoint='show_attendance_all')
def manage_attendance():
    if 'teacher_id' not in session:
        flash("Teacher login required to view attendance logs.", "danger")
        return redirect(url_for('teacher_login'))

    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT a.id, s.name, s.roll_no, s.section, a.date, a.time, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            ORDER BY a.date DESC, a.time DESC
        """)
        records = cur.fetchall()
        return render_template('manage_attendance.html', records=records)
    finally:
        cur.close()
        db.close()


# -------------------------------
# TEACHER PROFILE
# -------------------------------
@app.route('/teacher_profile', endpoint='teacher_profile')
def teacher_profile():
    if 'teacher_id' not in session:
        flash("Teacher login required.", "danger")
        return redirect(url_for('teacher_login'))

    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT id, name, email, subject, phone, department, qualification, image
            FROM teachers WHERE id=%s
        """, (session['teacher_id'],))
        teacher = cur.fetchone()
        return render_template('teacher_profile.html', teacher=teacher)
    finally:
        cur.close()
        db.close()


# -------------------------------
# LOGOUT
# -------------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for('home'))


# -------------------------------
# RUN APP
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True)

