import bcrypt

password = "password123"
hashed   = "$2b$12$sCiR6FJ/g1tYcBoEe7lAtuUTSR4O18luk1MwVbeRpu9YIf4e6UAhq"

if bcrypt.checkpw(password.encode(), hashed.encode()):
    print("✅ Match! The hash is correct.")
else:
    print("❌ No match.")