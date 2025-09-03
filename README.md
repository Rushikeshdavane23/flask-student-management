Student Management System
A Flask-based web application for educational institutions with role-based authentication for teachers and students.

Features
👨‍🏫 Teacher Features
Course creation and management

Student enrollment and management

Quiz and assignment creation

Class scheduling with conflict detection

Grade tracking and progress monitoring

👨‍🎓 Student Features
Course enrollment and access

Quiz taking and assignment submission

Progress tracking and grade viewing

Course material access

Tech Stack
Backend: Flask (Python)

Database: MySQL

Frontend: Bootstrap 5, JavaScript

Authentication: Session-based with password hashing

Quick Setup
Clone and install:

bash
git clone <repository-url>
cd flask-student-management
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
Database setup:

bash
mysql -u root -p < database/schema.sql
mysql -u root -p < database/sample_data.sql
Configure config.py with your MySQL credentials

Run the application:

bash
python app.py
Access: http://localhost:5000
