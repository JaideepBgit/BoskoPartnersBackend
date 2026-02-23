"""
Geocoding routes.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.geo_location import GeoLocation
from ..services.geocoding_service import geocoding_service

logger = logging.getLogger(__name__)

geo_bp = Blueprint('geo', __name__)


@geo_bp.route('/geo-locations', methods=['GET'])
def get_geo_locations():
    """Get all geo locations."""
    try:
        geo_locations = GeoLocation.query.all()
        return jsonify([g.to_dict() for g in geo_locations]), 200
    except Exception as e:
        logger.error(f"Error getting geo locations: {str(e)}")
        return jsonify({"error": str(e)}), 500


@geo_bp.route('/geo-locations', methods=['POST'])
def add_geo_location():
    """Create a new geo location."""
    data = request.json
    
    try:
        geo = GeoLocation(
            user_id=data.get('user_id'),
            organization_id=data.get('organization_id'),
            which=data.get('which'),
            continent=data.get('continent'),
            region=data.get('region'),
            province=data.get('province'),
            city=data.get('city'),
            town=data.get('town'),
            address_line1=data.get('address_line1'),
            address_line2=data.get('address_line2'),
            country=data.get('country'),
            postal_code=data.get('postal_code'),
            latitude=data.get('latitude', 0),
            longitude=data.get('longitude', 0)
        )
        db.session.add(geo)
        db.session.commit()
        
        return jsonify({
            "message": "Geo location created successfully",
            "id": geo.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating geo location: {str(e)}")
        return jsonify({"error": str(e)}), 500


@geo_bp.route('/geocode', methods=['POST'])
def geocode_endpoint():
    """Geocode an address to get latitude/longitude coordinates."""
    data = request.json
    
    try:
        address_components = {
            'address_line1': data.get('address') or data.get('address_line1'),
            'address_line2': data.get('address_line2'),
            'city': data.get('city'),
            'town': data.get('town'),
            'province': data.get('state') or data.get('province'),
            'country': data.get('country'),
            'postal_code': data.get('postal_code')
        }
        
        lat, lng = geocoding_service.geocode_address(address_components)
        
        if lat is not None and lng is not None:
            return jsonify({
                "success": True,
                "latitude": lat,
                "longitude": lng
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Could not geocode the provided address"
            }), 404
            
    except Exception as e:
        logger.error(f"Error geocoding address: {str(e)}")
        return jsonify({"error": str(e)}), 500


@geo_bp.route('/batch-update-coordinates', methods=['POST'])
def batch_update_coordinates():
    """Batch update coordinates for GeoLocation records with zero lat/lng."""
    try:
        # Get all geo locations with zero coordinates
        geo_locations = GeoLocation.query.filter(
            (GeoLocation.latitude == 0) | (GeoLocation.longitude == 0)
        ).all()
        
        updated = 0
        failed = 0
        
        for geo in geo_locations:
            if geocoding_service.update_geo_location_coordinates(geo):
                updated += 1
            else:
                failed += 1
        
        db.session.commit()
        
        return jsonify({
            "message": "Batch update completed",
            "updated": updated,
            "failed": failed,
            "total_processed": len(geo_locations)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in batch update: {str(e)}")
        return jsonify({"error": str(e)}), 500
