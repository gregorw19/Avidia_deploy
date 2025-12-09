#!/usr/bin/env python
"""
Quick script to check and reset user profiles for role testing.
Run this with: python manage_role_test.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hatchery.settings')
django.setup()

from django.contrib.auth import get_user_model
from pct.models import Profile

User = get_user_model()

def list_users():
    """List all users and their roles"""
    print("\n=== ALL USERS AND THEIR ROLES ===\n")
    users = User.objects.all()
    if not users:
        print("No users found in database.")
        return
    
    for user in users:
        try:
            profile = Profile.objects.get(user=user)
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"Role: {profile.role}")
            print(f"First Name: {profile.first_name or 'Not set'}")
            print(f"Last Name: {profile.last_name or 'Not set'}")
            print("-" * 40)
        except Profile.DoesNotExist:
            print(f"Username: {user.username} (NO PROFILE)")
            print("-" * 40)

def delete_user(username):
    """Delete a specific user by username"""
    try:
        user = User.objects.get(username=username)
        if hasattr(user, 'profile'):
            user.profile.delete()
            print(f"Deleted profile for {username}")
        user.delete()
        print(f"Deleted user: {username}")
    except User.DoesNotExist:
        print(f"User {username} not found.")

def delete_all_users():
    """Delete all users (use with caution!)"""
    User.objects.all().delete()
    Profile.objects.all().delete()
    print("All users and profiles deleted.")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("ROLE TESTING MANAGER")
    print("="*50)
    
    list_users()
    
    print("\nOptions:")
    print("1. List users again")
    print("2. Delete all users")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        list_users()
    elif choice == "2":
        confirm = input("Are you sure you want to delete ALL users? (yes/no): ")
        if confirm.lower() == "yes":
            delete_all_users()
        else:
            print("Cancelled.")
    else:
        print("Goodbye!")

