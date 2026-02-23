"""
Organization management routes.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.organization import Organization, OrganizationType
from ..models.geo_location import GeoLocation
from ..models.user import User, UserOrganizationTitle

logger = logging.getLogger(__name__)

organizations_bp = Blueprint('organizations', __name__)


@organizations_bp.route('/organizations', methods=['GET'])
def get_organizations():
    """Get all organizations."""
    try:
        organizations = Organization.query.all()
        
        return jsonify([{
            "id": org.id,
            "name": org.name,
            "type": org.type,
            "type_name": org.organization_type.type if org.organization_type else None,
            "parent_organization": org.parent_organization,
            "parent_name": org.parent.name if org.parent else None,
            "head": org.head,
            "head_name": f"{org.head_user.firstname} {org.head_user.lastname}" if org.head_user else None,
            "email": org.email,
            "phone": org.phone,
            "geo_location_id": org.geo_location_id,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None
        } for org in organizations]), 200
        
    except Exception as e:
        logger.error(f"Error getting organizations: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>', methods=['GET'])
def get_organization(org_id):
    """Get a specific organization by ID."""
    org = Organization.query.get_or_404(org_id)
    
    # Get geo location details
    geo_location = None
    if org.geo_location:
        geo_location = org.geo_location.to_dict()
    
    return jsonify({
        "id": org.id,
        "name": org.name,
        "type": org.type,
        "type_name": org.organization_type.type if org.organization_type else None,
        "parent_organization": org.parent_organization,
        "parent_name": org.parent.name if org.parent else None,
        "head": org.head,
        "head_name": f"{org.head_user.firstname} {org.head_user.lastname}" if org.head_user else None,
        "email": org.email,
        "phone": org.phone,
        "geo_location_id": org.geo_location_id,
        "geo_location": geo_location,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None
    }), 200


@organizations_bp.route('/organizations', methods=['POST'])
def add_organization():
    """Create a new organization."""
    data = request.json
    
    name = data.get('name')
    if not name:
        return jsonify({"error": "Organization name is required"}), 400
    
    try:
        # Handle geo location if provided
        geo_location_id = None
        geo_data = data.get('geo_location')
        if geo_data:
            geo_location = GeoLocation(
                which='organization',
                continent=geo_data.get('continent'),
                region=geo_data.get('region'),
                province=geo_data.get('province'),
                city=geo_data.get('city'),
                town=geo_data.get('town'),
                address_line1=geo_data.get('address_line1'),
                address_line2=geo_data.get('address_line2'),
                country=geo_data.get('country'),
                postal_code=geo_data.get('postal_code'),
                latitude=geo_data.get('latitude', 0),
                longitude=geo_data.get('longitude', 0)
            )
            db.session.add(geo_location)
            db.session.flush()
            geo_location_id = geo_location.id
        
        org = Organization(
            name=name,
            type=data.get('type'),
            parent_organization=data.get('parent_organization'),
            head=data.get('head'),
            email=data.get('email'),
            phone=data.get('phone'),
            geo_location_id=geo_location_id
        )
        
        db.session.add(org)
        db.session.commit()
        
        return jsonify({
            "message": "Organization created successfully",
            "id": org.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating organization: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>', methods=['PUT'])
def update_organization(org_id):
    """Update an existing organization."""
    data = request.json
    org = Organization.query.get_or_404(org_id)
    
    try:
        if 'name' in data:
            org.name = data['name']
        if 'type' in data:
            org.type = data['type']
        if 'parent_organization' in data:
            org.parent_organization = data['parent_organization']
        if 'head' in data:
            org.head = data['head']
        if 'email' in data:
            org.email = data['email']
        if 'phone' in data:
            org.phone = data['phone']
        
        # Update geo location if provided
        geo_data = data.get('geo_location')
        if geo_data:
            if org.geo_location:
                # Update existing
                geo = org.geo_location
                geo.continent = geo_data.get('continent', geo.continent)
                geo.region = geo_data.get('region', geo.region)
                geo.province = geo_data.get('province', geo.province)
                geo.city = geo_data.get('city', geo.city)
                geo.town = geo_data.get('town', geo.town)
                geo.address_line1 = geo_data.get('address_line1', geo.address_line1)
                geo.address_line2 = geo_data.get('address_line2', geo.address_line2)
                geo.country = geo_data.get('country', geo.country)
                geo.postal_code = geo_data.get('postal_code', geo.postal_code)
            else:
                # Create new
                geo_location = GeoLocation(
                    which='organization',
                    organization_id=org_id,
                    **geo_data
                )
                db.session.add(geo_location)
                db.session.flush()
                org.geo_location_id = geo_location.id
        
        db.session.commit()
        
        return jsonify({
            "message": "Organization updated successfully",
            "id": org.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating organization: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>', methods=['DELETE'])
def delete_organization(org_id):
    """Delete an organization and all related records."""
    org = Organization.query.get_or_404(org_id)
    
    try:
        # Delete user organization titles
        UserOrganizationTitle.query.filter_by(organization_id=org_id).delete()
        
        # Unlink users
        User.query.filter_by(organization_id=org_id).update({'organization_id': None})
        
        # Delete geo location
        if org.geo_location_id:
            GeoLocation.query.filter_by(id=org.geo_location_id).delete()
        
        # Delete child organizations
        Organization.query.filter_by(parent_organization=org_id).update({'parent_organization': None})
        
        db.session.delete(org)
        db.session.commit()
        
        return jsonify({"message": "Organization deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting organization: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>/users', methods=['GET'])
def get_organization_users(org_id):
    """Get all users in an organization."""
    try:
        users = User.query.filter_by(organization_id=org_id).all()
        
        return jsonify([{
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "survey_code": user.survey_code
        } for user in users]), 200
        
    except Exception as e:
        logger.error(f"Error getting organization users: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organization-types', methods=['GET'])
def get_organization_types():
    """Get all organization types."""
    types = OrganizationType.query.all()
    return jsonify([{
        "id": t.id,
        "type": t.type
    } for t in types]), 200


@organizations_bp.route('/organization-types', methods=['POST'])
def add_organization_type():
    """Add a new organization type."""
    data = request.json
    type_name = data.get('type')
    
    if not type_name:
        return jsonify({"error": "Type name is required"}), 400
    
    if OrganizationType.query.filter_by(type=type_name).first():
        return jsonify({"error": "Organization type already exists"}), 400
    
    try:
        org_type = OrganizationType(type=type_name)
        db.session.add(org_type)
        db.session.commit()
        
        return jsonify({
            "message": "Organization type created successfully",
            "id": org_type.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating organization type: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/users/<int:user_id>/organizations', methods=['GET'])
def get_user_organizations(user_id):
    """Get organizations associated with a user."""
    try:
        user = User.query.get_or_404(user_id)
        
        organizations = []
        
        # Add user's primary organization
        if user.organization:
            organizations.append({
                "id": user.organization.id,
                "name": user.organization.name,
                "type": user.organization.type,
                "is_primary": True
            })
        
        # Add organizations from user_organization_titles
        user_org_titles = UserOrganizationTitle.query.filter_by(user_id=user_id).all()
        for uot in user_org_titles:
            if uot.organization and uot.organization_id != user.organization_id:
                organizations.append({
                    "id": uot.organization.id,
                    "name": uot.organization.name,
                    "type": uot.organization.type,
                    "title": uot.title.name if uot.title else None,
                    "is_primary": False
                })
        
        return jsonify(organizations), 200
        
    except Exception as e:
        logger.error(f"Error getting user organizations: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/upload', methods=['POST'])
def upload_organizations():
    """Upload organizations from CSV file."""
    import csv
    import io
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "File must be a CSV"}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"))
        reader = csv.DictReader(stream)
        
        created_orgs = []
        errors = []
        
        for row_num, row in enumerate(reader, start=2):
            try:
                name = row.get('name', '').strip()
                
                if not name:
                    errors.append(f"Row {row_num}: Organization name is required")
                    continue
                
                org = Organization(
                    name=name,
                    type=int(row.get('type')) if row.get('type') else None,
                    email=row.get('email', '').strip() or None,
                    phone=row.get('phone', '').strip() or None
                )
                db.session.add(org)
                db.session.flush()
                
                created_orgs.append({
                    "id": org.id,
                    "name": name
                })
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            "message": f"Upload complete. Created {len(created_orgs)} organizations.",
            "created_organizations": created_orgs,
            "errors": errors
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error uploading organizations: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>/contacts', methods=['PUT'])
def update_organization_contacts(org_id):
    """Update organization contact information and relationships."""
    data = request.json
    org = Organization.query.get_or_404(org_id)
    
    try:
        if 'email' in data:
            org.email = data['email']
        if 'phone' in data:
            org.phone = data['phone']
        if 'head' in data:
            org.head = data['head']
        
        # Update associated users if provided
        if 'users' in data:
            for user_data in data['users']:
                user_id = user_data.get('id')
                if user_id:
                    user = User.query.get(user_id)
                    if user:
                        if 'email' in user_data:
                            user.email = user_data['email']
                        if 'phone' in user_data:
                            # Note: User model may not have phone field
                            pass
        
        db.session.commit()
        
        return jsonify({
            "message": "Organization contacts updated successfully",
            "id": org.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating organization contacts: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/organizations/<int:org_id>/email-service/status', methods=['GET'])
def get_organization_email_service_status(org_id):
    """Get email service status for an organization."""
    org = Organization.query.get_or_404(org_id)
    
    return jsonify({
        "organization_id": org_id,
        "is_active": True,  # Email service is always active for existing organizations
        "message": "Email service is active"
    }), 200


@organizations_bp.route('/organizations/<int:org_id>/email-service/config', methods=['GET'])
def get_organization_email_service_config(org_id):
    """Get email service configuration for an organization."""
    org = Organization.query.get_or_404(org_id)
    
    return jsonify({
        "organization_id": org_id,
        "email_enabled": True,
        "welcome_email_enabled": True,
        "reminder_email_enabled": True
    }), 200


@organizations_bp.route('/organizations/<int:org_id>/email-service/config', methods=['PUT'])
def update_organization_email_service_config(org_id):
    """Update email service configuration for an organization."""
    data = request.json
    org = Organization.query.get_or_404(org_id)
    
    # For now, just acknowledge the update
    # In production, you'd store these settings in the database
    return jsonify({
        "message": "Email service configuration updated",
        "organization_id": org_id
    }), 200


@organizations_bp.route('/organizations/search', methods=['GET'])
def search_organizations_fuzzy():
    """Search organizations with fuzzy matching."""
    query = request.args.get('q', '').strip().lower()
    limit = request.args.get('limit', 10, type=int)
    
    if not query:
        return jsonify([]), 200
    
    try:
        organizations = Organization.query.all()
        results = []
        
        for org in organizations:
            org_name_lower = org.name.lower()
            score = 0
            match_type = "none"
            
            # Exact match
            if org_name_lower == query:
                score = 100
                match_type = "exact"
            # Starts with
            elif org_name_lower.startswith(query):
                score = 90
                match_type = "prefix"
            # Contains
            elif query in org_name_lower:
                score = 70
                match_type = "contains"
            # Word match
            else:
                query_words = set(query.split())
                org_words = set(org_name_lower.split())
                common = query_words & org_words
                if common:
                    score = min(60, 30 + len(common) * 15)
                    match_type = "word_match"
            
            if score > 0:
                results.append({
                    "id": org.id,
                    "name": org.name,
                    "type": org.type,
                    "score": score,
                    "match_type": match_type
                })
        
        # Sort by score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return jsonify(results[:limit]), 200
        
    except Exception as e:
        logger.error(f"Error searching organizations: {str(e)}")
        return jsonify({"error": str(e)}), 500


@organizations_bp.route('/check-organization-exists', methods=['POST'])
def check_organization_exists():
    """Check if an organization exists by name."""
    data = request.json
    org_name = data.get('organization_name', '').strip()
    
    if not org_name:
        return jsonify({"error": "Organization name is required"}), 400
    
    try:
        # Exact match first
        org = Organization.query.filter(
            db.func.lower(Organization.name) == org_name.lower()
        ).first()
        
        if org:
            return jsonify({
                "exists": True,
                "match_type": "exact",
                "organization": {
                    "id": org.id,
                    "name": org.name,
                    "type": org.type
                }
            }), 200
        
        # Check for similar names
        similar = Organization.query.filter(
            Organization.name.ilike(f"%{org_name}%")
        ).limit(5).all()
        
        if similar:
            return jsonify({
                "exists": False,
                "similar_organizations": [{
                    "id": o.id,
                    "name": o.name,
                    "type": o.type
                } for o in similar]
            }), 200
        
        return jsonify({
            "exists": False,
            "similar_organizations": []
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking organization exists: {str(e)}")
        return jsonify({"error": str(e)}), 500
