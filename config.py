import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = 'student_management_system'
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = 'Rushikesh123'  # Change to your MySQL password
    MYSQL_DB = 'student_management'
    MYSQL_CURSORCLASS = 'DictCursor'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)