"""
Geocoding service for address to coordinates conversion.
"""
import os
import logging
import time
import requests

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from ..config.settings import Config

logger = logging.getLogger(__name__)


class GeocodingService:
    """Service class for geocoding operations."""
    
    def __init__(self):
        self.config = Config()
        self._nominatim = None
    
    def get_nominatim(self):
        """Get Nominatim geocoder instance."""
        if not self._nominatim:
            self._nominatim = Nominatim(user_agent="saurara_platform")
        return self._nominatim
    
    def geocode_address(self, address_components):
        """
        Geocode an address using multiple components and return latitude, longitude.
        
        Args:
            address_components (dict): Dictionary containing address components like:
                - address_line1, address_line2, city, town, province, country, postal_code
        
        Returns:
            tuple: (latitude, longitude) or (None, None) if geocoding fails
        """
        try:
            # Build address string from components
            parts = []
            
            if address_components.get('address_line1'):
                parts.append(address_components['address_line1'])
            if address_components.get('address_line2'):
                parts.append(address_components['address_line2'])
            if address_components.get('town'):
                parts.append(address_components['town'])
            if address_components.get('city'):
                parts.append(address_components['city'])
            if address_components.get('province'):
                parts.append(address_components['province'])
            if address_components.get('postal_code'):
                parts.append(address_components['postal_code'])
            if address_components.get('country'):
                parts.append(address_components['country'])
            
            if not parts:
                logger.warning("No address components provided for geocoding")
                return None, None
            
            address_string = ', '.join(parts)
            logger.info(f"Geocoding address: {address_string}")
            
            # Try Nominatim first
            result = self._geocode_nominatim(address_string)
            if result[0] is not None:
                return result
            
            # Fall back to Google Maps if Nominatim fails and API key is available
            if self.config.GOOGLE_MAPS_API_KEY:
                result = self._geocode_google(address_string)
                if result[0] is not None:
                    return result
            
            logger.warning(f"Failed to geocode address: {address_string}")
            return None, None
            
        except Exception as e:
            logger.error(f"Error geocoding address: {str(e)}")
            return None, None
    
    def _geocode_nominatim(self, address_string, retry=0):
        """Geocode using Nominatim service."""
        try:
            geolocator = self.get_nominatim()
            location = geolocator.geocode(address_string, timeout=10)
            
            if location:
                logger.info(f"Nominatim geocoding successful: {location.latitude}, {location.longitude}")
                return location.latitude, location.longitude
            
            return None, None
            
        except GeocoderTimedOut:
            if retry < 3:
                time.sleep(1)
                return self._geocode_nominatim(address_string, retry + 1)
            logger.warning("Nominatim geocoding timed out after 3 retries")
            return None, None
        except GeocoderServiceError as e:
            logger.error(f"Nominatim service error: {str(e)}")
            return None, None
        except Exception as e:
            logger.error(f"Nominatim geocoding error: {str(e)}")
            return None, None
    
    def _geocode_google(self, address_string):
        """Geocode using Google Maps API."""
        try:
            api_key = self.config.GOOGLE_MAPS_API_KEY
            if not api_key:
                return None, None
            
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "address": address_string,
                "key": api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                logger.info(f"Google geocoding successful: {location['lat']}, {location['lng']}")
                return location["lat"], location["lng"]
            
            logger.warning(f"Google geocoding returned status: {data.get('status')}")
            return None, None
            
        except Exception as e:
            logger.error(f"Google geocoding error: {str(e)}")
            return None, None
    
    def update_geo_location_coordinates(self, geo_location):
        """
        Update latitude and longitude for a GeoLocation record if they are zero.
        
        Args:
            geo_location: GeoLocation model instance
        
        Returns:
            bool: True if coordinates were updated, False otherwise
        """
        try:
            # Check if coordinates need updating
            if (float(geo_location.latitude or 0) != 0 or 
                float(geo_location.longitude or 0) != 0):
                return False
            
            # Build address components
            address_components = {
                'address_line1': geo_location.address_line1,
                'address_line2': geo_location.address_line2,
                'city': geo_location.city,
                'town': geo_location.town,
                'province': geo_location.province,
                'country': geo_location.country,
                'postal_code': geo_location.postal_code
            }
            
            lat, lng = self.geocode_address(address_components)
            
            if lat is not None and lng is not None:
                geo_location.latitude = lat
                geo_location.longitude = lng
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating geo location coordinates: {str(e)}")
            return False
    
    def build_address_string(self, city=None, state=None, country=None, address=None, town=None):
        """Build a complete address string from components for geocoding."""
        parts = []
        if address:
            parts.append(address)
        if town:
            parts.append(town)
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if country:
            parts.append(country)
        
        return ', '.join(parts) if parts else ''


# Create a singleton instance
geocoding_service = GeocodingService()
