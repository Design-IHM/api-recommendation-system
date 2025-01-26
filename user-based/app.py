from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Configuration de l'émulateur Firestore
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Chemin vers le fichier service-account-key.json
current_dir = os.path.dirname(os.path.abspath(__file__))
cred = credentials.Certificate(os.path.join(current_dir, 'service-account-key.json'))

# Initialisation de Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'projectId': 'syst-recommandation'
    })

db = firestore.client()

def calculate_user_similarity(user1_history, user2_history):
    """Calcule la similarité entre deux utilisateurs basée sur leur historique de lecture"""
    similarity = 0
    common_books = 0

    for book_id, rating1 in user1_history.items():
        if book_id in user2_history:
            rating2 = user2_history[book_id]
            # Calculer la différence de notation
            rating_diff = abs(rating1 - rating2)
            similarity += 5 - rating_diff  # 5 est la note maximale
            common_books += 1

    # Retourner la similarité moyenne
    return similarity / common_books if common_books > 0 else 0

@app.route('/')
def home():
    """Page d'accueil avec la liste des endpoints disponibles"""
    return jsonify({
        "message": "Bienvenue sur l'API de recommandation de livres",
        "endpoints": {
            "test": "/test",
            "recommandations_utilisateur": "/recommendations/user/<user_id>",
            "livres_populaires": "/recommendations/popular",
            "mise_a_jour_historique": "/user/<user_id>/history (POST)"
        }
    })

@app.route('/test')
def test():
    """Route de test simple"""
    return jsonify({"message": "API fonctionne!"})

@app.route('/recommendations/user/<user_id>')
def get_user_recommendations(user_id):
    """Obtenir des recommandations personnalisées pour un utilisateur"""
    try:
        # Récupérer l'historique de l'utilisateur
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        user_data = user_doc.to_dict()
        user_history = user_data.get('readingHistory', {})

        # Récupérer tous les utilisateurs pour comparaison
        users_ref = db.collection('users').stream()
        similar_users = []

        for other_user_doc in users_ref:
            if other_user_doc.id != user_id:
                other_user_data = other_user_doc.to_dict()
                other_history = other_user_data.get('readingHistory', {})
                
                similarity = calculate_user_similarity(user_history, other_history)
                if similarity > 0:
                    similar_users.append({
                        'id': other_user_doc.id,
                        'similarity': similarity,
                        'history': other_history
                    })

        # Trier par similarité
        similar_users.sort(key=lambda x: x['similarity'], reverse=True)

        # Trouver des livres recommandés
        recommendations = []
        seen_books = set(user_history.keys())

        for similar_user in similar_users:
            for book_id, rating in similar_user['history'].items():
                if book_id not in seen_books and rating >= 4:
                    book_ref = db.collection('books').document(book_id)
                    book_doc = book_ref.get()
                    if book_doc.exists:
                        book_data = book_doc.to_dict()
                        book_data['id'] = book_id
                        recommendations.append(book_data)
                        seen_books.add(book_id)

        return jsonify({"recommendations": recommendations[:5]})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recommendations/popular')
def get_popular_books():
    """Obtenir les livres les plus populaires"""
    try:
        books_ref = db.collection('books').order_by('borrowCount', direction=firestore.Query.DESCENDING).limit(10)
        books = []
        
        for doc in books_ref.stream():
            book_data = doc.to_dict()
            book_data['id'] = doc.id
            books.append(book_data)

        return jsonify({"books": books})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/user/<user_id>/history', methods=['POST'])
def update_reading_history(user_id):
    """Mettre à jour l'historique de lecture d'un utilisateur"""
    try:
        data = request.get_json()
        book_id = data.get('bookId')
        rating = data.get('rating')

        if not book_id or not isinstance(rating, (int, float)) or rating < 0 or rating > 5:
            return jsonify({"error": "Données invalides"}), 400

        user_ref = db.collection('users').document(user_id)
        user_ref.set({
            'readingHistory': {
                book_id: rating
            }
        }, merge=True)

        return jsonify({"message": "Historique mis à jour avec succès"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
