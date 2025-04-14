"""
Direct Save Script - A simple script to save form data directly to the database
This script provides a command-line interface to save form data to the database
"""

from app import app, db, UserDetails
import argparse
import json
from datetime import datetime

def save_form_data(user_id, org_id, form_data_json, page=1):
    """Save form data directly to the database"""
    try:
        with app.app_context():
            # Parse the form data JSON
            form_data = json.loads(form_data_json)
            
            # Check if user details already exist
            user_details = UserDetails.query.filter_by(user_id=user_id).first()
            
            if not user_details:
                # Create new user details
                user_details = UserDetails(
                    user_id=user_id,
                    organization_id=org_id,
                    form_data=form_data,
                    last_page=page
                )
                db.session.add(user_details)
                print(f"Created new user details record for user ID: {user_id}")
            else:
                # Update existing user details
                user_details.form_data = form_data
                user_details.last_page = page
                user_details.updated_at = datetime.utcnow()
                print(f"Updated existing user details record for user ID: {user_id}")
            
            db.session.commit()
            print(f"Form data saved successfully for user ID: {user_id}")
            return True
    except Exception as e:
        print(f"Error saving form data: {str(e)}")
        return False

def main():
    """Main function to parse command-line arguments and save form data"""
    parser = argparse.ArgumentParser(description='Save form data directly to the database')
    parser.add_argument('--user_id', type=int, required=True, help='User ID')
    parser.add_argument('--org_id', type=int, required=True, help='Organization ID')
    parser.add_argument('--form_data', type=str, required=True, help='Form data JSON string')
    parser.add_argument('--page', type=int, default=1, help='Current page number')
    
    args = parser.parse_args()
    
    save_form_data(args.user_id, args.org_id, args.form_data, args.page)

if __name__ == "__main__":
    main()
