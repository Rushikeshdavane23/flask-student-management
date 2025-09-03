from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from functools import wraps
import re
import os
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.config.from_object(Config)

# Initialize MySQL
mysql = MySQL(app)

# Ensure the upload directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Teacher required decorator
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'teacher':
            flash('You need teacher privileges to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Student required decorator
def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'student':
            flash('You need to be a student to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if user exists
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT u.*, 
                   COALESCE(s.id, t.id) as profile_id,
                   COALESCE(s.first_name, t.first_name) as first_name,
                   COALESCE(s.last_name, t.last_name) as last_name
            FROM users u 
            LEFT JOIN students s ON u.id = s.user_id 
            LEFT JOIN teachers t ON u.id = t.user_id 
            WHERE u.username = %s
        """, (username,))
        user = cur.fetchone()
        cur.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['profile_id'] = user['profile_id']
            session['first_name'] = user['first_name']
            session['last_name'] = user['last_name']
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

# Register route with role selection
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form['role']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        
        # Validate inputs
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')
        
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address.', 'danger')
            return render_template('register.html')
        
        # Check if username or email already exists
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        existing_user = cur.fetchone()
        
        if existing_user:
            flash('Username or email already exists.', 'danger')
            cur.close()
            return render_template('register.html')
        
        # Create new user
        hashed_password = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (username, email, hashed_password, role)
        )
        user_id = cur.lastrowid
        
        # Create profile based on role
        if role == 'student':
            student_id = 'S' + str(1000 + user_id)
            cur.execute(
                """INSERT INTO students 
                (user_id, student_id, first_name, last_name, email, enrollment_date, major) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (user_id, student_id, first_name, last_name, email, datetime.now().date(), 'Undeclared')
            )
        else:  # teacher
            teacher_id = 'T' + str(1000 + user_id)
            cur.execute(
                """INSERT INTO teachers 
                (user_id, teacher_id, first_name, last_name, email, hire_date, department) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (user_id, teacher_id, first_name, last_name, email, datetime.now().date(), 'General')
            )
        
        mysql.connection.commit()
        cur.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Dashboard route - shows different content based on role
@app.route('/dashboard')
@login_required
def dashboard():
    cur = mysql.connection.cursor()
    
    if session['role'] == 'teacher':
        # Get teacher's courses
        cur.execute("""
            SELECT c.*, COUNT(e.id) as student_count 
            FROM courses c 
            LEFT JOIN enrollments e ON c.id = e.course_id 
            WHERE c.instructor_id = %s 
            GROUP BY c.id
        """, (session['profile_id'],))
        courses = cur.fetchall()
        
        # Get recent enrollments
        cur.execute("""
            SELECT e.*, s.first_name, s.last_name, c.course_name 
            FROM enrollments e 
            JOIN students s ON e.student_id = s.id 
            JOIN courses c ON e.course_id = c.id 
            WHERE c.instructor_id = %s 
            ORDER BY e.created_at DESC 
            LIMIT 5
        """, (session['profile_id'],))
        recent_enrollments = cur.fetchall()
        
        cur.close()
        return render_template('teacher_dashboard.html', 
                              courses=courses, 
                              recent_enrollments=recent_enrollments)
    
    else:  # student
        # Get student's courses
        cur.execute("""
            SELECT c.*, e.grade, e.status 
            FROM courses c 
            JOIN enrollments e ON c.id = e.course_id 
            WHERE e.student_id = %s
        """, (session['profile_id'],))
        courses = cur.fetchall()
        
        # Get upcoming assignments
        cur.execute("""
            SELECT a.*, c.course_name 
            FROM assignments a 
            JOIN courses c ON a.course_id = c.id 
            JOIN enrollments e ON c.id = e.course_id 
            WHERE e.student_id = %s AND a.due_date > NOW() 
            ORDER BY a.due_date 
            LIMIT 5
        """, (session['profile_id'],))
        upcoming_assignments = cur.fetchall()
        
        # Get upcoming quizzes
        cur.execute("""
            SELECT q.*, c.course_name 
            FROM quizzes q 
            JOIN courses c ON q.course_id = c.id 
            JOIN enrollments e ON c.id = e.course_id 
            WHERE e.student_id = %s AND q.due_date > NOW() 
            ORDER BY q.due_date 
            LIMIT 5
        """, (session['profile_id'],))
        upcoming_quizzes = cur.fetchall()
        
        cur.close()
        return render_template('student_dashboard.html', 
                              courses=courses, 
                              upcoming_assignments=upcoming_assignments,
                              upcoming_quizzes=upcoming_quizzes)

# Teacher courses management
@app.route('/teacher/courses')
@login_required
@teacher_required
def teacher_courses():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE instructor_id = %s", (session['profile_id'],))
    courses = cur.fetchall()
    cur.close()
    return render_template('teacher_courses.html', courses=courses)

# Teacher course detail
@app.route('/teacher/course/<int:course_id>')
@login_required
@teacher_required
def teacher_course_detail(course_id):
    cur = mysql.connection.cursor()
    
    # Get course details
    cur.execute("SELECT * FROM courses WHERE id = %s AND instructor_id = %s", (course_id, session['profile_id']))
    course = cur.fetchone()
    
    if not course:
        flash('Course not found or access denied.', 'danger')
        return redirect(url_for('teacher_courses'))
    
    # Get enrolled students
    cur.execute("""
        SELECT s.*, e.grade, e.status 
        FROM students s 
        JOIN enrollments e ON s.id = e.student_id 
        WHERE e.course_id = %s
    """, (course_id,))
    students = cur.fetchall()
    
    # Get course content
    cur.execute("SELECT * FROM course_content WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    content = cur.fetchall()
    
    # Get quizzes
    cur.execute("SELECT * FROM quizzes WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    quizzes = cur.fetchall()
    
    # Get assignments
    cur.execute("SELECT * FROM assignments WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    assignments = cur.fetchall()
    
    cur.close()
    return render_template('teacher_course_detail.html', 
                          course=course, 
                          students=students,
                          content=content,
                          quizzes=quizzes,
                          assignments=assignments)

# Add course route
@app.route('/teacher/add_course', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_course():
    if request.method == 'POST':
        course_code = request.form['course_code']
        course_name = request.form['course_name']
        credits = request.form['credits']
        department = request.form['department']
        description = request.form['description']
        
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """INSERT INTO courses 
                (course_code, course_name, credits, department, instructor_id, description) 
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (course_code, course_name, credits, department, session['profile_id'], description)
            )
            mysql.connection.commit()
            flash('Course added successfully!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding course: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('teacher_courses'))
    
    return render_template('add_course.html')

# Add course content
@app.route('/teacher/course/<int:course_id>/add_content', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_course_content(course_id):
    # Verify the course belongs to the teacher
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE id = %s AND instructor_id = %s", (course_id, session['profile_id']))
    course = cur.fetchone()
    
    if not course:
        flash('Course not found or access denied.', 'danger')
        return redirect(url_for('teacher_courses'))
    
    if request.method == 'POST':
        title = request.form['title']
        content_type = request.form['content_type']
        description = request.form['description']
        
        # Handle file upload
        file_path = None
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filename = f"course_{course_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
        
        try:
            cur.execute(
                """INSERT INTO course_content 
                (course_id, title, content_type, description, file_path) 
                VALUES (%s, %s, %s, %s, %s)""",
                (course_id, title, content_type, description, file_path)
            )
            mysql.connection.commit()
            flash('Content added successfully!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding content: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('teacher_course_detail', course_id=course_id))
    
    return render_template('add_content.html', course=course)

# Create quiz
@app.route('/teacher/course/<int:course_id>/create_quiz', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_quiz(course_id):
    # Verify the course belongs to the teacher
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE id = %s AND instructor_id = %s", (course_id, session['profile_id']))
    course = cur.fetchone()
    
    if not course:
        flash('Course not found or access denied.', 'danger')
        return redirect(url_for('teacher_courses'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        time_limit = request.form['time_limit']
        total_marks = request.form['total_marks']
        due_date = request.form['due_date']
        
        try:
            cur.execute(
                """INSERT INTO quizzes 
                (course_id, title, description, time_limit, total_marks, due_date) 
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (course_id, title, description, time_limit, total_marks, due_date)
            )
            quiz_id = cur.lastrowid
            
            # Add questions
            question_count = int(request.form['question_count'])
            for i in range(1, question_count + 1):
                question_text = request.form[f'question_{i}_text']
                question_type = request.form[f'question_{i}_type']
                marks = request.form[f'question_{i}_marks']
                correct_answer = request.form[f'question_{i}_correct_answer']
                
                options = None
                if question_type == 'multiple_choice':
                    options_json = {}
                    option_letters = ['A', 'B', 'C', 'D']
                    for letter in option_letters:
                        option_value = request.form.get(f'question_{i}_option_{letter}')
                        if option_value:
                            options_json[letter] = option_value
                    options = json.dumps(options_json) if options_json else None
                
                cur.execute(
                    """INSERT INTO quiz_questions 
                    (quiz_id, question_text, question_type, options, correct_answer, marks) 
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (quiz_id, question_text, question_type, options, correct_answer, marks)
                )
            
            mysql.connection.commit()
            flash('Quiz created successfully!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error creating quiz: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('teacher_course_detail', course_id=course_id))
    
    return render_template('create_quiz.html', course=course)

# Student courses view
@app.route('/student/courses')
@login_required
@student_required
def student_courses():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.*, e.grade, e.status 
        FROM courses c 
        JOIN enrollments e ON c.id = e.course_id 
        WHERE e.student_id = %s
    """, (session['profile_id'],))
    courses = cur.fetchall()
    cur.close()
    return render_template('student_courses.html', courses=courses)

# Student course detail
@app.route('/student/course/<int:course_id>')
@login_required
@student_required
def student_course_detail(course_id):
    cur = mysql.connection.cursor()
    
    # Verify the student is enrolled in the course
    cur.execute("""
        SELECT c.*, e.grade, e.status 
        FROM courses c 
        JOIN enrollments e ON c.id = e.course_id 
        WHERE e.student_id = %s AND c.id = %s
    """, (session['profile_id'], course_id))
    course = cur.fetchone()
    
    if not course:
        flash('Course not found or access denied.', 'danger')
        return redirect(url_for('student_courses'))
    
    # Get course content
    cur.execute("SELECT * FROM course_content WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    content = cur.fetchall()
    
    # Get quizzes
    cur.execute("SELECT * FROM quizzes WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    quizzes = cur.fetchall()
    
    # Get assignments
    cur.execute("SELECT * FROM assignments WHERE course_id = %s ORDER BY created_at DESC", (course_id,))
    assignments = cur.fetchall()
    
    # Check student's quiz attempts
    quiz_attempts = {}
    for quiz in quizzes:
        cur.execute("""
            SELECT * FROM quiz_attempts 
            WHERE quiz_id = %s AND student_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (quiz['id'], session['profile_id']))
        attempt = cur.fetchone()
        quiz_attempts[quiz['id']] = attempt
    
    # Check student's assignment submissions
    assignment_submissions = {}
    for assignment in assignments:
        cur.execute("""
            SELECT * FROM student_assignments 
            WHERE assignment_id = %s AND student_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (assignment['id'], session['profile_id']))
        submission = cur.fetchone()
        assignment_submissions[assignment['id']] = submission
    
    cur.close()
    return render_template('student_course_detail.html', 
                          course=course, 
                          content=content,
                          quizzes=quizzes,
                          assignments=assignments,
                          quiz_attempts=quiz_attempts,
                          assignment_submissions=assignment_submissions)

# Take quiz
@app.route('/student/quiz/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
@student_required
def take_quiz(quiz_id):
    cur = mysql.connection.cursor()
    
    # Get quiz details
    cur.execute("""
        SELECT q.*, c.course_name 
        FROM quizzes q 
        JOIN courses c ON q.course_id = c.id 
        JOIN enrollments e ON c.id = e.course_id 
        WHERE q.id = %s AND e.student_id = %s
    """, (quiz_id, session['profile_id']))
    quiz = cur.fetchone()
    
    if not quiz:
        flash('Quiz not found or access denied.', 'danger')
        return redirect(url_for('student_courses'))
    
    # Check if student has already taken this quiz
    cur.execute("""
        SELECT * FROM quiz_attempts 
        WHERE quiz_id = %s AND student_id = %s AND status != 'in_progress'
    """, (quiz_id, session['profile_id']))
    existing_attempt = cur.fetchone()
    
    if existing_attempt and existing_attempt['status'] == 'submitted':
        flash('You have already submitted this quiz.', 'info')
        return redirect(url_for('student_course_detail', course_id=quiz['course_id']))
    
    # Start new attempt or resume existing one
    if not existing_attempt:
        cur.execute(
            """INSERT INTO quiz_attempts 
            (quiz_id, student_id, start_time, status) 
            VALUES (%s, %s, %s, %s)""",
            (quiz_id, session['profile_id'], datetime.now(), 'in_progress')
        )
        attempt_id = cur.lastrowid
        mysql.connection.commit()
    else:
        attempt_id = existing_attempt['id']
    
    # Get quiz questions
    cur.execute("SELECT * FROM quiz_questions WHERE quiz_id = %s ORDER BY id", (quiz_id,))
    questions = cur.fetchall()
    
    # Process quiz submission
    if request.method == 'POST':
        score = 0
        for question in questions:
            answer = request.form.get(f'question_{question["id"]}')
            
            # Check if answer is correct
            is_correct = False
            if question['question_type'] == 'multiple_choice':
                is_correct = (answer == question['correct_answer'])
            elif question['question_type'] == 'true_false':
                is_correct = (answer == question['correct_answer'])
            else:  # short answer (case-insensitive partial match)
                is_correct = (answer and answer.lower() in question['correct_answer'].lower())
            
            if is_correct:
                score += question['marks']
            
            # Save student answer
            cur.execute(
                """INSERT INTO student_answers 
                (attempt_id, question_id, answer, is_correct) 
                VALUES (%s, %s, %s, %s)""",
                (attempt_id, question['id'], answer, is_correct)
            )
        
        # Update attempt with score and end time
        cur.execute(
            """UPDATE quiz_attempts 
            SET end_time = %s, score = %s, status = 'submitted' 
            WHERE id = %s""",
            (datetime.now(), score, attempt_id)
        )
        mysql.connection.commit()
        cur.close()
        
        flash('Quiz submitted successfully!', 'success')
        return redirect(url_for('student_course_detail', course_id=quiz['course_id']))
    
    cur.close()
    return render_template('take_quiz.html', quiz=quiz, questions=questions, attempt_id=attempt_id)

# Teacher students management
@app.route('/teacher/students')
@login_required
@teacher_required
def teacher_students():
    cur = mysql.connection.cursor()
    
    # Get all students
    cur.execute("""
        SELECT s.*, COUNT(e.id) as enrollment_count,
               CASE WHEN COUNT(e.id) > 0 THEN 'active' ELSE 'inactive' END as status
        FROM students s 
        LEFT JOIN enrollments e ON s.id = e.student_id 
        GROUP BY s.id
    """)
    students = cur.fetchall()
    
    # Get enrollments for each student
    for student in students:
        cur.execute("""
            SELECT c.course_code 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.id 
            WHERE e.student_id = %s
        """, (student['id'],))
        enrollments = cur.fetchall()
        student['enrollments'] = enrollments
    
    # Get teacher's courses for enrollment
    cur.execute("SELECT * FROM courses WHERE instructor_id = %s", (session['profile_id'],))
    courses = cur.fetchall()
    
    cur.close()
    return render_template('teacher_students.html', students=students, courses=courses)

# Teacher schedule management
@app.route('/teacher/schedule')
@login_required
@teacher_required
def teacher_schedule():
    cur = mysql.connection.cursor()
    
    # Get teacher's courses
    cur.execute("SELECT * FROM courses WHERE instructor_id = %s", (session['profile_id'],))
    courses = cur.fetchall()
    
    # Get existing schedules
    cur.execute("""
        SELECT s.*, c.course_code 
        FROM schedules s 
        JOIN courses c ON s.course_id = c.id 
        WHERE c.instructor_id = %s 
        ORDER BY s.day, s.time_slot
    """, (session['profile_id'],))
    schedules = cur.fetchall()
    
    cur.close()
    
    # Define time slots
    time_slots = [
        '8:00-9:00', '9:00-10:00', '10:00-11:00', '11:00-12:00',
        '12:00-13:00', '13:00-14:00', '14:00-15:00', '15:00-16:00',
        '16:00-17:00', '17:00-18:00'
    ]
    
    # Get current week
    today = datetime.now()
    current_week = f"Week {today.isocalendar()[1]}, {today.year}"
    
    return render_template('teacher_schedule.html', 
                         courses=courses, 
                         schedules=schedules,
                         time_slots=time_slots,
                         current_week=current_week)

# Add student to course
@app.route('/teacher/enroll_student', methods=['POST'])
@login_required
@teacher_required
def enroll_student():
    student_id = request.form['student_id']
    course_id = request.form['course_id']
    enrollment_date = request.form['enrollment_date']
    
    cur = mysql.connection.cursor()
    
    try:
        # Check if already enrolled
        cur.execute("SELECT * FROM enrollments WHERE student_id = %s AND course_id = %s", 
                   (student_id, course_id))
        if cur.fetchone():
            flash('Student is already enrolled in this course.', 'warning')
            return redirect(url_for('teacher_students'))
        
        # Enroll student
        cur.execute(
            "INSERT INTO enrollments (student_id, course_id, enrollment_date) VALUES (%s, %s, %s)",
            (student_id, course_id, enrollment_date)
        )
        mysql.connection.commit()
        flash('Student enrolled successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error enrolling student: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('teacher_students'))

# Add schedule
@app.route('/teacher/add_schedule', methods=['POST'])
@login_required
@teacher_required
def add_schedule():
    course_id = request.form['course_id']
    day = request.form['day']
    time_slot = request.form['time_slot']
    room = request.form['room']
    duration = request.form['duration']
    
    cur = mysql.connection.cursor()
    
    try:
        # Check for schedule conflicts
        cur.execute("""
            SELECT * FROM schedules 
            WHERE day = %s AND time_slot = %s AND room = %s
        """, (day, time_slot, room))
        
        if cur.fetchone():
            flash('Schedule conflict! This room is already booked at this time.', 'danger')
            return redirect(url_for('teacher_schedule'))
        
        # Add schedule
        cur.execute(
            """INSERT INTO schedules (course_id, day, time_slot, room, duration) 
            VALUES (%s, %s, %s, %s, %s)""",
            (course_id, day, time_slot, room, duration)
        )
        mysql.connection.commit()
        flash('Schedule added successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error adding schedule: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('teacher_schedule'))

# Update schedule
@app.route('/teacher/update_schedule', methods=['POST'])
@login_required
@teacher_required
def update_schedule():
    schedule_id = request.form['schedule_id']
    course_id = request.form['course_id']
    day = request.form['day']
    time_slot = request.form['time_slot']
    room = request.form['room']
    duration = request.form['duration']
    
    cur = mysql.connection.cursor()
    
    try:
        # Check for schedule conflicts (excluding current schedule)
        cur.execute("""
            SELECT * FROM schedules 
            WHERE day = %s AND time_slot = %s AND room = %s AND id != %s
        """, (day, time_slot, room, schedule_id))
        
        if cur.fetchone():
            flash('Schedule conflict! This room is already booked at this time.', 'danger')
            return redirect(url_for('teacher_schedule'))
        
        # Update schedule
        cur.execute(
            """UPDATE schedules 
            SET course_id = %s, day = %s, time_slot = %s, room = %s, duration = %s 
            WHERE id = %s""",
            (course_id, day, time_slot, room, duration, schedule_id)
        )
        mysql.connection.commit()
        flash('Schedule updated successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error updating schedule: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('teacher_schedule'))

# Delete schedule
@app.route('/teacher/delete_schedule/<int:schedule_id>')
@login_required
@teacher_required
def delete_schedule(schedule_id):
    cur = mysql.connection.cursor()
    
    try:
        # Verify the schedule belongs to the teacher's course
        cur.execute("""
            SELECT s.* FROM schedules s 
            JOIN courses c ON s.course_id = c.id 
            WHERE s.id = %s AND c.instructor_id = %s
        """, (schedule_id, session['profile_id']))
        
        if not cur.fetchone():
            flash('Schedule not found or access denied.', 'danger')
            return redirect(url_for('teacher_schedule'))
        
        # Delete schedule
        cur.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
        mysql.connection.commit()
        flash('Schedule deleted successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting schedule: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('teacher_schedule'))

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)