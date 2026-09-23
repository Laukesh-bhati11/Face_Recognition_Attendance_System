import mysql.connector

def get_db_connection():
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        password='Laukesh@2006',
        database='face_attendance'
    )
    return connection
