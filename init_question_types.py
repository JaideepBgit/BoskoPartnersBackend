#!/usr/bin/env python3
"""
Script to initialize the database with question types based on Qualtrics structure.
Run this script to populate the question_types table with all the new question types.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, QuestionType

# Question types data based on the frontend configuration
QUESTION_TYPES_DATA = [
    # Standard Content Questions
    {
        'id': 1,
        'name': 'text_graphic',
        'display_name': 'Text / Graphic',
        'category': 'Standard Content',
        'description': 'Display text, images, or other media content',
        'config_schema': {
            'content_type': 'text',
            'content': '',
            'alignment': 'left'
        }
    },
    {
        'id': 2,
        'name': 'multiple_choice',
        'display_name': 'Multiple Choice',
        'category': 'Standard Content',
        'description': 'Single or multiple selection from predefined options',
        'config_schema': {
            'selection_type': 'single',
            'options': [],
            'randomize_options': False,
            'allow_other': False,
            'other_text': 'Other (please specify)'
        }
    },
    {
        'id': 3,
        'name': 'matrix_table',
        'display_name': 'Matrix Table',
        'category': 'Standard Content',
        'description': 'Grid of questions with same answer choices',
        'config_schema': {
            'statements': [],
            'scale_points': [],
            'force_response': False,
            'randomize_statements': False
        }
    },
    {
        'id': 4,
        'name': 'text_entry',
        'display_name': 'Text Entry',
        'category': 'Standard Content',
        'description': 'Open-ended text responses',
        'config_schema': {
            'input_type': 'single_line',
            'validation': None,
            'max_length': None,
            'placeholder': ''
        }
    },
    {
        'id': 5,
        'name': 'form_field',
        'display_name': 'Form Field',
        'category': 'Standard Content',
        'description': 'Structured form inputs (name, address, etc.)',
        'config_schema': {
            'field_type': 'name',
            'required_fields': [],
            'format': 'standard'
        }
    },
    {
        'id': 6,
        'name': 'slider',
        'display_name': 'Slider',
        'category': 'Standard Content',
        'description': 'Numeric input using a slider interface',
        'config_schema': {
            'min_value': 0,
            'max_value': 100,
            'step': 1,
            'default_value': None,
            'labels': {
                'min_label': '',
                'max_label': ''
            }
        }
    },
    {
        'id': 7,
        'name': 'rank_order',
        'display_name': 'Rank Order',
        'category': 'Standard Content',
        'description': 'Drag and drop ranking of items',
        'config_schema': {
            'items': [],
            'force_ranking': True,
            'randomize_items': False
        }
    },
    {
        'id': 8,
        'name': 'side_by_side',
        'display_name': 'Side by Side',
        'category': 'Standard Content',
        'description': 'Multiple questions displayed horizontally',
        'config_schema': {
            'questions': [],
            'layout': 'equal_width'
        }
    },
    {
        'id': 9,
        'name': 'autocomplete',
        'display_name': 'Autocomplete',
        'category': 'Standard Content',
        'description': 'Text input with autocomplete suggestions',
        'config_schema': {
            'suggestions': [],
            'allow_custom': True,
            'max_suggestions': 10
        }
    },

    # Specialty Questions
    {
        'id': 10,
        'name': 'constant_sum',
        'display_name': 'Constant Sum',
        'category': 'Specialty Questions',
        'description': 'Numeric entries that sum to a specific total',
        'config_schema': {
            'items': [],
            'total_sum': 100,
            'allow_decimals': False
        }
    },
    {
        'id': 11,
        'name': 'pick_group_rank',
        'display_name': 'Pick, Group & Rank',
        'category': 'Specialty Questions',
        'description': 'Select, categorize, and rank items',
        'config_schema': {
            'items': [],
            'groups': [],
            'max_picks': None,
            'require_ranking': True
        }
    },
    {
        'id': 12,
        'name': 'hot_spot',
        'display_name': 'Hot Spot',
        'category': 'Specialty Questions',
        'description': 'Click on areas of an image',
        'config_schema': {
            'image_url': '',
            'hot_spots': [],
            'max_selections': None
        }
    },
    {
        'id': 13,
        'name': 'heat_map',
        'display_name': 'Heat Map',
        'category': 'Specialty Questions',
        'description': 'Visual heat map responses on images',
        'config_schema': {
            'image_url': '',
            'heat_intensity': 'medium'
        }
    },
    {
        'id': 14,
        'name': 'graphic_slider',
        'display_name': 'Graphic Slider',
        'category': 'Specialty Questions',
        'description': 'Slider with custom graphics',
        'config_schema': {
            'min_value': 0,
            'max_value': 100,
            'step': 1,
            'graphic_type': 'emoji',
            'graphics': []
        }
    },
    {
        'id': 15,
        'name': 'drill_down',
        'display_name': 'Drill Down',
        'category': 'Specialty Questions',
        'description': 'Hierarchical selection (country > state > city)',
        'config_schema': {
            'levels': [],
            'data_source': 'custom'
        }
    },
    {
        'id': 16,
        'name': 'net_promoter_score',
        'display_name': 'Net Promoter Score',
        'category': 'Specialty Questions',
        'description': 'Standard NPS question (0-10 scale)',
        'config_schema': {
            'scale_labels': {
                'low': 'Not at all likely',
                'high': 'Extremely likely'
            },
            'follow_up_enabled': True
        }
    },
    {
        'id': 17,
        'name': 'highlight',
        'display_name': 'Highlight',
        'category': 'Specialty Questions',
        'description': 'Highlight text passages',
        'config_schema': {
            'text_content': '',
            'highlight_color': '#ffff00',
            'max_highlights': None
        }
    },
    {
        'id': 18,
        'name': 'signature',
        'display_name': 'Signature',
        'category': 'Specialty Questions',
        'description': 'Digital signature capture',
        'config_schema': {
            'canvas_width': 400,
            'canvas_height': 200,
            'pen_color': '#000000'
        }
    },
    {
        'id': 19,
        'name': 'video_response',
        'display_name': 'Video Response',
        'category': 'Specialty Questions',
        'description': 'Record video responses',
        'config_schema': {
            'max_duration': 300,
            'allow_retake': True,
            'quality': 'standard'
        }
    },
    {
        'id': 20,
        'name': 'user_testing',
        'display_name': 'User Testing',
        'category': 'Specialty Questions',
        'description': 'Unmoderated user testing tasks',
        'config_schema': {
            'task_description': '',
            'target_url': '',
            'success_criteria': []
        }
    },
    {
        'id': 21,
        'name': 'tree_testing',
        'display_name': 'Tree Testing',
        'category': 'Specialty Questions',
        'description': 'Information architecture testing',
        'config_schema': {
            'tree_structure': {},
            'task_description': '',
            'success_path': []
        }
    },

    # Advanced Questions
    {
        'id': 22,
        'name': 'timing',
        'display_name': 'Timing',
        'category': 'Advanced Questions',
        'description': 'Measure response time',
        'config_schema': {
            'timing_type': 'page_submit',
            'visible_to_respondent': False
        }
    },
    {
        'id': 23,
        'name': 'meta_info',
        'display_name': 'Meta Info',
        'category': 'Advanced Questions',
        'description': 'Capture browser/device information',
        'config_schema': {
            'capture_browser': True,
            'capture_os': True,
            'capture_device': True,
            'capture_location': False
        }
    },
    {
        'id': 24,
        'name': 'file_upload',
        'display_name': 'File Upload',
        'category': 'Advanced Questions',
        'description': 'Upload files or documents',
        'config_schema': {
            'allowed_types': ['pdf', 'doc', 'docx', 'jpg', 'png'],
            'max_file_size': 10,
            'max_files': 1
        }
    },
    {
        'id': 25,
        'name': 'captcha',
        'display_name': 'Captcha Verification',
        'category': 'Advanced Questions',
        'description': 'Bot prevention verification',
        'config_schema': {
            'captcha_type': 'recaptcha',
            'difficulty': 'medium'
        }
    },
    {
        'id': 26,
        'name': 'location_selector',
        'display_name': 'Location Selector',
        'category': 'Advanced Questions',
        'description': 'Geographic location selection',
        'config_schema': {
            'map_type': 'google',
            'default_zoom': 10,
            'allow_coordinates': True
        }
    },
    {
        'id': 27,
        'name': 'arcgis_map',
        'display_name': 'ArcGIS Map',
        'category': 'Advanced Questions',
        'description': 'Advanced mapping with ArcGIS',
        'config_schema': {
            'map_service_url': '',
            'layers': [],
            'tools_enabled': ['zoom', 'pan', 'measure']
        }
    }
]

def init_question_types():
    """Initialize the database with question types."""
    with app.app_context():
        print("Initializing question types...")
        
        # Clear existing question types
        QuestionType.query.delete()
        
        # Add new question types
        for qt_data in QUESTION_TYPES_DATA:
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
        
        try:
            db.session.commit()
            print(f"Successfully initialized {len(QUESTION_TYPES_DATA)} question types!")
            
            # Print summary by category
            categories = {}
            for qt in QUESTION_TYPES_DATA:
                cat = qt['category']
                if cat not in categories:
                    categories[cat] = 0
                categories[cat] += 1
            
            print("\nQuestion types by category:")
            for category, count in categories.items():
                print(f"  {category}: {count} types")
                
        except Exception as e:
            db.session.rollback()
            print(f"Error initializing question types: {e}")
            return False
        
        return True

if __name__ == '__main__':
    success = init_question_types()
    if success:
        print("\nQuestion types initialization completed successfully!")
    else:
        print("\nQuestion types initialization failed!")
        sys.exit(1) 