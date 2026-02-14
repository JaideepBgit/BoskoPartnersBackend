# ============================================================================
# AUDIENCE TARGETING SYSTEM - BACKEND ROUTES
# ============================================================================
# This module provides API endpoints for creating and managing audiences
# for sending reminders and communications to targeted groups of users.
# ============================================================================

from flask import jsonify, request
from sqlalchemy import text
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

def register_audience_routes(app, db):
    """Register all audience-related routes with the Flask app"""
    
    # Import models (assuming they're defined in app.py)
    from app import User, Organization, OrganizationType, SurveyResponse
    
    # ========================================================================
    # AUDIENCE CRUD OPERATIONS
    # ========================================================================
    
    @app.route('/api/audiences', methods=['GET'])
    def get_audiences():
        """Get all audiences with their metadata"""
        try:
            query = text("""
                SELECT 
                    a.id,
                    a.name,
                    a.description,
                    a.audience_type,
                    a.filter_criteria,
                    a.created_by,
                    a.created_at,
                    a.updated_at,
                    u.username as created_by_username,
                    u.firstname as created_by_firstname,
                    u.lastname as created_by_lastname
                FROM audiences a
                LEFT JOIN users u ON a.created_by = u.id
                ORDER BY a.created_at DESC
            """)
            
            result = db.session.execute(query)
            audiences = []
            
            for row in result:
                audience = {
                    'id': row.id,
                    'name': row.name,
                    'description': row.description,
                    'audience_type': row.audience_type,
                    'filter_criteria': row.filter_criteria,
                    'created_by': row.created_by,
                    'created_by_name': f"{row.created_by_firstname or ''} {row.created_by_lastname or ''}".strip() or row.created_by_username,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'updated_at': row.updated_at.isoformat() if row.updated_at else None
                }
                audiences.append(audience)
            
            logger.info(f"Retrieved {len(audiences)} audiences")
            return jsonify({'audiences': audiences}), 200
            
        except Exception as e:
            logger.error(f"Error fetching audiences: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to fetch audiences: {str(e)}'}), 500
    
    @app.route('/api/audiences/<int:audience_id>', methods=['GET'])
    def get_audience(audience_id):
        """Get a specific audience with all its details"""
        try:
            # Get audience metadata
            query = text("""
                SELECT 
                    a.id,
                    a.name,
                    a.description,
                    a.audience_type,
                    a.filter_criteria,
                    a.created_by,
                    a.created_at,
                    a.updated_at
                FROM audiences a
                WHERE a.id = :audience_id
            """)
            
            result = db.session.execute(query, {'audience_id': audience_id}).fetchone()
            
            if not result:
                return jsonify({'error': 'Audience not found'}), 404
            
            audience = {
                'id': result.id,
                'name': result.name,
                'description': result.description,
                'audience_type': result.audience_type,
                'filter_criteria': result.filter_criteria,
                'created_by': result.created_by,
                'created_at': result.created_at.isoformat() if result.created_at else None,
                'updated_at': result.updated_at.isoformat() if result.updated_at else None
            }
            
            # Get user IDs if audience includes users
            user_ids_query = text("""
                SELECT user_ids, notes 
                FROM audience_users 
                WHERE audience_id = :audience_id
            """)
            user_ids_result = db.session.execute(user_ids_query, {'audience_id': audience_id}).fetchone()
            audience['user_ids'] = user_ids_result.user_ids if user_ids_result else []
            audience['user_notes'] = user_ids_result.notes if user_ids_result else None
            
            # Get organization IDs if audience includes organizations
            org_ids_query = text("""
                SELECT organization_ids, notes 
                FROM audience_organizations 
                WHERE audience_id = :audience_id
            """)
            org_ids_result = db.session.execute(org_ids_query, {'audience_id': audience_id}).fetchone()
            audience['organization_ids'] = org_ids_result.organization_ids if org_ids_result else []
            audience['organization_notes'] = org_ids_result.notes if org_ids_result else None
            
            # Get association IDs if audience includes associations
            assoc_ids_query = text("""
                SELECT organization_type_ids, notes 
                FROM audience_associations 
                WHERE audience_id = :audience_id
            """)
            assoc_ids_result = db.session.execute(assoc_ids_query, {'audience_id': audience_id}).fetchone()
            audience['organization_type_ids'] = assoc_ids_result.organization_type_ids if assoc_ids_result else []
            audience['association_notes'] = assoc_ids_result.notes if assoc_ids_result else None
            
            return jsonify(audience), 200
            
        except Exception as e:
            logger.error(f"Error fetching audience {audience_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to fetch audience: {str(e)}'}), 500
    
    @app.route('/api/audiences', methods=['POST'])
    def create_audience():
        """Create a new audience"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if not data.get('name'):
                return jsonify({'error': 'Audience name is required'}), 400
            
            if not data.get('audience_type'):
                return jsonify({'error': 'Audience type is required'}), 400
            
            if not data.get('created_by'):
                return jsonify({'error': 'created_by user ID is required'}), 400
            
            # Insert audience
            insert_query = text("""
                INSERT INTO audiences (name, description, created_by, audience_type, filter_criteria)
                VALUES (:name, :description, :created_by, :audience_type, :filter_criteria)
            """)
            
            result = db.session.execute(insert_query, {
                'name': data['name'],
                'description': data.get('description'),
                'created_by': data['created_by'],
                'audience_type': data['audience_type'],
                'filter_criteria': data.get('filter_criteria')
            })
            
            db.session.commit()
            audience_id = result.lastrowid
            
            # Insert user IDs if provided
            if data.get('user_ids'):
                user_insert = text("""
                    INSERT INTO audience_users (audience_id, user_ids, added_by, notes)
                    VALUES (:audience_id, :user_ids, :added_by, :notes)
                """)
                db.session.execute(user_insert, {
                    'audience_id': audience_id,
                    'user_ids': data['user_ids'],
                    'added_by': data['created_by'],
                    'notes': data.get('user_notes')
                })
            
            # Insert organization IDs if provided
            if data.get('organization_ids'):
                org_insert = text("""
                    INSERT INTO audience_organizations (audience_id, organization_ids, added_by, notes)
                    VALUES (:audience_id, :organization_ids, :added_by, :notes)
                """)
                db.session.execute(org_insert, {
                    'audience_id': audience_id,
                    'organization_ids': data['organization_ids'],
                    'added_by': data['created_by'],
                    'notes': data.get('organization_notes')
                })
            
            # Insert organization type IDs if provided
            if data.get('organization_type_ids'):
                assoc_insert = text("""
                    INSERT INTO audience_associations (audience_id, organization_type_ids, added_by, notes)
                    VALUES (:audience_id, :organization_type_ids, :added_by, :notes)
                """)
                db.session.execute(assoc_insert, {
                    'audience_id': audience_id,
                    'organization_type_ids': data['organization_type_ids'],
                    'added_by': data['created_by'],
                    'notes': data.get('association_notes')
                })
            
            db.session.commit()
            
            logger.info(f"Created audience {audience_id}: {data['name']}")
            return jsonify({
                'message': 'Audience created successfully',
                'audience_id': audience_id
            }), 201
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating audience: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to create audience: {str(e)}'}), 500
    
    @app.route('/api/audiences/<int:audience_id>', methods=['PUT'])
    def update_audience(audience_id):
        """Update an existing audience"""
        try:
            data = request.get_json()
            
            # Update audience metadata
            update_query = text("""
                UPDATE audiences 
                SET name = :name,
                    description = :description,
                    audience_type = :audience_type,
                    filter_criteria = :filter_criteria,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :audience_id
            """)
            
            db.session.execute(update_query, {
                'audience_id': audience_id,
                'name': data['name'],
                'description': data.get('description'),
                'audience_type': data['audience_type'],
                'filter_criteria': data.get('filter_criteria')
            })
            
            # Update user IDs
            if 'user_ids' in data:
                # Delete existing and insert new
                db.session.execute(
                    text("DELETE FROM audience_users WHERE audience_id = :audience_id"),
                    {'audience_id': audience_id}
                )
                if data['user_ids']:
                    db.session.execute(text("""
                        INSERT INTO audience_users (audience_id, user_ids, added_by, notes)
                        VALUES (:audience_id, :user_ids, :added_by, :notes)
                    """), {
                        'audience_id': audience_id,
                        'user_ids': data['user_ids'],
                        'added_by': data.get('updated_by', data.get('created_by')),
                        'notes': data.get('user_notes')
                    })
            
            # Update organization IDs
            if 'organization_ids' in data:
                db.session.execute(
                    text("DELETE FROM audience_organizations WHERE audience_id = :audience_id"),
                    {'audience_id': audience_id}
                )
                if data['organization_ids']:
                    db.session.execute(text("""
                        INSERT INTO audience_organizations (audience_id, organization_ids, added_by, notes)
                        VALUES (:audience_id, :organization_ids, :added_by, :notes)
                    """), {
                        'audience_id': audience_id,
                        'organization_ids': data['organization_ids'],
                        'added_by': data.get('updated_by', data.get('created_by')),
                        'notes': data.get('organization_notes')
                    })
            
            # Update organization type IDs
            if 'organization_type_ids' in data:
                db.session.execute(
                    text("DELETE FROM audience_associations WHERE audience_id = :audience_id"),
                    {'audience_id': audience_id}
                )
                if data['organization_type_ids']:
                    db.session.execute(text("""
                        INSERT INTO audience_associations (audience_id, organization_type_ids, added_by, notes)
                        VALUES (:audience_id, :organization_type_ids, :added_by, :notes)
                    """), {
                        'audience_id': audience_id,
                        'organization_type_ids': data['organization_type_ids'],
                        'added_by': data.get('updated_by', data.get('created_by')),
                        'notes': data.get('association_notes')
                    })
            
            db.session.commit()
            
            logger.info(f"Updated audience {audience_id}")
            return jsonify({'message': 'Audience updated successfully'}), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating audience {audience_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to update audience: {str(e)}'}), 500
    
    @app.route('/api/audiences/<int:audience_id>', methods=['DELETE'])
    def delete_audience(audience_id):
        """Delete an audience (cascade deletes related records)"""
        try:
            delete_query = text("DELETE FROM audiences WHERE id = :audience_id")
            result = db.session.execute(delete_query, {'audience_id': audience_id})
            db.session.commit()
            
            if result.rowcount == 0:
                return jsonify({'error': 'Audience not found'}), 404
            
            logger.info(f"Deleted audience {audience_id}")
            return jsonify({'message': 'Audience deleted successfully'}), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting audience {audience_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to delete audience: {str(e)}'}), 500
    
    # ========================================================================
    # AUDIENCE MEMBERS RETRIEVAL
    # ========================================================================
    
    @app.route('/api/audiences/<int:audience_id>/members', methods=['GET'])
    def get_audience_members(audience_id):
        """Get all users that are part of this audience"""
        try:
            # Combined query to get all users from all sources
            query = text("""
                SELECT DISTINCT 
                    u.id,
                    u.username,
                    u.email,
                    u.firstname,
                    u.lastname,
                    u.survey_code,
                    u.organization_id,
                    o.name as organization_name,
                    'direct' as source
                FROM audience_users au
                JOIN users u ON JSON_CONTAINS(au.user_ids, CAST(u.id AS JSON))
                LEFT JOIN organizations o ON u.organization_id = o.id
                WHERE au.audience_id = :audience_id
                
                UNION
                
                SELECT DISTINCT 
                    u.id,
                    u.username,
                    u.email,
                    u.firstname,
                    u.lastname,
                    u.survey_code,
                    u.organization_id,
                    o.name as organization_name,
                    'organization' as source
                FROM audience_organizations ao
                JOIN organizations o ON JSON_CONTAINS(ao.organization_ids, CAST(o.id AS JSON))
                JOIN users u ON u.organization_id = o.id
                WHERE ao.audience_id = :audience_id
                
                UNION
                
                SELECT DISTINCT 
                    u.id,
                    u.username,
                    u.email,
                    u.firstname,
                    u.lastname,
                    u.survey_code,
                    u.organization_id,
                    o.name as organization_name,
                    'association' as source
                FROM audience_associations aa
                JOIN organizations o ON JSON_CONTAINS(aa.organization_type_ids, CAST(o.type AS JSON))
                JOIN users u ON u.organization_id = o.id
                WHERE aa.audience_id = :audience_id
                
                ORDER BY username
            """)
            
            result = db.session.execute(query, {'audience_id': audience_id})
            members = []
            
            for row in result:
                member = {
                    'id': row.id,
                    'username': row.username,
                    'email': row.email,
                    'firstname': row.firstname,
                    'lastname': row.lastname,
                    'survey_code': row.survey_code,
                    'organization_id': row.organization_id,
                    'organization_name': row.organization_name,
                    'source': row.source
                }
                members.append(member)
            
            logger.info(f"Retrieved {len(members)} members for audience {audience_id}")
            return jsonify({
                'audience_id': audience_id,
                'total_members': len(members),
                'members': members
            }), 200
            
        except Exception as e:
            logger.error(f"Error fetching audience members: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to fetch audience members: {str(e)}'}), 500
    
    # ========================================================================
    # SURVEY RESPONSE FILTERING
    # ========================================================================
    
    @app.route('/api/audiences/survey-responses', methods=['POST'])
    def get_users_from_survey_responses():
        """Get users based on survey response filters"""
        try:
            data = request.get_json()
            
            # Build dynamic query based on filters
            base_query = """
                SELECT DISTINCT 
                    u.id,
                    u.username,
                    u.email,
                    u.firstname,
                    u.lastname,
                    u.survey_code,
                    u.organization_id,
                    o.name as organization_name,
                    sr.template_id,
                    sr.status,
                    sr.submitted_at
                FROM survey_responses sr
                JOIN users u ON sr.user_id = u.id
                LEFT JOIN organizations o ON u.organization_id = o.id
                WHERE 1=1
            """
            
            params = {}
            
            # Add filters
            if data.get('template_id'):
                base_query += " AND sr.template_id = :template_id"
                params['template_id'] = data['template_id']
            
            if data.get('status'):
                base_query += " AND sr.status = :status"
                params['status'] = data['status']
            
            if data.get('organization_id'):
                base_query += " AND u.organization_id = :organization_id"
                params['organization_id'] = data['organization_id']
            
            if data.get('organization_type_id'):
                base_query += " AND o.type = :organization_type_id"
                params['organization_type_id'] = data['organization_type_id']
            
            # Date filters
            if data.get('submitted_after'):
                base_query += " AND sr.submitted_at >= :submitted_after"
                params['submitted_after'] = data['submitted_after']
            
            if data.get('submitted_before'):
                base_query += " AND sr.submitted_at <= :submitted_before"
                params['submitted_before'] = data['submitted_before']
            
            base_query += " ORDER BY u.username"
            
            result = db.session.execute(text(base_query), params)
            users = []
            
            for row in result:
                user = {
                    'id': row.id,
                    'username': row.username,
                    'email': row.email,
                    'firstname': row.firstname,
                    'lastname': row.lastname,
                    'survey_code': row.survey_code,
                    'organization_id': row.organization_id,
                    'organization_name': row.organization_name,
                    'template_id': row.template_id,
                    'status': row.status,
                    'submitted_at': row.submitted_at.isoformat() if row.submitted_at else None
                }
                users.append(user)
            
            logger.info(f"Found {len(users)} users matching survey response filters")
            return jsonify({
                'total_users': len(users),
                'users': users
            }), 200
            
        except Exception as e:
            logger.error(f"Error filtering survey responses: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to filter survey responses: {str(e)}'}), 500
    
    # ========================================================================
    # SEND REMINDERS TO AUDIENCE
    # ========================================================================
    
    @app.route('/api/audiences/<int:audience_id>/send-reminders', methods=['POST'])
    def send_audience_reminders(audience_id):
        """Send reminder emails to all members of an audience"""
        try:
            data = request.get_json()
            
            # Get all members of the audience
            members_response = get_audience_members(audience_id)
            members_data = members_response[0].get_json()
            members = members_data.get('members', [])
            
            if not members:
                return jsonify({'error': 'No members found in this audience'}), 400
            
            # Prepare bulk reminder data
            users_for_reminder = []
            for member in members:
                user_data = {
                    'to_email': member['email'],
                    'username': member['username'],
                    'survey_code': member['survey_code'],
                    'firstname': member['firstname'],
                    'organization_name': member['organization_name'],
                    'organization_id': member['organization_id'],
                    'days_remaining': data.get('days_remaining')
                }
                users_for_reminder.append(user_data)
            
            # Use existing bulk reminder endpoint logic
            from app import send_reminder_email
            
            results = {
                'total_users': len(users_for_reminder),
                'successful_sends': 0,
                'failed_sends': 0,
                'results': []
            }
            
            for user_data in users_for_reminder:
                try:
                    result = send_reminder_email(
                        to_email=user_data['to_email'],
                        username=user_data['username'],
                        survey_code=user_data['survey_code'],
                        firstname=user_data.get('firstname'),
                        organization_name=user_data.get('organization_name'),
                        days_remaining=user_data.get('days_remaining'),
                        organization_id=user_data.get('organization_id')
                    )
                    
                    if result['success']:
                        results['successful_sends'] += 1
                        results['results'].append({
                            'user': user_data['username'],
                            'email': user_data['to_email'],
                            'success': True
                        })
                    else:
                        results['failed_sends'] += 1
                        results['results'].append({
                            'user': user_data['username'],
                            'email': user_data['to_email'],
                            'success': False,
                            'error': result.get('error')
                        })
                        
                except Exception as e:
                    logger.error(f"Error sending reminder to {user_data['username']}: {str(e)}")
                    results['failed_sends'] += 1
                    results['results'].append({
                        'user': user_data['username'],
                        'email': user_data['to_email'],
                        'success': False,
                        'error': str(e)
                    })
            
            success_rate = (results['successful_sends'] / results['total_users'] * 100) if results['total_users'] > 0 else 0
            
            logger.info(f"Sent reminders to audience {audience_id}: {results['successful_sends']}/{results['total_users']} successful")
            
            return jsonify({
                'message': f'Reminders sent: {results["successful_sends"]} successful, {results["failed_sends"]} failed',
                'success_rate': round(success_rate, 1),
                'results': results
            }), 200
            
        except Exception as e:
            logger.error(f"Error sending audience reminders: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to send audience reminders: {str(e)}'}), 500
    
    logger.info("Audience routes registered successfully")
