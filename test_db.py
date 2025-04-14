from app import app, db, Organization, User, UserDetails
import json
from datetime import datetime
from sqlalchemy import text

# Test script to verify database connectivity and insert test data

def test_database_connection():
    """Test basic database connectivity"""
    try:
        with app.app_context():
            # Test connection
            result = db.session.execute(text("SELECT 1")).fetchone()
            print(f"Database connection test: {result[0] == 1}")
            return result[0] == 1
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        return False

def create_test_data():
    """Create test organization and user"""
    try:
        with app.app_context():
            # Check if test organization exists
            test_org = Organization.query.filter_by(name="Test Organization").first()
            if not test_org:
                test_org = Organization(name="Test Organization", type="other")
                db.session.add(test_org)
                db.session.commit()
                print(f"Created test organization with ID: {test_org.id}")
            else:
                print(f"Test organization already exists with ID: {test_org.id}")
            
            # Check if test user exists
            test_user = User.query.filter_by(username="testuser").first()
            if not test_user:
                test_user = User(
                    username="testuser",
                    email="test@example.com",
                    password="password",
                    role="user",
                    organization_id=test_org.id,
                    firstname="Test",
                    lastname="User"
                )
                db.session.add(test_user)
                db.session.commit()
                print(f"Created test user with ID: {test_user.id}")
            else:
                print(f"Test user already exists with ID: {test_user.id}")
                
            return {
                "org_id": test_org.id,
                "user_id": test_user.id if test_user else None
            }
    except Exception as e:
        print(f"Error creating test data: {str(e)}")
        return None

def save_form_data(user_id, org_id):
    """Test saving form data"""
    try:
        with app.app_context():
            # Create sample form data
            form_data = {
                "personal": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john.doe@example.com",
                    "phone": "123-456-7890"
                },
                "organizational": {
                    "country": "United States",
                    "region": "West",
                    "church": "Example Church",
                    "school": "Example School"
                }
            }
            
            # Check if user details already exist
            user_details = UserDetails.query.filter_by(user_id=user_id).first()
            
            if not user_details:
                # Create new user details
                user_details = UserDetails(
                    user_id=user_id,
                    organization_id=org_id,
                    form_data=form_data,
                    last_page=1
                )
                db.session.add(user_details)
            else:
                # Update existing user details
                user_details.form_data = form_data
                user_details.updated_at = datetime.utcnow()
            
            db.session.commit()
            print(f"Form data saved for user ID: {user_id}")
            
            # Verify data was saved
            saved_details = UserDetails.query.filter_by(user_id=user_id).first()
            if saved_details:
                print(f"Verified saved data: {saved_details.form_data}")
                return True
            return False
    except Exception as e:
        print(f"Error saving form data: {str(e)}")
        return False

def retrieve_form_data(user_id):
    """Test retrieving form data"""
    try:
        with app.app_context():
            user_details = UserDetails.query.filter_by(user_id=user_id).first()
            if user_details:
                print(f"Retrieved form data for user ID {user_id}: {user_details.form_data}")
                return user_details.form_data
            else:
                print(f"No form data found for user ID: {user_id}")
                return None
    except Exception as e:
        print(f"Error retrieving form data: {str(e)}")
        return None

if __name__ == "__main__":
    print("Testing database connection...")
    if test_database_connection():
        print("Database connection successful!")
        
        print("\nCreating test data...")
        test_data = create_test_data()
        if test_data:
            user_id = test_data["user_id"]
            org_id = test_data["org_id"]
            
            print(f"\nSaving form data for user ID: {user_id}, org ID: {org_id}")
            if save_form_data(user_id, org_id):
                print("Form data saved successfully!")
                
                print("\nRetrieving form data...")
                form_data = retrieve_form_data(user_id)
                if form_data:
                    print("Form data retrieved successfully!")
                else:
                    print("Failed to retrieve form data.")
            else:
                print("Failed to save form data.")
        else:
            print("Failed to create test data.")
    else:
        print("Database connection failed!")
