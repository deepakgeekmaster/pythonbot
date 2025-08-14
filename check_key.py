from database import Database

# Initialize database
db = Database('data')

# Check key validity
key = 'L13MC6OT'
print(f'Is key {key} valid:', db.is_key_valid(key))

# Get key data
key_data = db.get_key(key)
print('Key data:', key_data)

# Check if a user exists and their premium status
user_id = '5791523928'
user = db.get_user(user_id)
if user:
    print(f'User {user_id} exists')
    print('Premium status:', user.get('premium', False))
else:
    print(f'User {user_id} does not exist')