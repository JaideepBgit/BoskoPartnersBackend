#!/usr/bin/env python3
"""
Database migration script to add missing columns to question_types table.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate_question_types_table():
    """Add missing columns to the question_types table."""
    print("Migrating question_types table to add missing columns...")
    
    try:
        with app.app_context():
            # Get the database connection
            connection = db.engine.raw_connection()
            cursor = connection.cursor()
            
            # Check existing columns first
            cursor.execute("DESCRIBE question_types")
            existing_columns = {row[0] for row in cursor.fetchall()}
            print(f"Existing columns: {existing_columns}")
            
            # List of columns to add with their definitions
            columns_to_add = [
                ("display_name", "VARCHAR(100) NOT NULL DEFAULT ''"),
                ("category", "VARCHAR(50) NOT NULL DEFAULT 'Core Questions'"),
                ("description", "TEXT"),
                ("config_schema", "JSON"),
                ("is_active", "BOOLEAN DEFAULT TRUE"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
            ]
            
            # Add only missing columns
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    statement = f"ALTER TABLE question_types ADD COLUMN {column_name} {column_def}"
                    try:
                        print(f"Executing: {statement}")
                        cursor.execute(statement)
                    except Exception as e:
                        print(f"Error adding column {column_name}: {e}")
                        return False
                else:
                    print(f"Column {column_name} already exists, skipping")
            
            # Commit the changes
            connection.commit()
            cursor.close()
            connection.close()
            
            print("✅ Migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        return False

if __name__ == '__main__':
    success = migrate_question_types_table()
    sys.exit(0 if success else 1) 