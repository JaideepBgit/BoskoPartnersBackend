"""
Contact referral routes.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.contact import ContactReferral, ReferralLink
from ..models.user import User

logger = logging.getLogger(__name__)

contact_referrals_bp = Blueprint('contact_referrals', __name__)


# ==========================================
# Referral Link Endpoints
# ==========================================

@contact_referrals_bp.route('/referral-links/generate', methods=['POST'])
def generate_referral_link():
    """Generate or retrieve an existing referral link for a user."""
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    try:
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Check if user already has an active referral link
        existing_link = ReferralLink.query.filter_by(user_id=user_id, is_active=True).first()
        
        if existing_link:
            return jsonify({
                "referral_code": existing_link.referral_code,
                "is_new": False,
                "link": existing_link.to_dict()
            }), 200
        
        # Generate a new referral link
        referral_code = ReferralLink.generate_code()
        
        # Ensure uniqueness
        while ReferralLink.query.filter_by(referral_code=referral_code).first():
            referral_code = ReferralLink.generate_code()
        
        new_link = ReferralLink(
            user_id=user_id,
            referral_code=referral_code,
            is_active=True
        )
        db.session.add(new_link)
        db.session.commit()
        
        return jsonify({
            "referral_code": new_link.referral_code,
            "is_new": True,
            "link": new_link.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating referral link: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/referral-links/validate/<string:code>', methods=['GET'])
def validate_referral_link(code):
    """Validate a referral code and return the referring user's info."""
    try:
        link = ReferralLink.query.filter_by(referral_code=code, is_active=True).first()
        
        if not link:
            return jsonify({
                "valid": False,
                "message": "Invalid or expired referral link"
            }), 404
        
        # Increment click count
        link.click_count += 1
        db.session.commit()
        
        # Get referring user info
        user = User.query.get(link.user_id)
        referring_user = None
        if user:
            referring_user = {
                "id": user.id,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "email": user.email,
                "organization_id": user.organization_id
            }
        
        return jsonify({
            "valid": True,
            "referral_link_id": link.id,
            "referring_user": referring_user,
            "message": "Valid referral link"
        }), 200
        
    except Exception as e:
        logger.error(f"Error validating referral link: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/referral-links/user/<int:user_id>', methods=['GET'])
def get_user_referral_links(user_id):
    """Get all referral links for a specific user."""
    try:
        links = ReferralLink.query.filter_by(user_id=user_id).order_by(ReferralLink.created_at.desc()).all()
        return jsonify([link.to_dict() for link in links]), 200
    except Exception as e:
        logger.error(f"Error getting user referral links: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/contact-referrals', methods=['GET'])
def get_contact_referrals():
    """Get all contact referrals (admin endpoint)."""
    try:
        status = request.args.get('status')
        
        query = ContactReferral.query.filter_by(parent_referral_id=None)  # Only get top-level referrals
        
        if status:
            query = query.filter_by(status=status)
        
        referrals = query.order_by(ContactReferral.created_at.desc()).all()
        
        return jsonify([r.to_dict() for r in referrals]), 200
        
    except Exception as e:
        logger.error(f"Error getting contact referrals: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/contact-referrals', methods=['POST'])
def create_contact_referral():
    """Create a new contact referral submission."""
    data = request.json
    
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    
    if not all([first_name, last_name, email]):
        return jsonify({"error": "First name, last name, and email are required"}), 400
    
    try:
        # If a referral_code is provided, resolve it to a referral_link_id
        referred_by_link_id = data.get('referred_by_link_id')
        referral_code = data.get('referral_code')
        if referral_code and not referred_by_link_id:
            link = ReferralLink.query.filter_by(referral_code=referral_code, is_active=True).first()
            if link:
                referred_by_link_id = link.id
        
        referral = ContactReferral(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=data.get('phone'),
            organization_name=data.get('organization_name'),
            organization_type=data.get('organization_type'),
            country=data.get('country'),
            city=data.get('city'),
            province=data.get('province'),
            role_in_organization=data.get('role_in_organization'),
            notes=data.get('notes'),
            submitted_by_user_id=data.get('submitted_by_user_id'),
            referred_by_link_id=referred_by_link_id
        )
        db.session.add(referral)
        db.session.flush()
        
        # Add sub-referrals if provided
        sub_referrals = data.get('referrals', [])
        for sub_data in sub_referrals:
            if sub_data.get('email'):
                sub_referral = ContactReferral(
                    first_name=sub_data.get('first_name', ''),
                    last_name=sub_data.get('last_name', ''),
                    email=sub_data['email'],
                    phone=sub_data.get('phone'),
                    organization_name=sub_data.get('organization_name'),
                    role_in_organization=sub_data.get('role_in_organization'),
                    parent_referral_id=referral.id
                )
                db.session.add(sub_referral)
        
        db.session.commit()
        
        return jsonify({
            "message": "Contact referral submitted successfully",
            "id": referral.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating contact referral: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/contact-referrals/<int:referral_id>', methods=['PUT'])
def update_contact_referral(referral_id):
    """Update an existing contact referral."""
    data = request.json
    referral = ContactReferral.query.get_or_404(referral_id)
    
    try:
        if 'first_name' in data:
            referral.first_name = data['first_name']
        if 'last_name' in data:
            referral.last_name = data['last_name']
        if 'email' in data:
            referral.email = data['email']
        if 'phone' in data:
            referral.phone = data['phone']
        if 'organization_name' in data:
            referral.organization_name = data['organization_name']
        if 'organization_type' in data:
            referral.organization_type = data['organization_type']
        if 'country' in data:
            referral.country = data['country']
        if 'city' in data:
            referral.city = data['city']
        if 'province' in data:
            referral.province = data['province']
        if 'role_in_organization' in data:
            referral.role_in_organization = data['role_in_organization']
        if 'notes' in data:
            referral.notes = data['notes']
        if 'status' in data:
            referral.status = data['status']
        
        db.session.commit()
        
        return jsonify({
            "message": "Contact referral updated successfully",
            "id": referral.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating contact referral: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/contact-referrals/<int:referral_id>/approve', methods=['POST'])
def approve_contact_referral(referral_id):
    """Approve a contact referral and optionally create user/organization."""
    data = request.json
    referral = ContactReferral.query.get_or_404(referral_id)
    
    try:
        referral.status = 'approved'
        
        # Additional processing can be added here (create user, organization, etc.)
        
        db.session.commit()
        
        return jsonify({
            "message": "Contact referral approved successfully",
            "id": referral.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving contact referral: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/contact-referrals/<int:referral_id>/reject', methods=['DELETE'])
def reject_contact_referral(referral_id):
    """Reject and delete a contact referral."""
    referral = ContactReferral.query.get_or_404(referral_id)
    
    try:
        # If primary contact, also delete sub-referrals (cascade)
        db.session.delete(referral)
        db.session.commit()
        
        return jsonify({"message": "Contact referral rejected and deleted"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting contact referral: {str(e)}")
        return jsonify({"error": str(e)}), 500


@contact_referrals_bp.route('/check-email-exists', methods=['POST'])
def check_email_exists():
    """Check if an email exists in contact referrals or users table."""
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    try:
        # Check in users
        user = User.query.filter_by(email=email).first()
        if user:
            return jsonify({
                "exists": True,
                "location": "users",
                "message": "This email is already registered as a user"
            }), 200
        
        # Check in referrals
        referral = ContactReferral.query.filter_by(email=email).first()
        if referral:
            return jsonify({
                "exists": True,
                "location": "contact_referrals",
                "status": referral.status,
                "message": f"This email has already been submitted as a referral (status: {referral.status})"
            }), 200
        
        return jsonify({
            "exists": False,
            "message": "Email is available"
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking email: {str(e)}")
        return jsonify({"error": str(e)}), 500
