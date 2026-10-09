import os

USERNAME = 'user'
PASSWORD = 'pass'


def insert_default_user(connection, password_hash):
    """Create the initial account only when the users table is empty."""
    if not connection.execute('SELECT 1 FROM users').fetchone():
        connection.execute(
            'INSERT INTO users(username,password) VALUES(?,?)',
            (USERNAME, password_hash(os.environ.get('INITIAL_PASSWORD', PASSWORD))),
        )
