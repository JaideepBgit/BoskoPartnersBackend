# ============================================================================
# ROLE REQUEST / APPROVAL SYSTEM - BACKEND ROUTES
# ============================================================================
# Users can request new roles via the "+" button in the account menu.
# Admin/Root users can approve or deny these requests from the Approvals page.
# ============================================================================

from flask import jsonify, request
from sqlalchemy import and_
import logging
import traceback
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_models():
    """
    Get model references from the main module to avoid the dual-import problem.
    When app.py runs as __main__, 'from app import ...' would re-import app.py
    as a separate 'app' module, creating a second Flask/SQLAlchemy instance.
    This helper gets models from the actual running module instead.
    """
    main = sys.modules.get('__main__')
    if main and hasattr(main, 'RoleRequest'):
        return (
            main.User,
            main.Role,
            main.Organization,
            main.RoleRequest,
            main.user_roles,
        )
    # Fallback: if running from a different entry point (e.g. gunicorn)
    from app import User, Role, Organization, RoleRequest, user_roles
    return User, Role, Organization, RoleRequest, user_roles


def register_role_request_routes(app, db):
    """Register all role-request-related routes with the Flask app"""

    # ========================================================================
    # CREATE A ROLE REQUEST
    # ========================================================================
    @app.route('/api/role-requests', methods=['POST'])
    def create_role_request():
        """
        A logged-in user submits a request for a new role.
        Body: { user_id, role_id, organization_id, reason? }
        """
        try:
            User, Role, Organization, RoleRequest, user_roles = _get_models()

            data = request.get_json()
            user_id = data.get('user_id')
            role_id = data.get('role_id')
            organization_id = data.get('organization_id')
            reason = data.get('reason', '')

            if not all([user_id, role_id, organization_id]):
                return jsonify({'error': 'user_id, role_id, and organization_id are required'}), 400

            # Verify user exists
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Verify role exists
            role = Role.query.get(role_id)
            if not role:
                return jsonify({'error': 'Role not found'}), 404

            # Verify organization exists
            org = Organization.query.get(organization_id)
            if not org:
                return jsonify({'error': 'Organization not found'}), 404

            # Check if user already has this role in this org
            existing_role = db.session.execute(
                user_roles.select().where(
                    and_(
                        user_roles.c.user_id == user_id,
                        user_roles.c.role_id == role_id,
                        user_roles.c.organization_id == organization_id
                    )
                )
            ).fetchone()
            if existing_role:
                return jsonify({'error': 'You already have this role in this organization'}), 409

            # Check for existing pending request
            existing_request = RoleRequest.query.filter_by(
                user_id=user_id,
                requested_role_id=role_id,
                organization_id=organization_id,
                status='pending'
            ).first()
            if existing_request:
                return jsonify({'error': 'You already have a pending request for this role'}), 409

            role_request = RoleRequest(
                user_id=user_id,
                requested_role_id=role_id,
                organization_id=organization_id,
                reason=reason
            )
            db.session.add(role_request)
            db.session.commit()

            logger.info(f"Role request created: user {user_id} requested role '{role.name}' in org {organization_id}")

            return jsonify({
                'message': 'Role request submitted successfully',
                'id': role_request.id,
                'status': role_request.status
            }), 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating role request: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Failed to submit role request'}), 500

    # ========================================================================
    # GET ROLE REQUESTS (for Admin/Root - all pending; or for a specific user)
    # ========================================================================
    @app.route('/api/role-requests', methods=['GET'])
    def get_role_requests():
        """
        Get role requests.
        Query params:
          - status: filter by status (pending, approved, denied). Default: all
          - user_id: filter by requesting user
        """
        try:
            User, Role, Organization, RoleRequest, user_roles = _get_models()

            status_filter = request.args.get('status')
            user_id_filter = request.args.get('user_id')

            query = RoleRequest.query

            if status_filter:
                query = query.filter_by(status=status_filter)
            if user_id_filter:
                query = query.filter_by(user_id=int(user_id_filter))

            requests_list = query.order_by(RoleRequest.created_at.desc()).all()

            result = []
            for rr in requests_list:
                reviewer_name = None
                if rr.reviewer:
                    reviewer_name = f"{rr.reviewer.firstname or ''} {rr.reviewer.lastname or ''}".strip() or rr.reviewer.username

                result.append({
                    'id': rr.id,
                    'user_id': rr.user_id,
                    'user_name': f"{rr.user.firstname or ''} {rr.user.lastname or ''}".strip() or rr.user.username,
                    'user_email': rr.user.email,
                    'requested_role_id': rr.requested_role_id,
                    'requested_role_name': rr.requested_role.name,
                    'organization_id': rr.organization_id,
                    'organization_name': rr.organization.name if rr.organization else 'N/A',
                    'status': rr.status,
                    'reason': rr.reason,
                    'reviewed_by': rr.reviewed_by,
                    'reviewer_name': reviewer_name,
                    'reviewed_at': rr.reviewed_at.isoformat() if rr.reviewed_at else None,
                    'review_note': rr.review_note,
                    'created_at': rr.created_at.isoformat() if rr.created_at else None,
                    'updated_at': rr.updated_at.isoformat() if rr.updated_at else None,
                })

            return jsonify(result), 200

        except Exception as e:
            logger.error(f"Error fetching role requests: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to fetch role requests: {str(e)}'}), 500

    # ========================================================================
    # APPROVE OR DENY A ROLE REQUEST
    # ========================================================================
    @app.route('/api/role-requests/<int:request_id>/review', methods=['PUT'])
    def review_role_request(request_id):
        """
        Admin/Root approves or denies a role request.
        Body: { action: 'approve' | 'deny', reviewed_by, review_note? }
        """
        try:
            User, Role, Organization, RoleRequest, user_roles = _get_models()

            data = request.get_json()
            action = data.get('action')
            reviewed_by = data.get('reviewed_by')
            review_note = data.get('review_note', '')

            if action not in ('approve', 'deny'):
                return jsonify({'error': "action must be 'approve' or 'deny'"}), 400

            if not reviewed_by:
                return jsonify({'error': 'reviewed_by is required'}), 400

            role_request = RoleRequest.query.get(request_id)
            if not role_request:
                return jsonify({'error': 'Role request not found'}), 404

            if role_request.status != 'pending':
                return jsonify({'error': f'This request has already been {role_request.status}'}), 400

            # Verify reviewer exists and is admin/root
            reviewer = User.query.get(reviewed_by)
            if not reviewer:
                return jsonify({'error': 'Reviewer not found'}), 404

            new_status = 'approved' if action == 'approve' else 'denied'
            role_request.status = new_status
            role_request.reviewed_by = reviewed_by
            role_request.reviewed_at = datetime.utcnow()
            role_request.review_note = review_note

            if action == 'approve':
                # Actually assign the role to the user
                db.session.execute(
                    user_roles.insert().values(
                        user_id=role_request.user_id,
                        role_id=role_request.requested_role_id,
                        organization_id=role_request.organization_id
                    )
                )
                logger.info(
                    f"Role request {request_id} approved: user {role_request.user_id} "
                    f"granted role {role_request.requested_role.name} in org {role_request.organization_id}"
                )
            else:
                logger.info(f"Role request {request_id} denied by user {reviewed_by}")

            db.session.commit()

            return jsonify({
                'message': f'Role request {new_status}',
                'id': role_request.id,
                'status': new_status
            }), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error reviewing role request: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Failed to review role request'}), 500

    # ========================================================================
    # GET PENDING REQUEST COUNT (for badge on Approvals sidebar item)
    # ========================================================================
    @app.route('/api/role-requests/pending-count', methods=['GET'])
    def get_pending_role_requests_count():
        """Returns the count of pending role requests."""
        try:
            User, Role, Organization, RoleRequest, user_roles = _get_models()

            count = RoleRequest.query.filter_by(status='pending').count()
            return jsonify({'count': count}), 200
        except Exception as e:
            logger.error(f"Error getting pending count: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Failed to get pending count'}), 500
