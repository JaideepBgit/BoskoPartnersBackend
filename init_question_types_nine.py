#!/usr/bin/env python3
"""
Database initialization script for the nine validated question types.
This script replaces all legacy question types with the validated formats.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, QuestionType

# Nine validated question types data
NINE_QUESTION_TYPES = [
    {
        'id': 1,
        'name': 'short_text',
        'display_name': 'Short Text',
        'category': 'Core Questions',
        'description': 'Brief free-text responses and fill-in-the-blank fields',
        'config_schema': {
            'max_length': 255,
            'placeholder': '',
            'validation': None,  # email, number, url, custom_regex
            'validation_regex': '',
            'required': False
        }
    },
    {
        'id': 2,
        'name': 'single_choice',
        'display_name': 'Single Choice',
        'category': 'Core Questions',
        'description': 'Radio button selection from predefined categorical options',
        'config_schema': {
            'options': [],  # Array of {value, label} objects
            'randomize_options': False,
            'allow_other': False,
            'other_text': 'Other (please specify)',
            'display_type': 'radio',  # radio, dropdown
            'required': False
        }
    },
    {
        'id': 3,
        'name': 'yes_no',
        'display_name': 'Yes/No',
        'category': 'Core Questions',
        'description': 'Binary choice questions for clear decision points',
        'config_schema': {
            'yes_label': 'Yes',
            'no_label': 'No',
            'default_value': None,  # null, 'yes', 'no'
            'required': False
        }
    },
    {
        'id': 4,
        'name': 'likert5',
        'display_name': 'Five-Point Likert Scale',
        'category': 'Core Questions',
        'description': 'Five-point scale from "A great deal" to "None"',
        'config_schema': {
            'scale_labels': {
                1: 'None',
                2: 'A little',
                3: 'A moderate amount',
                4: 'A lot',
                5: 'A great deal'
            },
            'reverse_scale': False,
            'required': False
        }
    },
    {
        'id': 5,
        'name': 'multi_select',
        'display_name': 'Multiple Select',
        'category': 'Core Questions',
        'description': '"Select all that apply" checkbox questions',
        'config_schema': {
            'options': [],  # Array of {value, label} objects
            'randomize_options': False,
            'min_selections': None,
            'max_selections': None,
            'allow_other': False,
            'other_text': 'Other (please specify)',
            'required': False
        }
    },
    {
        'id': 6,
        'name': 'paragraph',
        'display_name': 'Paragraph Text',
        'category': 'Core Questions',
        'description': 'Open-ended narrative and essay responses',
        'config_schema': {
            'min_length': None,
            'max_length': 2000,
            'placeholder': '',
            'character_counter': True,
            'required': False
        }
    },
    {
        'id': 7,
        'name': 'numeric',
        'display_name': 'Numeric Entry',
        'category': 'Core Questions',
        'description': 'Absolute number input with validation',
        'config_schema': {
            'number_type': 'integer',  # integer, decimal
            'min_value': None,
            'max_value': None,
            'decimal_places': 0,
            'unit_label': '',
            'required': False
        }
    },
    {
        'id': 8,
        'name': 'percentage',
        'display_name': 'Percentage Allocation',
        'category': 'Core Questions',
        'description': 'Distribution and allocation percentage questions',
        'config_schema': {
            'items': [],  # Array of {value, label} objects
            'total_percentage': 100,
            'allow_decimals': False,
            'show_running_total': True,
            'required': False
        }
    },
    {
        'id': 9,
        'name': 'year_matrix',
        'display_name': 'Year Matrix',
        'category': 'Core Questions',
        'description': 'Row-by-year grid for temporal data collection',
        'config_schema': {
            'rows': [],  # Array of {value, label} objects
            'start_year': 2024,
            'end_year': 2029,
            'input_type': 'numeric',  # numeric, text, dropdown
            'required': False
        }
    }
]

def initialize_nine_question_types():
    """Initialize the database with the nine validated question types."""
    print("Initializing database with nine validated question types...")
    
    try:
        # Clear existing question types
        QuestionType.query.delete()
        print("Cleared existing question types.")
        
        # Add the nine validated question types
        for qt_data in NINE_QUESTION_TYPES:
            question_type = QuestionType(
                id=qt_data['id'],
                name=qt_data['name'],
                display_name=qt_data['display_name'],
                category=qt_data['category'],
                description=qt_data['description'],
                config_schema=qt_data['config_schema'],
                is_active=True
            )
            db.session.add(question_type)
            print(f"Added question type: {qt_data['display_name']}")
        
        # Commit all changes
        db.session.commit()
        print(f"\nSuccessfully initialized {len(NINE_QUESTION_TYPES)} question types.")
        
        # Verify the data was inserted correctly
        verification_count = QuestionType.query.filter_by(is_active=True).count()
        print(f"Verification: {verification_count} active question types in database.")
        
        if verification_count != len(NINE_QUESTION_TYPES):
            raise Exception(f"Expected {len(NINE_QUESTION_TYPES)} question types, but found {verification_count}")
        
        print("\n✅ Question types initialization completed successfully!")
        
        # Display the question types for confirmation
        print("\nInitialized Question Types:")
        print("-" * 60)
        for qt in QuestionType.query.filter_by(is_active=True).order_by(QuestionType.id).all():
            print(f"{qt.id}. {qt.display_name} ({qt.name})")
            print(f"   Category: {qt.category}")
            print(f"   Description: {qt.description}")
            print()
        
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error initializing question types: {str(e)}")
        return False

if __name__ == '__main__':
    with app.app_context():
        success = initialize_nine_question_types()
    sys.exit(0 if success else 1) 