from flask import Flask, request, jsonify, send_from_directory
import requests
from flask_cors import CORS
from urllib.parse import quote
import os

app = Flask(__name__, static_folder='../public')
CORS(app)  # Enable CORS for all routes

# API Keys - Load from environment variables for security
FOURSQUARE_API_KEY = os.environ.get('FOURSQUARE_API_KEY', "fsq3O4D0phsJNt6+/2kMtnio+xzIefJgDf2Gx3dlDJAVkI0=")
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', "AIzaSyDZkrw3OvuAcWhdrgZCK_2DbWvYaf0K-_I")

# Serve React Frontend
@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

def get_venue_photos(venue_id, headers):
    """Helper function to get photos for a venue"""
    try:
        photos_response = requests.get(
            f"https://api.foursquare.com/v3/places/{venue_id}/photos",
            headers=headers,
            params={'limit': 1},
            timeout=5
        )
        if photos_response.status_code == 200:
            photos_data = photos_response.json()
            if photos_data and isinstance(photos_data, list):
                photo = photos_data[0]
                return f"{photo.get('prefix', '')}300x300{photo.get('suffix', '')}"
    except:
        pass
    return None

@app.route('/api/search-venues', methods=['POST'])
def search_venues():
    try:
        data = request.json
        location = data.get('location', 'New York').strip()
        query = data.get('query', 'restaurant').strip()
        budget = data.get('budget')
        
        headers = {
            "Accept": "application/json",
            "Authorization": FOURSQUARE_API_KEY
        }
        
        # Basic search parameters
        params = {
            'query': query,
            'near': location,
            'limit': 5,
            'fields': 'name,location,rating,price,fsq_id,categories,tel,website'
        }
        
        # Add price filter if budget is specified
        if budget and isinstance(budget, (int, float)):
            price_level = min(max(1, int(budget) // 25), 4)
            params['price'] = ','.join(str(i) for i in range(1, price_level + 1))
        
        # Make the search request
        search_response = requests.get(
            "https://api.foursquare.com/v3/places/search",
            headers=headers,
            params=params,
            timeout=10
        )
        
        # Check for API errors
        if search_response.status_code == 400:
            return jsonify({
                'success': False,
                'error': "Invalid request parameters",
                'suggestion': "Please check your location and search terms"
            }), 400
            
        search_response.raise_for_status()
        
        venues = search_response.json().get('results', [])
        enriched_venues = []
        
        for venue in venues:
            # Get basic venue info
            venue_data = {
                'id': venue.get('fsq_id'),
                'name': venue.get('name', 'Unknown Venue'),
                'address': ', '.join(filter(None, [
                    venue.get('location', {}).get('address'),
                    venue.get('location', {}).get('locality'),
                    venue.get('location', {}).get('region')
                ])) or 'Address not available',
                'rating': round(venue.get('rating', 0)),  # Round to nearest integer
                'price': venue.get('price', {}).get('tier', 0) if isinstance(venue.get('price'), dict) else venue.get('price', 0),
                'categories': [cat['name'] for cat in venue.get('categories', []) if 'name' in cat],
                'phone': venue.get('tel', 'Not available'),
                'website': venue.get('website', 'Not available'),
                'photo': None
            }
            
            # Get photo if available
            if venue_data['id']:
                venue_data['photo'] = get_venue_photos(venue_data['id'], headers)
            
            enriched_venues.append(venue_data)
        
        return jsonify({
            'success': True,
            'venues': enriched_venues,
            'search_params': {
                'location': location,
                'query': query,
                'budget': budget
            }
        })
        
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "400" in error_msg:
            return jsonify({
                'success': False,
                'error': "Invalid search parameters",
                'details': "Please check your location and search terms"
            }), 400
        elif "404" in error_msg:
            return jsonify({
                'success': False,
                'error': "Location not found",
                'details': "Try a different city or location"
            }), 404
        else:
            return jsonify({
                'success': False,
                'error': "Foursquare API error",
                'details': error_msg
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': "Internal server error",
            'details': str(e)
        }), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        prompt = {
            "contents": [{
                "parts": [{
                    "text": f"""You are a helpful assistant for the Venue Finder chatbot. Your role is to provide information and recommendations about venues. 
                    When asked about venues, respond with helpful details about types of venues, what to look for in a good venue, or general venue information.
                    
                    Current user query: {data.get('message')}
                    
                    Respond concisely with venue-related information. If the query isn't about venues, politely guide the conversation back to venue topics.
                    Example responses:
                    - "For restaurants, I recommend checking the rating and price level. Would you like me to find some in your area?"
                    - "That's an interesting question! As a venue finder, I specialize in helping with places like restaurants, cafes, and event spaces."
                    - "Good venues typically have ratings above 4.0. I can search for highly-rated options near you."
                    """
                }]
            }]
        }
        
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=prompt,
            timeout=10
        )
        
        response.raise_for_status()
        result = response.json()
        return jsonify({
            'success': True,
            'response': result['candidates'][0]['content']['parts'][0]['text']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': "Gemini API error",
            'details': str(e)
        }), 500

# Handle 404 errors
@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True)
