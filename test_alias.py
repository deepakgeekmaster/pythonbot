import os
import json
from database import Database

# Initialize database
db = Database()

# Generate and print 10 aliases
print("Generating 10 unique aliases:")
for i in range(10):
    alias = db._generate_alias()
    print(f"{i+1}. {alias}")